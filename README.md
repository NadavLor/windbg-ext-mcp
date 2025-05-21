# WinDbg MCP Extension

A WinDbg extension that allows AI tools to drive WinDbg during debugging via the Model Context Protocol (MCP). This extension bridges WinDbg's powerful debugging capabilities with AI-powered assistance.

## Overview

The WinDbg MCP Extension enables AI tools to interact directly with WinDbg by:

- Executing WinDbg commands and analyzing their output
- Navigating memory structures and processes
- Examining loaded modules and symbols
- Setting breakpoints and analyzing memory regions
- Providing intelligent debugging assistance

## Project Structure

```
windbg_alpha/
├── extension/              # C++ WinDbg extension
│   ├── include/            # External header files
│   ├── src/                # Source files
│   │   ├── command/        # Command handlers
│   │   ├── ipc/            # Named pipe communication
│   │   └── utils/          # Utilities and helpers
│   └── .vs/                # Visual Studio configuration
├── mcp_server/             # Python MCP server
│   ├── commands/           # Command implementation modules
│   ├── lib/                # Reusable components
│   └── tests/              # Test files
├── docs/                   # Documentation
│   └── examples/           # Usage examples
└── tools/                  # Development tools & utilities
```

## Requirements

### For the WinDbg Extension:
- Windows 10 or later
- Visual Studio 2019 or later with C++ development tools
- WinDbg Preview or WinDbg 10.0 or later
- Windows SDK 10.0.19041.0 or later

### For the MCP Server:
- Python 3.8 or later
- Windows 10 or later
- Required Python packages (listed in mcp_server/requirements.txt)

## Building the Extension

1. Open `extension/windbgmcpExt.sln` in Visual Studio
2. Select the desired build configuration (Debug/Release, x86/x64)
3. Build the solution

## Setting Up the MCP Server

1. Make sure Python 3.8 or later is installed
2. Install required packages:
   ```
   cd mcp_server
   pip install -r requirements.txt
   ```
3. Start the server:
   ```
   python server.py
   ```

The server will be available at `http://localhost:8000/sse` by default.

## Using with WinDbg

1. Start WinDbg and attach to a debugging target (process or kernel)
2. Load the extension:
   ```
   .load [path-to-extension]\windbgmcpExt.dll
   ```
3. The extension will establish a named pipe connection that the MCP server can connect to

## Connecting to AI Tools

The WinDbg MCP Extension implements the Model Context Protocol, which allows it to be used with any MCP-compatible AI tool:

1. Start the WinDbg MCP Server as described above
2. In your AI tool (like Cursor IDE), configure an MCP server with the URL: `http://localhost:8000/sse`
3. You can now use the AI tool to send commands to WinDbg

## Available Commands

The extension provides access to the following functionality:

### Core Functionality
- Execute any WinDbg command and capture the output
- Display type information and memory contents
- List modules and processes
- Navigate threads and processes

### Specialized Commands with Enhanced Handling

| Command | Description |
|---------|-------------|
| `!process <addr> <flags>` | Display information about processes |
| `!dlls -p <addr>` | Display loaded modules for a process |
| `!address [-f:PROTECTION]` | Display memory regions with optional protection filtering |
| `!handle [addr] [flags]` | Display handle information |
| `!for_each_module <command>` | Execute a command for each loaded module |
| `switch_process <addr> [save_previous]` | Switch to specified process and optionally save previous context |
| `restore_process_context` | Restore the previously saved process context |

## Troubleshooting

### Common Issues

1. **Connection Errors**:
   - Ensure WinDbg is running with the extension loaded
   - Check that the MCP server is running
   - Verify there are no firewalls blocking the connection

2. **Command Execution Errors**:
   - Some commands require specific context (user mode vs kernel mode)
   - Certain commands may time out if processing large amounts of data
   - Some extension commands may require additional extensions to be loaded

3. **Output Handling Issues**:
   - Large command outputs may be truncated (maximum size: 1MB)
   - Some commands produce special formatting that may not be parsed correctly

### Logs and Diagnostics

- Enable debug logging in the MCP server by setting the `DEBUG=true` environment variable
- Review the console output of the MCP server for error messages and connection status

### Process Context Management

The extension includes intelligent process context management:

- All commands that change process context will automatically save and restore the original context
- The `switch_process` command includes an option to save the previous context (`save_previous=True` by default)
- Use `restore_process_context` to switch back to a previously saved process context
- Commands that modify process context in specialized handlers (`!process`, `!dlls`, `!handle`) all maintain context integrity
- Thread-safe implementation ensures reliable context switching even in multi-threaded scenarios

This prevents the common issue of commands changing debugging context and not restoring it, which can lead to confusing results in subsequent commands.

### Command Validation

The extension includes a comprehensive command validation system:

- All commands are validated before execution to prevent errors and security issues
- Potentially dangerous commands (like quit, kill, detach) are blocked
- Parameters are validated for correct format and range
- Long-running or resource-intensive commands are identified and handled appropriately
- Specific command handlers perform additional validation for their parameters

This validation system provides several benefits:
- Prevents accidental termination of debugging sessions
- Reduces errors from malformed commands
- Provides more helpful error messages when commands fail
- Protects against potentially harmful operations
- Improves overall stability of debugging sessions

### Timeouts and Performance

Long-running commands have increased timeouts:
- Standard commands: 30 seconds
- Module listing: 60 seconds
- Handle enumeration: 120 seconds

Commands with potentially very large outputs (like `!handle` with the 'f' flag) include automatic pagination to prevent overwhelming the client.

## Advanced Usage

### Custom Command Handlers

The MCP server includes specialized handlers for common debugging scenarios:

- Process and thread navigation
- Memory region analysis
- Module enumeration
- Handle inspection
- Symbol resolution

## License

This project is distributed under the MIT License.

## Contributing

Contributions are welcome! Please feel free to submit pull requests or open issues to improve the extension.

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## Credits

This project was built with insights from WinDbg developers, Windows Internals experts, and the AI debugging community. 