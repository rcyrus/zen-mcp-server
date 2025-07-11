"""
HTTP Transport for Zen MCP Server

This module implements HTTP transport support alongside the existing stdio transport.
It provides a FastAPI-based HTTP server that implements the MCP streamable HTTP protocol
to enable direct connections from ChatMCP iOS and other HTTP-based MCP clients.
"""

import asyncio
import json
import logging
import uuid
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

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
        
        self._setup_routes()
    
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
            
            # Parse request body
            try:
                body = await request.json()
            except Exception as e:
                logger.error(f"Failed to parse request body: {e}")
                raise HTTPException(status_code=400, detail="Invalid JSON")
            
            # Create streaming response
            response_generator = self._handle_mcp_message(session_id, session, body)
            return StreamingResponse(
                response_generator,
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "Mcp-Session-Id": session_id,
                }
            )
        
        @self.app.get("/health")
        async def health_check():
            """Health check endpoint."""
            return {"status": "ok", "server": "zen-mcp-http"}
    
    async def _handle_mcp_message(self, session_id: str, session: Dict[str, Any], message: Dict[str, Any]):
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
                # Simplify tools for ChatMCP iOS compatibility
                simplified_tools = []
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
                    simplified_tools.append(simplified_tool)
                
                response = {
                    "jsonrpc": "2.0",
                    "id": message_id,
                    "result": {"tools": simplified_tools}
                }
            
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