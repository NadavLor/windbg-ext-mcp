# WinDbg-MCP Extension – LLM-Assisted Kernel Debugging

**WinDbg-MCP** is a security-focused toolchain that connects an LLM-based IDE (like Cursor) to WinDbg for real-time kernel debugging. The architecture consists of three parts: (1) a WinDbg extension (C++) loaded in a kernel debugging session; (2) an MCP server (Python/FastMCP) that bridges Cursor and WinDbg; and (3) the Cursor IDE (LLM client) that sends natural-language prompts. In practice, you attach WinDbg to a Windows 10 VM kernel (e.g. via `net:port,key`), set breakpoints, and then ask questions in Cursor such as _“What is the address of explorer.exe’s PEB?”_ or _“Show me the EPROCESS of explorer.exe.”_ The system invokes the corresponding MCP tool, runs WinDbg commands, and returns structured answers.

## Architecture

- **WinDbg Extension (C++):**  
  A DLL (`windbgmcpExt`) loaded into WinDbg (kernel mode) that initializes an MCP server over a named pipe (`\\.\pipe\windbgmcp`), registers command handlers, and exports custom commands. Notably it provides `help`, `objecttypes`, `hello`, and MCP control commands `!mcpstart`, `!mcpstop`, and `!mcpstatus`. When these commands are invoked in WinDbg, the extension starts/stops the server or displays status via the pipe server thread.

- **MCP Server (Python):**  
  A FastMCP-based HTTP/SSE server that registers asynchronous _tools_ for debugging tasks. Example tools include connection checks, session metadata, registers, memory dumps, module and process listings, PEB/TEB queries, stack traces, etc. Each tool executes WinDbg commands by sending JSON messages over the pipe to the extension. For instance, the `get_peb` tool runs `!peb` in WinDbg and returns the output. The server listens (by default) at `http://localhost:8000/sse`.

- **Cursor IDE (LLM client):**  
  Connects to the MCP server and uses the defined tools to answer queries. When the user prompts Cursor, the LLM selects a suitable tool (e.g. `display_type`, `list_modules`, `get_peb`) and invokes it via MCP. The JSON output is then formatted by the LLM into a human-readable response. This enables asking natural-language questions about the live kernel state.

## Installation

1. **WinDbg & Visual Studio:** Ensure you have WinDbg (Windows Debugger) and Visual Studio (C++ tools) installed on the host.  
2. **Build the Extension:** Open the `extension` project in Visual Studio (it’s a WinDbg extension sample project). Compile for 64-bit. This produces `windbgmcpExt.dll`. Copy it to the WinDbg extension folder or note its path.  
3. **WinDbg Setup:** In your WinDbg kernel session (connected to the target VM), load the extension DLL:  
   ```none
   .load C:\path\to\windbgmcpExt.dll
   ```  
   You should see a message like:  
   ```
   MCP server started on pipe: \\.\pipe\windbgmcp
   ```
4. **Python & MCP Server:** Install Python 3.8+ and navigate to `mcp_server`. Install requirements via the provided PowerShell script or manually:  
   ```powershell
   # PowerShell script
   mcp_server\scripts\start_mcp_server.ps1
   ```  
   Or:
   ```shell
   pip install -r mcp_server/requirements.txt
   ```
5. **Run the Server:** Start the MCP server by executing:
   ```shell
   cd mcp_server
   python server.py
   ```
   (An entry point `windbg-mcp` may also be available.) The server will list available tools and listen on the configured host/port.

## Setup and Usage

- **Cursor IDE:** Configure Cursor (or another LLM tool) to use the MCP server’s endpoint (default `http://localhost:8000/sse`). Verify the `check_connection` tool returns success.  
- **WinDbg Session:** Ensure WinDbg is connected to the target kernel. Use `.symfix`/`.reload` to load symbols as needed.  
- **Start/Stop MCP:** The extension auto-starts the MCP server on load. You can also control it in WinDbg:  
  ```none
  !mcpstart   ; start server if stopped  
  !mcpstop    ; stop server  
  !mcpstatus  ; show server status  
  ```  
- **Breakpoints:** Set breakpoints, e.g.,  
  ```none
  bp nt!NtOpenProcess; g
  ```  
- **Issuing Prompts:** In Cursor, type a natural-language question. The LLM will call the appropriate tool. For example:  
  > **User Prompt:** “What is the address of explorer.exe’s PEB?”  
  > **LLM Action:** Calls `get_peb` (executes `!peb`).  
  > **Response:** “Explorer.exe PEB is at `0xfffffa8001234000`.”

## Contribution Guidelines

- **Code Organization:** Components are separate: C++ extension, Python server, Cursor logic. Refactor each in isolation.  
- **Coding Style:** Use PEP8 for Python; follow Microsoft C++ conventions. Apply consistent formatting (e.g. `clang-format`, `black`).  
- **Documentation:** Maintain docstrings and comments.  
- **Testing:** Run existing tests (`pytest` or `unittest`). Add tests for new changes.  
- **Pull Requests:** Fork, branch, and submit PRs with clear descriptions.  
- **Modernization:** Remove redundancies, modularize long functions, use type hints and smart pointers, and add meaningful logging.

## Troubleshooting

- **Connection Issues:** Ensure MCP server is running and accessible at the configured host/port, and that `MCP_TRANSPORT` is set to `sse`.  
- **Symbol Loading:** Use `.symfix` and `.reload` in WinDbg to load symbols.  
- **Timeouts:** Increase `FASTMCP_TIMEOUT` if commands hang.  
- **Extension Status:** Use `!mcpstatus` in WinDbg to verify the extension’s server state.

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.
