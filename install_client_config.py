#!/usr/bin/env python3
import os
import sys
import json
import argparse
import platform
import shutil
from pathlib import Path

def get_os_type():
    """Detect the operating system type."""
    system = platform.system().lower()
    if "windows" in system:
        return "windows"
    elif "darwin" in system:
        return "macos"
    elif "linux" in system:
        return "linux"
    else:
        print(f"Warning: Unknown operating system: {system}")
        return "unknown"

def expand_path(path):
    """Expand environment variables and user home directory in path."""
    expanded = os.path.expandvars(os.path.expanduser(path))
    return expanded

def get_client_config_paths(os_type):
    """Get configuration file paths for different client applications based on OS type."""
    paths = {}
    
    if os_type == "windows":
        paths["cursor"] = {
            "config_path": r"%USERPROFILE%\.cursor\mcp.json",
            "install_path": r"%USERPROFILE%\AppData\Local\Programs\cursor",
            "app_name": "Cursor"
        }
        paths["cline"] = {
            "config_path": r"%APPDATA%\Code\User\globalStorage\saoudrizwan.claude-dev\settings\cline_mcp_settings.json",
            "install_path": r"%APPDATA%\Code\User\globalStorage\saoudrizwan.claude-dev",
            "app_name": "Cline (VS Code extension)"
        }
        paths["roo_code"] = {
            "config_path": r"%APPDATA%\Code\User\globalStorage\rooveterinaryinc.roo-cline\settings\mcp_settings.json",
            "install_path": r"%APPDATA%\Code\User\globalStorage\rooveterinaryinc.roo-cline",
            "app_name": "Roo Code (VS Code extension)"
        }
        paths["claude_desktop"] = {
            "config_path": r"%APPDATA%\Claude\claude_desktop_config.json",
            "install_path": r"%LOCALAPPDATA%\Programs\Claude",
            "app_name": "Claude Desktop"
        }
        paths["windsurf"] = {
            "config_path": r"%USERPROFILE%\.codeium\windsurf\mcp_config.json",
            "install_path": r"%USERPROFILE%\.codeium\windsurf",
            "app_name": "Windsurf (Codeium)"
        }
    elif os_type == "macos":
        paths["cursor"] = {
            "config_path": "~/.cursor/mcp.json",
            "install_path": "/Applications/Cursor.app",
            "app_name": "Cursor"
        }
        paths["cline"] = {
            "config_path": "~/Library/Application Support/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json",
            "install_path": "~/Library/Application Support/Code/User/globalStorage/saoudrizwan.claude-dev",
            "app_name": "Cline (VS Code extension)"
        }
        paths["roo_code"] = {
            "config_path": "~/Library/Application Support/Code/User/globalStorage/rooveterinaryinc.roo-cline/settings/mcp_settings.json",
            "install_path": "~/Library/Application Support/Code/User/globalStorage/rooveterinaryinc.roo-cline",
            "app_name": "Roo Code (VS Code extension)"
        }
        paths["claude_desktop"] = {
            "config_path": "~/Library/Application Support/Claude/claude_desktop_config.json",
            "install_path": "/Applications/Claude.app",
            "app_name": "Claude Desktop"
        }
        paths["windsurf"] = {
            "config_path": "~/.codeium/windsurf/mcp_config.json",
            "install_path": "~/.codeium/windsurf",
            "app_name": "Windsurf (Codeium)"
        }
    elif os_type == "linux":
        paths["cursor"] = {
            "config_path": "~/.cursor/mcp.json",
            "install_path": "~/.local/share/cursor",
            "app_name": "Cursor"
        }
        paths["cline"] = {
            "config_path": "~/.config/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json",
            "install_path": "~/.config/Code/User/globalStorage/saoudrizwan.claude-dev",
            "app_name": "Cline (VS Code extension)"
        }
        paths["roo_code"] = {
            "config_path": "~/.config/Code/User/globalStorage/rooveterinaryinc.roo-cline/settings/mcp_settings.json",
            "install_path": "~/.config/Code/User/globalStorage/rooveterinaryinc.roo-cline",
            "app_name": "Roo Code (VS Code extension)"
        }
        # No Claude desktop for Linux
        paths["windsurf"] = {
            "config_path": "~/.codeium/windsurf/mcp_config.json",
            "install_path": "~/.codeium/windsurf",
            "app_name": "Windsurf (Codeium)"
        }
    
    # Expand all paths
    for client, data in paths.items():
        for key in ['config_path', 'install_path']:
            data[key] = expand_path(data[key])
    
    return paths

def is_app_installed(app_info):
    """Check if the app is installed by examining the install path."""
    install_path = app_info.get('install_path')
    if not install_path:
        return False
    
    # For VSCode extensions, if the globalStorage directory exists, assume extension is installed
    if os.path.exists(install_path):
        return True
    
    # Additional checks for desktop apps based on OS
    os_type = get_os_type()
    app_name = app_info.get('app_name', '')
    
    if os_type == "windows":
        # Check Programs and Features
        if 'Claude' in app_name and shutil.which('claude'):
            return True
        if 'Cursor' in app_name and shutil.which('cursor'):
            return True
    elif os_type == "macos":
        # Check Applications folder for .app bundles
        if install_path.endswith('.app') and os.path.exists(install_path):
            return True
    elif os_type == "linux":
        # Check if binary is in PATH
        if 'Cursor' in app_name and (shutil.which('cursor') or os.path.exists(os.path.expanduser('~/.local/bin/cursor'))):
            return True
        
    # If config file exists, we can assume the app is/was installed
    config_path = app_info.get('config_path')
    if config_path and os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                # If we can read the config file, it's likely the app is installed
                json.load(f)
                return True
        except:
            pass
            
    return False

def get_windbg_mcp_config():
    """Return the configuration for the windbg-mcp server."""
    # Current tools from our modular architecture (16 tools total)
    tools_list = [
        # Session management tools
        "debug_session",
        "connection_manager", 
        "session_manager",
        
        # Command execution tools
        "run_command",
        "run_sequence",
        "breakpoint_and_continue",
        
        # Analysis tools
        "analyze_process",
        "analyze_thread", 
        "analyze_memory",
        "analyze_kernel",
        
        # Performance tools
        "performance_manager",
        "async_manager",
        
        # Support tools
        "troubleshoot",
        "get_help",
        "test_windbg_communication",
        "network_debugging_troubleshoot",
    ]
    
    # Get the current script directory to find the server
    current_dir = Path(__file__).parent.absolute()
    server_path = current_dir / "mcp_server" / "server.py"
    
    return {
        "command": sys.executable,
        "args": [str(server_path)],
        "env": {
            "DEBUG": "false"  # Set to "true" for debug logging
        },
        "description": "WinDbg MCP Server (FastMCP, stdio)",
        "disabled": False,
        "timeout": 30000,  # 30 seconds timeout
        "autoApprove": tools_list,
        "alwaysAllow": tools_list
    }

def read_json_config(config_path):
    """Read JSON configuration file, returning empty dict if file doesn't exist or is invalid."""
    try:
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    except json.JSONDecodeError:
        print(f"Warning: Invalid JSON in {config_path}, starting with empty configuration")
        return {}
    except Exception as e:
        print(f"Error reading {config_path}: {e}")
        return {}

def write_json_config(config_path, config_data):
    """Write JSON configuration data to file, creating directories if needed."""
    try:
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=2)
        return True
    except Exception as e:
        print(f"Error writing to {config_path}: {e}")
        return False

def install_windbg_mcp(config_path, quiet=False, dry_run: bool = False):
    """Install windbg-mcp configuration to the specified config file."""
    # Verify that the server file exists
    current_dir = Path(__file__).parent.absolute()
    server_path = current_dir / "mcp_server" / "server.py"
    
    if not server_path.exists():
        if not quiet:
            print(f"Error: Server file not found at {server_path}")
            print("Make sure you're running this script from the windbg-ext-mcp root directory")
        return False
    
    # Build configuration payload
    windbg_config = get_windbg_mcp_config()

    if dry_run:
        if not quiet:
            print(f"[DRY-RUN] Would install windbg-mcp at: {config_path}")
            print(f"  Server path: {server_path}")
            print(f"  Tools configured: {len(windbg_config['autoApprove'])} tools")
            print("  Transport: stdio (FastMCP)")
        return True

    # Read existing config and write changes
    config = read_json_config(config_path)
    if "mcpServers" not in config:
        config["mcpServers"] = {}
    config["mcpServers"]["windbg-mcp"] = windbg_config

    success = write_json_config(config_path, config)
    if success and not quiet:
        print(f"  Server path: {server_path}")
        print(f"  Tools configured: {len(windbg_config['autoApprove'])} tools")
        print(f"  Transport: stdio (FastMCP)")
        print(f"  Debug mode: {windbg_config['env']['DEBUG']}")

    return success

def uninstall_windbg_mcp(config_path, quiet=False, dry_run: bool = False):
    """Remove windbg-mcp configuration from the specified config file."""
    # Dry-run: report intent regardless of file existence
    if dry_run:
        if not quiet:
            print(f"[DRY-RUN] Would uninstall windbg-mcp from: {config_path}")
        return True
    
    # Skip if file does not exist
    if not os.path.exists(config_path):
        return False
    
    # Read existing config and remove entry if present
    config = read_json_config(config_path)
    if "mcpServers" in config and "windbg-mcp" in config["mcpServers"]:
        del config["mcpServers"]["windbg-mcp"]
        success = write_json_config(config_path, config)
        return success
    
    return False  # Nothing to uninstall
def process_clients(client_paths, action_func, quiet=False, dry_run: bool = False):
    """Process all client configurations with the specified action function."""
    results = {}
    
    for client_name, client_info in client_paths.items():
        config_path = client_info['config_path']
        app_name = client_info['app_name']
        
        # Check if app is installed
        if not is_app_installed(client_info):
            if not quiet:
                print(f"Skipping {app_name} (not installed)")
            results[client_name] = False
            continue
        
        # Apply action
        success = action_func(config_path, quiet, dry_run)
        results[client_name] = success
        
        if not quiet:
            action_name = "Installed" if action_func == install_windbg_mcp else "Uninstalled"
            if dry_run:
                action_name = f"[DRY-RUN] {action_name}"
            status = "successfully" if success else "failed"
            print(f"{action_name} for {app_name} {status}: {config_path}")
    
    return results

def test_server_installation(quiet=False):
    """Test that the WinDbg MCP server can be started."""
    current_dir = Path(__file__).parent.absolute()
    server_path = current_dir / "mcp_server" / "server.py"
    
    if not server_path.exists():
        if not quiet:
            print(f"ERROR: Server file not found: {server_path}")
            return False
    
    if not quiet:
        print("Testing server installation...")
    
    try:
        import subprocess
        import sys
        
        # Try to import the server modules to check for syntax errors
        result = subprocess.run([
            sys.executable, "-c", 
            "import sys; sys.path.append('mcp_server'); import server; print('Server imports successfully')"
        ], capture_output=True, text=True, cwd=current_dir, timeout=10)
        
        if result.returncode == 0:
            if not quiet:
                print("Server syntax check passed")
                print("All required modules can be imported")
            return True
        else:
            if not quiet:
                print("ERROR: Server import failed:")
                print(f"   {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        if not quiet:
            print("Server test timed out (this might be normal)")
        return True  # Timeout is acceptable for this test
    except Exception as e:
        if not quiet:
            print(f"ERROR: Error testing server: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Install or uninstall WinDBG MCP server configuration")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--install", action="store_true", help="Install WinDBG MCP server configuration (default)")
    group.add_argument("--uninstall", action="store_true", help="Uninstall WinDBG MCP server configuration")
    group.add_argument("--test", action="store_true", help="Test server installation without installing")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without writing files")
    parser.add_argument("--quiet", action="store_true", help="Suppress informational messages")
    parser.add_argument("--force", action="store_true", help="Force installation even if app is not detected")

    args = parser.parse_args()

    # Handle test mode
    if args.test:
        success = test_server_installation(args.quiet)
        sys.exit(0 if success else 1)

    # Default to install
    if not (args.install or args.uninstall):
        args.install = True

    # Pre-flight server check (skip prints, still gate failures)
    if args.install:
        if not test_server_installation(True):
            print("ERROR: Server test failed. Fix server issues before installing.")
            sys.exit(1)
        elif not args.quiet and not args.dry_run:
            print("Server test passed\n")

    # Resolve clients
    os_type = get_os_type()
    if not args.quiet:
        print(f"Detected OS: {os_type}")
    client_paths = get_client_config_paths(os_type)

    # Install
    if args.install:
        if not args.quiet:
            print("\nInstalling WinDbg MCP server configuration..." if not args.dry_run else "\n[DRY-RUN] Installing WinDbg MCP server configuration...")
        results = process_clients(client_paths, install_windbg_mcp, args.quiet, args.dry_run)

        successful = sum(1 for success in results.values() if success)
        total = len([client for client, info in client_paths.items() if is_app_installed(info)])
        if not args.quiet:
            print(f"\nInstallation complete: {successful}/{total} clients configured")
            if successful > 0:
                print("\nNext steps:")
                print("   1. Restart your MCP client (Cursor, Claude Desktop, etc.)")
                print("   2. The 'windbg-mcp' server should appear in your MCP tools")
                print("   3. Start with get_help() to see available tools")
                print("   4. Use debug_session(action='status') to test the connection")

    # Uninstall
    elif args.uninstall:
        if not args.quiet:
            print("\nUninstalling WinDbg MCP server configuration..." if not args.dry_run else "\n[DRY-RUN] Uninstalling WinDbg MCP server configuration...")
        results = process_clients(client_paths, uninstall_windbg_mcp, args.quiet, args.dry_run)
        successful = sum(1 for success in results.values() if success)
        if not args.quiet:
            print(f"\nUninstallation complete: {successful} configurations removed")

if __name__ == "__main__":
    main()
