"""
Setup script for WinDbg MCP Server.
"""
from setuptools import setup, find_packages

# Read requirements from requirements.txt
with open("requirements.txt") as f:
    requirements = [line.strip() for line in f if line.strip() and not line.startswith("#")]

setup(
    name="windbg-mcp",
    version="0.1.0",
    description="Model Context Protocol server for WinDbg integration",
    long_description="A Model Context Protocol server that connects WinDbg to Cursor for enhanced debugging with LLM assistance.",
    author="WinDbg MCP Team",
    author_email="windbg-mcp@example.com",
    url="https://github.com/NadavLor/windbg-ext-mcp",
    packages=find_packages(),
    install_requires=requirements,
    python_requires=">=3.8",
    entry_points={
        "console_scripts": [
            "windbg-mcp=server:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Debuggers",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
) 