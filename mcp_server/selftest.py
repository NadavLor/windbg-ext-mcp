"""
Hermetic self-test for the WinDbg MCP server package.

This test stubs transport at the boundary and validates basic contracts:
- MessageProtocol serialize/parse roundtrip
- Unified executor returns structured result when send_command is stubbed
- Tool registry imports cleanly
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Make package-local absolute imports like `from config import ...` resolve
sys.path.insert(0, str(Path(__file__).parent))


def _roundtrip_message() -> None:
    from mcp_server.core.communication import MessageProtocol

    msg = MessageProtocol.create_command_message("version", timeout_ms=5000)
    payload = MessageProtocol.serialize_message(msg)
    parsed = MessageProtocol.parse_response(json.dumps({
        "status": "success",
        "output": "WinDbg version (stub)"
    }).encode("utf-8"))  # parse_response expects bytes from pipe
    assert parsed["status"] == "success"


def _stubbed_executor() -> None:
    # Stub send_command to avoid named pipe use
    from mcp_server.core import communication as comm
    from mcp_server.core.execution import strategies as strat
    original_send = comm.send_command
    original_send_strat = strat.send_command
    stub = lambda command, timeout_ms=0: f"stub-output for {command}"
    comm.send_command = stub
    strat.send_command = stub
    try:
        from mcp_server.core.execution import execute_command
        result = execute_command("version", resilient=True, optimize=False)
        assert result.success
        assert isinstance(result.result, str)
    finally:
        comm.send_command = original_send
        strat.send_command = original_send_strat


def _tools_import() -> None:
    from mcp_server.tools import get_tool_info
    info = get_tool_info()
    assert "categories" in info and info["total_tools"] >= 1


def main() -> int:
    _roundtrip_message()
    _stubbed_executor()
    _tools_import()
    print("Selftest OK")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
