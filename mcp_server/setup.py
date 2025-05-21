from setuptools import setup, find_packages

setup(
    name="windbg-mcp",
    version="0.1.0",
    description="Model Context Protocol server for WinDbg integration",
    author="WinDbg MCP Team",
    packages=find_packages(),
    install_requires=[
        "fastmcp>=0.2.0",
        "pywin32>=305.1",
        "requests>=2.25.0",
        "sseclient-py>=1.8.0",
    ],
    python_requires=">=3.8",
    entry_points={
        "console_scripts": [
            "windbg-mcp=hybrid_server:main",
        ],
    },
) 