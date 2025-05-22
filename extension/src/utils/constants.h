/**
 * @file constants.h
 * @brief Common constants used throughout the WinDbg MCP Extension.
 */
#pragma once

#include <Windows.h>

/**
 * @namespace Constants
 * @brief Contains all constants used by the WinDbg MCP Extension.
 */
namespace Constants {
    // Named pipe settings
    constexpr const char* DEFAULT_PIPE_NAME = "\\\\.\\pipe\\windbgmcp";
    constexpr DWORD PIPE_BUFFER_SIZE = 4096;  // Buffer size for reading from the pipe
    
    // Timeout settings (in milliseconds)
    constexpr unsigned int DEFAULT_TIMEOUT_MS = 10000;    // Default timeout (10 seconds)
    constexpr unsigned int LONG_TIMEOUT_MS = 30000;       // Longer timeout for complex commands (30 seconds)
    constexpr unsigned int VERY_LONG_TIMEOUT_MS = 60000;  // Very long timeout for heavy operations (60 seconds)
    
    // Server version information
    constexpr const char* SERVER_VERSION = "WinDbg Extension v1.0.0";
} 