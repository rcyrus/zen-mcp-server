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
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import StreamingResponse

# Import existing server handlers
from server import handle_call_tool, handle_get_prompt, handle_list_prompts, handle_list_tools

logger = logging.getLogger(__name__)

# No chunking needed - iOS Safari handles 200KB+ SSE events easily


class HTTPTransport:
    """HTTP transport implementation for MCP using FastAPI."""

    def __init__(self, host: str = "0.0.0.0", port: int = 8080):
        self.host = host
        self.port = port
        self.app = FastAPI(title="Zen MCP HTTP Server")
        self.sessions: dict[str, dict[str, Any]] = {}

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

    def _chunk_tools_response(self, tools: list, message_id: str, chunk_size_kb: int = 80) -> list:
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
        base_response = {"jsonrpc": "2.0", "id": message_id, "result": {"tools": []}}
        base_size = len(json.dumps(base_response))

        for tool in tools:
            # Handle both Tool objects and dictionaries
            if hasattr(tool, "name"):
                tool_data = {"name": tool.name, "description": tool.description, "inputSchema": tool.inputSchema}
            else:
                # tool is already a dictionary
                tool_data = tool
            tool_size = len(json.dumps(tool_data))

            # Check if adding this tool would exceed chunk size
            if current_size + tool_size + base_size > chunk_size_bytes and current_chunk:
                # Create chunk with current tools
                chunk_response = {"jsonrpc": "2.0", "id": message_id, "result": {"tools": current_chunk}}
                chunks.append(chunk_response)
                logger.debug(
                    f"[MCP Chunking] Created chunk with {len(current_chunk)} tools ({current_size + base_size} bytes)"
                )

                # Start new chunk
                current_chunk = [tool_data]
                current_size = tool_size
            else:
                # Add to current chunk
                current_chunk.append(tool_data)
                current_size += tool_size

        # Add final chunk if there are remaining tools
        if current_chunk:
            chunk_response = {"jsonrpc": "2.0", "id": message_id, "result": {"tools": current_chunk}}
            chunks.append(chunk_response)
            logger.debug(
                f"[MCP Chunking] Created final chunk with {len(current_chunk)} tools ({current_size + base_size} bytes)"
            )

        logger.info(f"[MCP Chunking] Split {len(tools)} tools into {len(chunks)} chunks (target: {chunk_size_kb}KB)")
        return chunks

    def _setup_routes(self):
        """Set up HTTP routes for MCP protocol."""

        @self.app.post("/mcp")
        async def handle_mcp_request(request: Request):
            """Handle MCP requests via streamable HTTP."""
            # Validate Accept header - client should accept both JSON and SSE
            accept_header = request.headers.get("Accept", "")
            if not accept_header or not any(
                content_type in accept_header for content_type in ["application/json", "text/event-stream", "*/*"]
            ):
                raise HTTPException(
                    status_code=406, detail="Not Acceptable: Client must accept application/json or text/event-stream"
                )

            # Detect mobile clients for appropriate schema optimization
            user_agent = request.headers.get("User-Agent", "").lower()
            is_mobile = any(
                mobile_ua in user_agent for mobile_ua in ["mobile", "iphone", "ipad", "android", "chatmcp", "dart"]
            )
            logger.debug(f"[MCP HTTP] User-Agent: {user_agent}, Mobile detected: {is_mobile}")

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

            # Determine if this should be a streaming response
            method = body.get("method")
            should_stream = method == "tools/call"  # Only stream tool calls

            if should_stream:
                # Create SSE streaming response for tool calls
                response_generator = self._handle_mcp_message_stream(session_id, session, body, is_mobile)
                headers = {
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "Mcp-Session-Id": session_id,
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                    "Access-Control-Allow-Headers": "*",
                }

                return StreamingResponse(response_generator, media_type="text/event-stream", headers=headers)
            else:
                # Return JSON response for protocol messages
                response_data = await self._handle_mcp_message_json(session_id, session, body, is_mobile)
                headers = {
                    "Mcp-Session-Id": session_id,
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                    "Access-Control-Allow-Headers": "*",
                }

                if response_data is None:
                    # No response needed (e.g., notifications)
                    # MCP spec requires 202 Accepted for notifications
                    return Response(status_code=202, headers=headers)

                return Response(content=json.dumps(response_data), media_type="application/json", headers=headers)

        @self.app.options("/mcp")
        async def handle_mcp_options():
            """Handle CORS preflight requests for MCP endpoint."""
            return Response(
                status_code=200,
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                    "Access-Control-Allow-Headers": "*",
                    "Access-Control-Max-Age": "86400",
                },
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
                sizes = [32 * 1024, 64 * 1024, 96 * 1024, 128 * 1024, 160 * 1024, 200 * 1024]
                for size in sizes:
                    payload = "x" * size
                    yield f"event: test\nid: {size}\ndata: {payload}\n\n"
                    await asyncio.sleep(1)  # 1 second between tests

            return StreamingResponse(
                test_generator(),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
            )

    async def _handle_mcp_message_json(
        self, session_id: str, session: dict[str, Any], message: dict[str, Any], is_mobile: bool = False
    ):
        """Handle individual MCP messages and return JSON responses."""
        method = message.get("method")
        message_id = message.get("id")
        params = message.get("params", {})

        logger.info(f"[MCP HTTP] JSON Request: {method} (id: {message_id})")

        try:
            if method == "initialize":
                result = await self._handle_initialize(session, params)
                return {"jsonrpc": "2.0", "id": message_id, "result": result}

            elif method == "notifications/initialized":
                # No response needed for notifications
                return None

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
                            "required": tool.inputSchema.get("required", []),
                        }

                        # Keep essential properties but simplify their definitions
                        if "properties" in tool.inputSchema:
                            props = tool.inputSchema["properties"]
                            for key, value in props.items():
                                simplified_schema["properties"][key] = simplify_property(value)

                        tool_list.append(
                            {"name": tool.name, "description": simplified_description, "inputSchema": simplified_schema}
                        )
                    else:
                        # Desktop: full schemas with complete functionality
                        tool_list.append(
                            {"name": tool.name, "description": tool.description, "inputSchema": tool.inputSchema}
                        )

                schema_type = "mobile-optimized" if is_mobile else "full"
                logger.info(f"[MCP HTTP] Returning {len(tool_list)} tools with {schema_type} schemas")

                # Create response
                response = {"jsonrpc": "2.0", "id": message_id, "result": {"tools": tool_list}}

                # Log response size for monitoring
                response_size = len(json.dumps(response))
                logger.info(f"[MCP HTTP] {schema_type.title()} response size: {response_size} bytes")

                return response

            elif method == "prompts/list":
                prompts = await handle_list_prompts()
                return {
                    "jsonrpc": "2.0",
                    "id": message_id,
                    "result": {"prompts": [prompt.model_dump() for prompt in prompts]},
                }

            elif method == "prompts/get":
                prompt_name = params.get("name")
                prompt_args = params.get("arguments", {})
                prompt_result = await handle_get_prompt(prompt_name, prompt_args)
                return {"jsonrpc": "2.0", "id": message_id, "result": prompt_result.model_dump()}

            elif method == "ping":
                return {"jsonrpc": "2.0", "id": message_id, "result": {}}

            else:
                return {
                    "jsonrpc": "2.0",
                    "id": message_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                }

        except Exception as e:
            logger.error(f"Error handling MCP message: {e}", exc_info=True)
            return {"jsonrpc": "2.0", "id": message_id, "error": {"code": -32000, "message": str(e)}}

    async def _handle_mcp_message_stream(
        self, session_id: str, session: dict[str, Any], message: dict[str, Any], is_mobile: bool = False
    ):
        """Handle tool calls and yield SSE responses."""
        method = message.get("method")
        message_id = message.get("id")
        params = message.get("params", {})

        logger.info(f"[MCP HTTP] Stream Request: {method} (id: {message_id})")

        try:
            if method == "tools/call":
                tool_name = params.get("name")
                arguments = params.get("arguments", {})

                # Call the tool handler with full arguments
                result = await handle_call_tool(tool_name, arguments)
                response = {
                    "jsonrpc": "2.0",
                    "id": message_id,
                    "result": {"content": [content.model_dump() for content in result]},
                }

                # Yield SSE response
                yield f"data: {json.dumps(response)}\n\n"
            else:
                # Fallback for unexpected streaming requests
                error_response = {
                    "jsonrpc": "2.0",
                    "id": message_id,
                    "error": {"code": -32601, "message": f"Streaming not supported for method: {method}"},
                }
                yield f"data: {json.dumps(error_response)}\n\n"

        except Exception as e:
            logger.error(f"Error handling streaming MCP message: {e}", exc_info=True)
            error_response = {"jsonrpc": "2.0", "id": message_id, "error": {"code": -32000, "message": str(e)}}
            yield f"data: {json.dumps(error_response)}\n\n"

    async def _handle_initialize(self, session: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        """Handle MCP initialize request."""
        session["initialized"] = True

        # Import here to avoid circular imports
        from config import __version__

        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {"listChanged": False}, "prompts": {"listChanged": False}},
            "serverInfo": {"name": "zen-mcp-server", "version": __version__},
        }

    async def start(self):
        """Start the HTTP server."""
        import uvicorn

        logger.info(f"Starting Zen MCP HTTP server on {self.host}:{self.port}")
        logger.info(f"MCP endpoint: http://{self.host}:{self.port}/mcp")
        logger.info(f"Health check: http://{self.host}:{self.port}/health")

        config = uvicorn.Config(self.app, host=self.host, port=self.port, log_level="info")
        server = uvicorn.Server(config)
        await server.serve()


# Factory function for creating HTTP transport
def create_http_transport(host: str = "0.0.0.0", port: int = 8080) -> HTTPTransport:
    """Create and configure HTTP transport."""
    return HTTPTransport(host, port)
