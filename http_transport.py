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

# No chunking needed - iOS Safari handles 200KB+ SSE events easily

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
            
            # Detect mobile clients for appropriate schema optimization
            user_agent = request.headers.get("User-Agent", "").lower()
            is_mobile = any(mobile_ua in user_agent for mobile_ua in [
                "mobile", "iphone", "ipad", "android", "chatmcp"
            ])
            logger.debug(f"[MCP HTTP] User-Agent: {user_agent}, Mobile detected: {is_mobile}")
            
            # Get or create session
            session_id = request.headers.get("Mcp-Session-Id")
            if not session_id or session_id not in self.sessions:
                session_id = str(uuid.uuid4())
                self.sessions[session_id] = {"initialized": False}
            
            session = self.sessions[session_id]
            
            # No query parameter processing needed anymore
            
            # Parse request body
            try:
                body = await request.json()
            except Exception as e:
                logger.error(f"Failed to parse request body: {e}")
                raise HTTPException(status_code=400, detail="Invalid JSON")
            
            # Create streaming response with compression support
            response_generator = self._handle_mcp_message(session_id, session, body, is_mobile)
            headers = {
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Mcp-Session-Id": session_id,
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
        
        @self.app.get("/sse-test")
        async def sse_size_test():
            """Test SSE size limits empirically."""
            async def test_generator():
                # Test various payload sizes to find the limit
                sizes = [32*1024, 64*1024, 96*1024, 128*1024, 160*1024, 200*1024]
                for size in sizes:
                    payload = "x" * size
                    yield f"event: test\nid: {size}\ndata: {payload}\n\n"
                    await asyncio.sleep(1)  # 1 second between tests
            
            return StreamingResponse(
                test_generator(),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
            )
    
    async def _handle_mcp_message(self, session_id: str, session: Dict[str, Any], message: Dict[str, Any], is_mobile: bool = False):
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
                
                # Build tool schemas optimized for client type
                tool_list = []
                for tool in tools:
                    if is_mobile:
                        # Mobile optimization: trim description and simplify schema
                        simplified_description = tool.description
                        if len(simplified_description) > 150:
                            simplified_description = simplified_description[:147] + "..."
                        
                        # Aggressively simplify input schema for mobile
                        def simplify_property(prop):
                            """Strip verbose parts from property definitions"""
                            if isinstance(prop, dict):
                                simplified = {"type": prop.get("type", "string")}
                                if "description" in prop and len(prop["description"]) < 50:
                                    simplified["description"] = prop["description"]
                                if "enum" in prop:
                                    simplified["enum"] = prop["enum"]
                                return simplified
                            return prop
                        
                        simplified_schema = {
                            "type": "object",
                            "properties": {},
                            "required": tool.inputSchema.get("required", [])
                        }
                        
                        # Keep essential properties but simplify their definitions
                        if "properties" in tool.inputSchema:
                            props = tool.inputSchema["properties"]
                            for key, value in props.items():
                                simplified_schema["properties"][key] = simplify_property(value)
                        
                        tool_list.append({
                            "name": tool.name,
                            "description": simplified_description,
                            "inputSchema": simplified_schema
                        })
                    else:
                        # Desktop: full schemas with complete functionality
                        tool_list.append({
                            "name": tool.name,
                            "description": tool.description,
                            "inputSchema": tool.inputSchema
                        })
                
                schema_type = "mobile-optimized" if is_mobile else "full"
                logger.info(f"[MCP HTTP] Returning {len(tool_list)} tools with {schema_type} schemas")
                
                # Create response
                response = {
                    "jsonrpc": "2.0",
                    "id": message_id,
                    "result": {"tools": tool_list}
                }
                
                # Log response size for monitoring
                response_size = len(json.dumps(response))
                logger.info(f"[MCP HTTP] {schema_type.title()} response size: {response_size} bytes")
                
                # Send single response - iOS Safari can handle 200KB+ easily
                # No chunking needed since our 108KB response is well under the limit
            
            elif method == "tools/call":
                tool_name = params.get("name")
                arguments = params.get("arguments", {})
                
                # Call the tool handler with full arguments (no simplified mapping needed)
                result = await handle_call_tool(tool_name, arguments)
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