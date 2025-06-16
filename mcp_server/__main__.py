#!/usr/bin/env python
"""
Entry point for mcp_server when run as a module.
This file enables running the server with proper import resolution.
"""
import sys
import os

# Add the current directory to Python path to enable relative imports
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

def main():
    """Main entry point that properly sets up the environment."""
    # Now import from the server module with relative imports working
    from server import main as server_main
    server_main()

if __name__ == "__main__":
    main()
