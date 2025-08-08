#!/usr/bin/env python3
"""
Zen MCP HTTP Server

A standalone HTTP server that wraps the existing Zen MCP Server with HTTP transport.
This allows direct connections from ChatMCP iOS and other HTTP-based MCP clients
while maintaining full compatibility with the existing stdio-based server.
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Add the server directory to Python path for imports
sys.path.insert(0, str(Path(__file__).parent))

from http_transport import create_http_transport
from server import configure_providers

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


async def main():
    """Main entry point for the HTTP server."""
    parser = argparse.ArgumentParser(description="Zen MCP HTTP Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8080, help="Port to bind to")
    parser.add_argument("--env-file", help="Path to .env file")

    args = parser.parse_args()

    # Load environment file if specified
    if args.env_file:
        try:
            from dotenv import load_dotenv

            load_dotenv(args.env_file)
            logger.info(f"Loaded environment from {args.env_file}")
        except ImportError:
            logger.warning("python-dotenv not available, skipping .env file loading")

    # Configure providers (same as stdio server)
    try:
        configure_providers()
    except Exception as e:
        logger.error(f"Failed to configure providers: {e}")
        sys.exit(1)

    # Create and start HTTP transport
    transport = create_http_transport(args.host, args.port)

    try:
        await transport.start()
    except KeyboardInterrupt:
        logger.info("Server shutdown requested")
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
