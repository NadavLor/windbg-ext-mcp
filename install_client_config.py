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
        if 'Cursor' in app_name and (shutil.which('cursor') or os.path.exists('~/.local/bin/cursor')):
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
    tools_list = [
        "check_connection", "get_metadata", "get_current_address", "list_modules",
        "run_command", "display_type", "display_memory", "set_breakpoint",
        "list_processes", "get_peb", "get_teb", "switch_process", "list_threads",
        "switch_thread", "get_interrupt", "get_idt", "get_object",
        "get_object_header", "get_pte", "get_handle", "search_symbols",
        "get_stack_trace"
    ]
    
    return {
        "transport": "sse",
        "url": "http://localhost:8000/sse",
        "description": "WinDBG Model Context Protocol integration for kernel debugging analysis",
        "timeout": 3800,
        "disabled": False,
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

def install_windbg_mcp(config_path, quiet=False):
    """Install windbg-mcp configuration to the specified config file."""
    # Read existing config
    config = read_json_config(config_path)
    
    # Ensure mcpServers key exists
    if "mcpServers" not in config:
        config["mcpServers"] = {}
    
    # Add or update windbg-mcp entry
    config["mcpServers"]["windbg-mcp"] = get_windbg_mcp_config()
    
    # Write updated config
    success = write_json_config(config_path, config)
    return success

def uninstall_windbg_mcp(config_path, quiet=False):
    """Remove windbg-mcp configuration from the specified config file."""
    # Skip if file doesn't exist
    if not os.path.exists(config_path):
        return False
    
    # Read existing config
    config = read_json_config(config_path)
    
    # Remove windbg-mcp entry if it exists
    if "mcpServers" in config and "windbg-mcp" in config["mcpServers"]:
        del config["mcpServers"]["windbg-mcp"]
        
        # Write updated config
        success = write_json_config(config_path, config)
        return success
    
    return False  # Nothing to uninstall

def process_clients(client_paths, action_func, quiet=False):
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
        success = action_func(config_path, quiet)
        results[client_name] = success
        
        if not quiet:
            action_name = "Installed" if action_func == install_windbg_mcp else "Uninstalled"
            status = "successfully" if success else "failed"
            print(f"{action_name} for {app_name} {status}: {config_path}")
    
    return results

def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(description="Install or uninstall WinDBG MCP server configuration")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--install", action="store_true", help="Install WinDBG MCP server configuration (default)")
    group.add_argument("--uninstall", action="store_true", help="Uninstall WinDBG MCP server configuration")
    parser.add_argument("--quiet", action="store_true", help="Suppress informational messages")
    parser.add_argument("--force", action="store_true", help="Force installation even if app is not detected")
    
    args = parser.parse_args()
    
    # If neither install nor uninstall is specified, default to install
    if not (args.install or args.uninstall):
        args.install = True
    
    # Detect OS and get client paths
    os_type = get_os_type()
    if not args.quiet:
        print(f"Detected OS: {os_type}")
    
    client_paths = get_client_config_paths(os_type)
    
    # Process client configurations
    if args.install:
        process_clients(client_paths, install_windbg_mcp, args.quiet)
    elif args.uninstall:
        process_clients(client_paths, uninstall_windbg_mcp, args.quiet)

if __name__ == "__main__":
    main() 