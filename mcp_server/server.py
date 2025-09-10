#!/usr/bin/env python
"""
WinDbg MCP Server

Main entry point for the MCP server that brokers between MCP clients and the
WinDbg extension over a named pipe.
"""
import argparse
import logging
import sys
from pathlib import Path
from typing import Dict

from fastmcp import FastMCP

# Make intra-package absolute imports like `from config import ...` resolve
sys.path.insert(0, str(Path(__file__).parent))

from config import LOG_FORMAT, load_environment_config, LOG_LEVEL, DEBUG_ENABLED
from tools import register_all_tools, get_tool_info
from core.server_initialization import ServerInitializer, InitializationConfig


def _configure_logging() -> logging.Logger:
    load_environment_config()
    logging.basicConfig(level=getattr(logging, LOG_LEVEL), format=LOG_FORMAT)
    logger = logging.getLogger(__name__)
    if DEBUG_ENABLED:
        logger.setLevel(logging.DEBUG)
        logging.getLogger("fastmcp").setLevel(logging.DEBUG)
    return logger


class WinDbgMCPServer:
    """Main WinDbg MCP Server class."""

    def __init__(self) -> None:
        self.mcp = FastMCP()
        self.initializer = ServerInitializer(InitializationConfig())
        self._initialized = False
        self.logger = logging.getLogger(__name__)

    def start(self) -> None:
        """Start the WinDbg MCP Server."""
        try:
            self._log_startup_banner()
            self.initializer.initialize()
            self._initialized = True
            self._register_tools()
            self.logger.info("MCP server ready. Listening on stdio.")
            self._run_server()
        except Exception as e:  # pragma: no cover - startup path
            self.logger.error(f"Failed to start server: {e}")
            raise

    def _log_startup_banner(self) -> None:
        tool_info: Dict = get_tool_info()
        self.logger.info("WinDbg MCP Server")
        self.logger.info("=" * 40)
        self.logger.info(f"Total tools: {tool_info['total_tools']}")
        self.logger.info("Tool categories:")
        for category, details in tool_info["categories"].items():
            self.logger.info(f"  {category}: {len(details['tools'])} tools")

    def _register_tools(self) -> None:
        self.logger.debug("Registering tools…")
        register_all_tools(self.mcp)

    def _run_server(self) -> None:
        try:
            self.mcp.run()
        except KeyboardInterrupt:
            pass


def main(argv: list[str] | None = None) -> int:
    _configure_logging()
    parser = argparse.ArgumentParser(prog="windbg-mcp", description="WinDbg MCP server")
    parser.add_argument("--list-tools", action="store_true", help="Print available tools and exit")
    parser.add_argument("--version", action="store_true", help="Print version and exit")
    args = parser.parse_args(argv)

    if args.version:
        from mcp_server import __version__
        print(__version__)
        return 0

    if args.list_tools:
        info = get_tool_info()
        print(f"Total tools: {info['total_tools']}")
        for cat, details in info["categories"].items():
            print(f"- {cat}: {', '.join(details['tools'])}")
        return 0

    server = WinDbgMCPServer()
    server.start()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
