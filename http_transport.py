"""
HTTP Transport for Zen MCP Server

This module implements HTTP transport support alongside the existing stdio transport.
It provides a FastAPI-based HTTP server that implements the MCP streamable HTTP protocol
to enable direct connections from ChatMCP iOS and other HTTP-based MCP clients.
"""

import asyncio
import gzip
import json
import logging
import uuid
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from mcp.types import (
    CallToolRequest,
    GetPromptRequest,
    InitializeRequest,
    ListPromptsRequest,
    ListToolsRequest,
    TextContent,
)

# Import existing server handlers
from server import server, handle_call_tool, handle_list_tools, handle_list_prompts, handle_get_prompt

logger = logging.getLogger(__name__)

# Configuration for response chunking
DEFAULT_CHUNK_SIZE_KB = 20  # 20KB chunks for mobile compatibility
MIN_CHUNK_SIZE_KB = 8       # Minimum viable chunk size
MAX_CHUNK_SIZE_KB = 50      # Maximum chunk size for memory efficiency

class HTTPTransport:
    """HTTP transport implementation for MCP using FastAPI."""
    
    def __init__(self, host: str = "0.0.0.0", port: int = 8080):
        self.host = host
        self.port = port
        self.app = FastAPI(title="Zen MCP HTTP Server")
        self.sessions: Dict[str, Dict[str, Any]] = {}
        
        # Configure CORS
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
        # Add gzip compression for responses > 4KB
        self.app.add_middleware(GZipMiddleware, minimum_size=4096)
        
        self._setup_routes()
    
    def _chunk_tools_response(self, tools: list, message_id: str, chunk_size_kb: int = DEFAULT_CHUNK_SIZE_KB) -> list:
        """
        Chunk a large tools list into multiple MCP-compliant JSON-RPC responses.
        
        Each chunk will be a complete, valid JSON-RPC response with a subset of tools.
        This ensures mobile clients can process large tool lists without hitting
        SSE payload limits while maintaining full MCP protocol compliance.
        """
        chunk_size_bytes = chunk_size_kb * 1024
        chunks = []
        current_chunk = []
        current_size = 0
        
        # Base response overhead (without tools array)
        base_response = {
            "jsonrpc": "2.0", 
            "id": message_id,
            "result": {"tools": []}
        }
        base_size = len(json.dumps(base_response))
        
        for tool in tools:
            # Handle both Tool objects and dictionaries
            if hasattr(tool, 'name'):
                tool_data = {
                    "name": tool.name,
                    "description": tool.description,
                    "inputSchema": tool.inputSchema
                }
            else:
                # tool is already a dictionary
                tool_data = tool
            tool_size = len(json.dumps(tool_data))
            
            # Check if adding this tool would exceed chunk size
            if current_size + tool_size + base_size > chunk_size_bytes and current_chunk:
                # Create chunk with current tools
                chunk_response = {
                    "jsonrpc": "2.0",
                    "id": message_id, 
                    "result": {"tools": current_chunk}
                }
                chunks.append(chunk_response)
                logger.debug(f"[MCP Chunking] Created chunk with {len(current_chunk)} tools ({current_size + base_size} bytes)")
                
                # Start new chunk
                current_chunk = [tool_data]
                current_size = tool_size
            else:
                # Add to current chunk
                current_chunk.append(tool_data)
                current_size += tool_size
        
        # Add final chunk if there are remaining tools
        if current_chunk:
            chunk_response = {
                "jsonrpc": "2.0",
                "id": message_id,
                "result": {"tools": current_chunk}
            }
            chunks.append(chunk_response)
            logger.debug(f"[MCP Chunking] Created final chunk with {len(current_chunk)} tools ({current_size + base_size} bytes)")
        
        logger.info(f"[MCP Chunking] Split {len(tools)} tools into {len(chunks)} chunks (target: {chunk_size_kb}KB)")
        return chunks
    
    def _setup_routes(self):
        """Set up HTTP routes for MCP protocol."""
        
        @self.app.post("/mcp")
        async def handle_mcp_request(request: Request):
            """Handle MCP requests via streamable HTTP."""
            # Validate Accept header
            accept_header = request.headers.get("Accept", "")
            if not accept_header or not (
                "text/event-stream" in accept_header or "*/*" in accept_header
            ):
                raise HTTPException(
                    status_code=406,
                    detail="Not Acceptable: Client must accept text/event-stream"
                )
            
            # Get or create session
            session_id = request.headers.get("Mcp-Session-Id")
            if not session_id or session_id not in self.sessions:
                session_id = str(uuid.uuid4())
                self.sessions[session_id] = {"initialized": False}
            
            session = self.sessions[session_id]
            
            # Parse query parameters for enhanced features
            query_params = dict(request.query_params)
            view_mode = query_params.get("view", "compact")  # compact or full
            
            # Parse chunk size parameter for response optimization
            chunk_size_kb = DEFAULT_CHUNK_SIZE_KB
            if "chunk_size" in query_params:
                try:
                    requested_chunk_size = int(query_params["chunk_size"])
                    chunk_size_kb = max(MIN_CHUNK_SIZE_KB, min(requested_chunk_size, MAX_CHUNK_SIZE_KB))
                    logger.debug(f"[MCP HTTP] Using custom chunk size: {chunk_size_kb}KB")
                except (ValueError, TypeError):
                    logger.warning(f"[MCP HTTP] Invalid chunk_size parameter, using default: {DEFAULT_CHUNK_SIZE_KB}KB")
            
            # Parse request body
            try:
                body = await request.json()
            except Exception as e:
                logger.error(f"Failed to parse request body: {e}")
                raise HTTPException(status_code=400, detail="Invalid JSON")
            
            # Create streaming response with compression support
            response_generator = self._handle_mcp_message(session_id, session, body, query_params, chunk_size_kb)
            headers = {
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Mcp-Session-Id": session_id,
                "Vary": "view, chunk_size"  # Cache varies on view and chunk_size parameters
            }
            
            return StreamingResponse(
                response_generator,
                media_type="text/event-stream",
                headers=headers
            )
        
        @self.app.get("/health")
        async def health_check():
            """Health check endpoint."""
            return {"status": "ok", "server": "zen-mcp-http"}
    
    async def _handle_mcp_message(self, session_id: str, session: Dict[str, Any], message: Dict[str, Any], query_params: Dict[str, str] = None, chunk_size_kb: int = DEFAULT_CHUNK_SIZE_KB):
        """Handle individual MCP messages and yield SSE responses."""
        method = message.get("method")
        message_id = message.get("id")
        params = message.get("params", {})
        
        logger.info(f"[MCP HTTP] Request: {method} (id: {message_id})")
        
        try:
            if method == "initialize":
                result = await self._handle_initialize(session, params)
                response = {
                    "jsonrpc": "2.0",
                    "id": message_id,
                    "result": result
                }
            
            elif method == "notifications/initialized":
                # No response needed for notifications
                return
            
            elif method == "tools/list":
                tools = await handle_list_tools()
                
                # Parse query parameters
                query_params = query_params or {}
                view_mode = query_params.get("view", "compact")
                logger.debug(f"[MCP HTTP] Query params: {query_params}, view_mode: {view_mode}")
                
                # Handle tool pagination and filtering
                tool_ids = query_params.get("ids")
                if tool_ids:
                    # Selective tool loading: ?ids=chat,thinkdeep,debug
                    requested_ids = [id.strip() for id in tool_ids.split(",")]
                    tools = [tool for tool in tools if tool.name in requested_ids]
                else:
                    # Pagination: ?page=1&limit=10
                    try:
                        page = int(query_params.get("page", "1"))
                        limit = min(int(query_params.get("limit", "50")), 1000)  # Cap at 1000
                        start_idx = (page - 1) * limit
                        end_idx = start_idx + limit
                        tools = tools[start_idx:end_idx]
                    except (ValueError, TypeError):
                        # Invalid pagination params, use all tools
                        pass
                
                if view_mode == "full":
                    # Return original complex schemas for power users
                    tool_list = []
                    for tool in tools:
                        tool_list.append({
                            "name": tool.name,
                            "description": tool.description,
                            "inputSchema": tool.inputSchema
                        })
                    logger.info(f"[MCP HTTP] Returning {len(tool_list)} tools with full schemas")
                else:
                    # Return simplified schemas for mobile compatibility
                    tool_list = []
                    for tool in tools:
                        simplified_tool = {
                            "name": tool.name,
                            "description": tool.description[:200] + "..." if len(tool.description) > 200 else tool.description,
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "prompt": {
                                        "type": "string",
                                        "description": "Your request or question"
                                    }
                                },
                                "required": ["prompt"]
                            }
                        }
                        tool_list.append(simplified_tool)
                    logger.info(f"[MCP HTTP] Returning {len(tool_list)} tools with simplified schemas")
                
                # Create initial response
                response = {
                    "jsonrpc": "2.0",
                    "id": message_id,
                    "result": {"tools": tool_list}
                }
                
                # Check response size and chunk if necessary
                response_size = len(json.dumps(response))
                chunk_threshold = chunk_size_kb * 1024  # Convert to bytes
                
                if response_size > chunk_threshold:
                    logger.info(f"[MCP Chunking] Response size {response_size} bytes exceeds threshold {chunk_threshold} bytes, chunking with {chunk_size_kb}KB chunks...")
                    # Use the chunking method to split into multiple responses
                    for chunk_response in self._chunk_tools_response(tool_list, message_id, chunk_size_kb):
                        yield f"data: {json.dumps(chunk_response)}\n\n"
                    return  # Exit early since we've already yielded all chunks
                else:
                    logger.debug(f"[MCP HTTP] Response size {response_size} bytes is under threshold {chunk_threshold} bytes, sending single response")
            
            elif method == "tools/call":
                tool_name = params.get("name")
                arguments = params.get("arguments", {})
                
                # Convert simplified arguments to Zen MCP format
                if "prompt" in arguments and tool_name != "listmodels" and tool_name != "version":
                    # For most tools, map the prompt to appropriate fields
                    zen_arguments = {
                        "prompt": arguments["prompt"],
                        "model": "auto",  # Use auto model selection
                    }
                    # Add step workflow for workflow tools
                    if tool_name in ["thinkdeep", "planner", "consensus", "codereview", "precommit", "debug", "secaudit", "docgen", "analyze", "refactor", "tracer", "testgen"]:
                        zen_arguments.update({
                            "step": arguments["prompt"],
                            "step_number": 1,
                            "total_steps": 3,
                            "next_step_required": False,
                            "findings": "Starting analysis based on user request"
                        })
                else:
                    zen_arguments = arguments
                
                # Call the existing tool handler
                result = await handle_call_tool(tool_name, zen_arguments)
                response = {
                    "jsonrpc": "2.0",
                    "id": message_id,
                    "result": {
                        "content": [content.model_dump() for content in result]
                    }
                }
            
            elif method == "prompts/list":
                prompts = await handle_list_prompts()
                response = {
                    "jsonrpc": "2.0",
                    "id": message_id,
                    "result": {"prompts": [prompt.model_dump() for prompt in prompts]}
                }
            
            elif method == "prompts/get":
                prompt_name = params.get("name")
                prompt_args = params.get("arguments", {})
                prompt_result = await handle_get_prompt(prompt_name, prompt_args)
                response = {
                    "jsonrpc": "2.0",
                    "id": message_id,
                    "result": prompt_result.model_dump()
                }
            
            elif method == "ping":
                response = {
                    "jsonrpc": "2.0",
                    "id": message_id,
                    "result": {}
                }
            
            else:
                response = {
                    "jsonrpc": "2.0",
                    "id": message_id,
                    "error": {
                        "code": -32601,
                        "message": f"Method not found: {method}"
                    }
                }
            
            # Yield SSE response
            yield f"data: {json.dumps(response)}\n\n"
            
        except Exception as e:
            logger.error(f"Error handling MCP message: {e}", exc_info=True)
            error_response = {
                "jsonrpc": "2.0",
                "id": message_id,
                "error": {
                    "code": -32000,
                    "message": str(e)
                }
            }
            yield f"data: {json.dumps(error_response)}\n\n"
    
    async def _handle_initialize(self, session: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle MCP initialize request."""
        session["initialized"] = True
        
        # Import here to avoid circular imports
        from config import __version__
        
        return {
            "protocolVersion": "2025-03-26",
            "capabilities": {
                "tools": {},
                "prompts": {}
            },
            "serverInfo": {
                "name": "zen-mcp-server",
                "version": __version__
            }
        }
    
    async def start(self):
        """Start the HTTP server."""
        import uvicorn
        
        logger.info(f"Starting Zen MCP HTTP server on {self.host}:{self.port}")
        logger.info(f"MCP endpoint: http://{self.host}:{self.port}/mcp")
        logger.info(f"Health check: http://{self.host}:{self.port}/health")
        
        config = uvicorn.Config(
            self.app,
            host=self.host,
            port=self.port,
            log_level="info"
        )
        server = uvicorn.Server(config)
        await server.serve()

# Factory function for creating HTTP transport
def create_http_transport(host: str = "0.0.0.0", port: int = 8080) -> HTTPTransport:
    """Create and configure HTTP transport."""
    return HTTPTransport(host, port)