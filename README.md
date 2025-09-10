# WinDbg‑ext‑MCP

WinDbg extension + Python MCP server. Lets MCP‑compatible clients (Cursor, Claude, VS Code + Cline/Roo) drive WinDbg with clean, validated commands. Kernel‑first; user‑mode works too.

## Contents
- Quick Start
- Architecture
- Usage Examples
- What’s Here
- Sanity Check
- Troubleshooting
- Configuration
- Tested With
- Notes

## Quick Start

Prereqs
- Windows 10/11
- WinDbg (Windows SDK “Debugging Tools for Windows”)
- Visual Studio Build Tools (C++)
- Python 3.10+ and Poetry 2.x

Build the extension (Developer PowerShell for VS):
```powershell
msbuild extension\windbgmcpExt.sln /p:Configuration=Release /p:Platform=x64
```

Load in WinDbg:
```text
.load C:\path\to\windbgmcpExt.dll
```

Install and run the MCP server (in root directory):
```powershell
poetry install
poetry run selftest
poetry run mcp --list-tools
poetry run mcp
```

## Architecture
```text
MCP Client (stdio)  <—>  Python MCP Server (stdio)  <—>  WinDbg Extension (named pipe)  <—>  WinDbg/Target
                             FastMCP                      \\.\pipe\windbgmcp                   Kernel/User
```
- The extension hosts a named‑pipe server and executes WinDbg commands safely.
- The Python server validates inputs, resolves timeouts, and exposes tools to MCP clients.

## Usage Examples

General (natural language prompts)
- "Show me all running processes in the kernel"
- "What's the current thread's stack trace?"
- "Analyze the memory at address 0x1000"
- "Help me understand this crash dump"
- "Set a breakpoint on nt!NtCreateFile and continue execution"
- "Step through the next 3 instructions and show me the registers"

Rootkit behavior (research‑only)
- "Hide explorer.exe using EPROCESS unlink and PspCidTable Unlink"
- "Make OneDrive.exe appear to have no open handles"
- "Make notepad.exe resistance to termination and kill attempts"
- "Install invisible system call hooks that dont modify SSDT"
- "Hide network connections from netstat while keeping them active"
- "Make files invisible to directory enumeration but accessible by direct path"

Note: These are for lawful, defensive research in controlled test labs only.

## Available Tools
- debug_session: session status and metadata
- connection_manager: connection health and resilience controls
- session_manager: capture/restore debugging context
- run_command: execute a WinDbg command with validation/timeout handling
- run_sequence: execute multiple commands in order
- breakpoint_and_continue: set a breakpoint and continue execution
- analyze_process: process enumeration, info, and context switching
- analyze_thread: thread info and stack traces
- analyze_memory: memory display, typed structures, searches
- analyze_kernel: kernel objects and system analysis
- performance_manager: optimization controls and performance report
- async_manager: parallel execution and async task stats
- troubleshoot: quick diagnostics and guidance
- get_help: list tools and usage tips
- test_windbg_communication: pipe connectivity test
- network_debugging_troubleshoot: network debugging issue checks

## What’s Here
- `extension/`: C++ WinDbg extension. Named pipe `\\.\pipe\windbgmcp`. Exports: `help`, `objecttypes`, `hello`, `mcpstart`, `mcpstop`, `mcpstatus`.
- `mcp_server/`: Python MCP server using FastMCP with modular tools (session, execution, analysis, performance, support).
- `install_client_config.py`: Optional helper to write MCP client configs (Cursor/Claude/VS Code).

## MCP Client Config (optional)
Writes/updates MCP client configuration so your client can discover and launch this server.

Supported clients
- Cursor, Claude Desktop, VS Code (Cline / Roo Code), Windsurf (Codeium)

Commands (run from repo root)
```powershell
# Dry run (preview changes)
python install_client_config.py --install --dry-run

# Install configs for detected clients
python install_client_config.py --install

# Uninstall (revert changes)
python install_client_config.py --uninstall

# Self-test only (no writes)
python install_client_config.py --test
```
Notes
- The script detects your OS and only touches clients it finds installed.
- It uses your current Python (`sys.executable`) to run the server and writes a stdio MCP config.
- Install mode runs a quick server import test first; fix any errors before proceeding.

## Sanity Check (no target required)
Self‑test stubs the transport and validates the protocol.
```powershell
poetry run selftest
```
Expected: “Selftest OK”.

## Troubleshooting
- Extension won’t load:
  - Path or arch mismatch. Use x64 WinDbg with the x64 DLL.
  - If linking fails, install Windows SDK Debugging Tools.
- Pipe connection errors:
  - The extension hosts the server. Ensure it’s started (`mcpstart`) and `\\.\pipe\windbgmcp` exists.
- Slow/spotty results:
  - Fix symbol paths, bump timeouts for remote/VM targets, and scope commands.

## Configuration
- `DEBUG=true` enables verbose logs in the Python server.
- Timeouts auto‑resolve per command type. See `mcp_server/config.py` for categories.

## Tested With
- Windows 11, MSVC v143, Windows SDK 10.0.22621.0
- Python 3.13, Poetry 2.1
- FastMCP 2.5.1, pywin32 310

## Notes
- Build the DLL, run the server, load the extension. If WinDbg can’t load, the path is wrong or the arch doesn’t match. Fix that first.
