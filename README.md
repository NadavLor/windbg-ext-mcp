# WinDbg-ext-MCP

**Vibe kernel debugging with LLMs and WinDbg!**

WinDbg-ext-MCP connects your favorite LLM client (like Cursor) with WinDbg, enabling natural language, AI-assisted kernel debugging. Write prompts in your AI coding assistant and get real-time insights from the Windows kernel being debugged in WinDbg.

---

## Key Features

- 🔍 **Natural Language Kernel Debugging**: Ask questions in plain English about kernel structures, processes, memory, and more.
- 🔄 **Real-time Integration**: Works with live kernel debugging sessions, including breakpoints.
- 🛠 **Comprehensive Toolset**: 25+ specialized debugging tools for memory inspection, process analysis, and more.
- 🧠 **LLM Context Awareness**: Your AI assistant understands kernel debugging concepts and WinDbg commands.

---

## Architecture

The system consists of four main components:

```
┌──────────────────────┐     ┌────────────────────────┐     ┌────────────────────────────┐     ┌────────────────────────────┐
│  LLM Client          │<--->│  MCP Server            │<--->│  WinDbg                    │<--->│  Windows 10 VM             │
│  (e.g. Cursor)       │     │  (Python/FastMCP)      │     │  Extension (C++)           │     │  (Target Kernel)           │
└──────────────────────┘     └────────────────────────┘     └────────────────────────────┘     └────────────────────────────┘
```

- **LLM Client**: Any AI coding assistant that supports MCP (e.g., Cursor, Claude Desktop, VS Code with Cline/Roo Code).
- **MCP Server**: Python-based Model Context Protocol server that translates LLM requests into WinDbg commands.
- **WinDbg Extension**: C++ extension loaded into WinDbg that executes commands and returns results.
- **Windows 10 VM**: The target kernel being debugged.

---

## Quick Start

### Prerequisites

- [WinDbg (Windows Debugger)](https://developer.microsoft.com/en-us/windows/downloads/windows-sdk/)
- Visual Studio with C++ tools
- Python 3.10+ with [Poetry](https://python-poetry.org/)
- An MCP-compatible LLM client (Cursor, Claude Desktop, VS Code with Cline/Roo Code, etc.)
- Windows VM for target debugging

### Installation

1. **Clone the repository and build the WinDbg Extension:**
    ```powershell
    git clone https://github.com/yourusername/windbg-ext-mcp.git
    cd windbg-ext-mcp/extension
    msbuild /p:Configuration=Release /p:Platform=x64
    ```

2. **Install and run the MCP Server:**
    ```powershell
    cd ../mcp_server
    poetry install
    poetry run python server.py
    ```

3. **Load the Extension in WinDbg:**
    ```text
    .load C:\\path\\to\\windbg-ext-mcp\\extension\\x64\\Release\\windbgmcpExt.dll
    ```

4. **Configure your LLM client:**
    ```powershell
    python ../install_client_config.py
    ```

---

## Usage

See the [Usage Guide](#usage-guide) below for detailed instructions and examples.

---

## Usage Guide

### Setting Up a Debugging Session

1. **Start your Windows 10 VM** in debugging mode 
   - Guide on how to do it: https://learn.microsoft.com/en-us/windows-hardware/drivers/debugger/setting-up-network-debugging-of-a-virtual-machine-host
2. **Connect WinDbg** to the VM kernel:
   ```
   windbg -k net:port=<port>,key=<key>
   ```
3. **Load symbols** in WinDbg:
   ```
   .symfix
   .reload
   ```
4. **Load the WinDbg-MCP extension**:
   ```
   .load C:\path\to\windbgmcpExt.dll
   ```
5. **Set breakpoints** as needed, or manually break into the debugger:
   ```
   bp nt!NtOpenProcess
   g
   ```
6. **Verify MCP connection** in WinDbg:
   ```
   !mcpstatus
   ```

### Example Workflow

1. **Break into the kernel** (hit a breakpoint or press Ctrl+Break)
2. **Ask questions in your LLM client**:

   - "What process is currently running?"
   - "Show me the stack trace of the current thread"
   - "What's the address of explorer.exe's PEB?"
   - "Display the EPROCESS structure at 0xffff8e0e481d7080"
   - "List all running processes"
   - "Show me the IDT"
   - "Analyze the current exception"

3. **Your LLM assistant** will:
   - Select the appropriate MCP tool
   - Execute the necessary WinDbg commands
   - Format and return the results

### Available Commands in WinDbg

- `!mcpstart` - Start the MCP server if stopped
- `!mcpstop` - Stop the MCP server
- `!mcpstatus` - Show MCP server status
- `!help` - Display available commands

## Available MCP Tools

WinDbg-MCP provides 25+ specialized debugging tools, including:

- **Session Information**: `check_connection`, `get_metadata`
- **Memory Analysis**: `display_memory`, `display_type`, `get_pte`
- **Process Management**: `list_processes`, `get_peb`, `switch_process`
- **Thread Analysis**: `list_threads`, `get_teb`, `switch_thread`, `get_stack_trace`
- **Kernel Objects**: `get_object`, `get_object_header`, `get_handle`
- **Debugging Helpers**: `search_symbols`, `set_breakpoint`, `run_command`
- **Advanced Analysis**: `get_all_thread_stacks`, `analyze_exception`, `troubleshoot_symbols`

## Troubleshooting

- **Connection Issues**: Ensure the MCP server is running and WinDbg extension is loaded
- **Symbol Problems**: Use `!troubleshoot_symbols` or manually run `.symfix` and `.reload`
- **Command Timeouts**: For long-running commands, increase the timeout in the MCP server config
- **Extension Not Loading**: Check path, build configuration, and WinDbg architecture match

## Advanced Features

### Process Context Management

WinDbg-MCP maintains context when switching between processes:

```
# In your client:
"Switch to explorer.exe process and show its PEB"
```

The extension will:
1. Save the current process context
2. Switch to explorer.exe
3. Get the PEB information
4. Restore the original process context

### Command Sequences

Run multiple commands in sequence:

```
# In your client:
"Run these commands: !process 0 0, !thread, !peb"
```

## Contributing

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
