# WinDbg-ext-MCP

**Vibe debug your Windows kernel!**

---

## 🚀 Overview

WinDbg-ext-MCP connects your LLM client (like Cursor, Claude, or VS Code) with WinDbg, enabling **real-time, AI assistant kernel debugging**. Write prompts in your AI coding assistant and receive instant, context-aware analysis and insights from your live kernel debugging session.

---

## ✨ Features

- **Natural Language Debugging:** Ask questions about kernel structures, processes, memory, and more in your language.
- **Live Session Integration:** Seamless operation with live kernel debugging sessions (breakpoints, process/thread context, etc.).
- **Comprehensive Toolset:** 25+ commands for memory inspection, process/thread analysis, and kernel tasks.
- **Context-Aware AI:** LLMs understand WinDbg terminology and kernel debugging workflows.

---

## 🏗️ Architecture

```plaintext
┌─────────────────────┐     ┌─────────────────────┐     ┌────────────────────────┐     ┌──────────────────────┐
│    LLM Client       │ <-> │     MCP Server      │ <-> │   WinDbg Extension     │ <-> │    Windows VM        │
│  (Cursor, Claude)   │     │   (Python/FastMCP)  │     │    (C++ DLL)           │     │  (Target Kernel)     │
└─────────────────────┘     └─────────────────────┘     └────────────────────────┘     └──────────────────────┘
```

- **LLM Client:** Any AI coding assistant that supports MCP (e.g., Cursor, Claude, VS Code with Cline/Roo Code)
- **MCP Server:** Python based Model Context Protocol server, translating LLM prompts to WinDbg commands.
- **WinDbg Extension:** C++ DLL loaded into WinDbg, executes commands and returns results.
- **Windows VM:** The target system for kernel debugging.

---

## ⚡ Quick Start

### Prerequisites

- [WinDbg (Windows Debugger)](https://developer.microsoft.com/en-us/windows/downloads/windows-sdk/)
- (Optional) Visual Studio with C++ build tools
- Python 3.10+ with [Poetry](https://python-poetry.org/)
- An MCP-compatible LLM client (Cursor, Claude Desktop, VS Code + Cline/Roo)
- Windows VM for kernel debugging

### Installation

1. **Get the WinDbg Extension DLL:**

   You have two options:

   - **Option 1: Download Pre-built DLL**
     - Go to the [Releases page](https://github.com/NadavLor/windbg-ext-mcp/releases) and download the latest `windbgmcpExt.dll` for your platform.
     - Place the DLL in a known directory (you’ll load it from this path in WinDbg).

   - **Option 2: Clone and Build from Source**
     ```sh
     git clone https://github.com/NadavLor/windbg-ext-mcp.git
     cd windbg-ext-mcp/extension
     msbuild /p:Configuration=Release /p:Platform=x64
     ```
     - The built DLL will be in `extension/x64/Release/windbgmcpExt.dll`.


2. **Install and start the MCP server:**
   ```sh
   cd ../mcp_server
   poetry install
   poetry run python server.py
   ```

3. **Load the extension in WinDbg:**
   ```sh
   .load C:\path\to\windbg-ext-mcp\extension\x64\Release\windbgmcpExt.dll
   ```

4. **Configure your LLM client:**
   ```sh
   python ../install_client_config.py
   ```

---

## 🛠️ Usage

### Start a Debugging Session

1. **Start your Windows 10 VM** in debugging mode  
   [Network Debugging Guide](https://learn.microsoft.com/en-us/windows-hardware/drivers/debugger/setting-up-network-debugging-of-a-virtual-machine-host)

2. **Connect WinDbg to the VM:**
   ```sh
   windbg -k net:port=<port>,key=<key>
   ```

3. **Load symbols:**
   ```sh
   .symfix
   .reload
   ```

4. **Load the extension:**
   ```sh
   .load C:\path\to\windbgmcpExt.dll
   ```

5. **Set breakpoints (optional):**
   ```sh
   bp nt!NtOpenProcess
   g
   ```

6. **Verify MCP connection:**
   ```sh
   !mcpstatus
   ```

---

### Example AI Queries

> Just type these questions in your LLM client:

- What process is currently running?
- Show me the stack trace of the current thread
- What's the address of explorer.exe's PEB?
- Display the EPROCESS structure at 0xffff8e0e481d7080
- List all running processes
- Show me the IDT
- Analyze the current exception

The LLM assistant will:
- Select the best MCP tool
- Run the corresponding WinDbg commands
- Format and present the results

---

## 🧰 Command Reference

| Command         | Description                         |
|-----------------|-------------------------------------|
| `!mcpstart`     | Start the MCP server                |
| `!mcpstop`      | Stop the MCP server                 |
| `!mcpstatus`    | Show MCP server status              |
| `!help`         | List available commands             |

---

### 🧑‍💻 Available MCP Tools

- **Session Info:** `check_connection`, `get_metadata`
- **Memory:** `display_memory`, `display_type`, `get_pte`
- **Process:** `list_processes`, `get_peb`, `switch_process`
- **Threads:** `list_threads`, `get_teb`, `switch_thread`, `get_stack_trace`
- **Kernel Objects:** `get_object`, `get_object_header`, `get_handle`
- **Helpers:** `search_symbols`, `set_breakpoint`, `run_command`
- **Advanced:** `get_all_thread_stacks`, `analyze_exception`, `troubleshoot_symbols`

---

## 💡 Additional Features

### Process Context Management

Seamlessly switch between processes in your session:

```text
Switch to explorer.exe process and show its PEB
```
The extension:
1. Saves current process context
2. Switches to explorer.exe
3. Retrieves PEB info
4. Restores original context

### Command Sequences

Run multiple commands at once:

```text
Run these commands: !process 0 0, !thread, !peb
```

---

## 📄 License

MIT License. See [LICENSE](LICENSE) for details.

---
