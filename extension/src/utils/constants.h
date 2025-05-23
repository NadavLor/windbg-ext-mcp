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
    
    // Timeout settings (in milliseconds) - Enhanced categorization
    constexpr unsigned int DEFAULT_TIMEOUT_MS = 10000;    // Default timeout (10 seconds)
    constexpr unsigned int LONG_TIMEOUT_MS = 30000;       // Longer timeout for complex commands (30 seconds)
    constexpr unsigned int VERY_LONG_TIMEOUT_MS = 60000;  // Very long timeout for heavy operations (60 seconds)
    
    // New categorized timeouts for enhanced performance
    constexpr unsigned int QUICK_TIMEOUT_MS = 5000;       // Quick commands (5 seconds)
    constexpr unsigned int NORMAL_TIMEOUT_MS = 15000;     // Normal commands (15 seconds)
    constexpr unsigned int SLOW_TIMEOUT_MS = 30000;       // Slow commands (30 seconds)
    constexpr unsigned int BULK_TIMEOUT_MS = 60000;       // Bulk operations (60 seconds)
    constexpr unsigned int ANALYSIS_TIMEOUT_MS = 120000;  // Analysis commands (120 seconds)
    
    // Performance and streaming settings
    constexpr size_t MAX_OUTPUT_SIZE = 1048576;           // 1MB max output size
    constexpr int DEFAULT_CHUNK_SIZE = 4096;              // Default streaming chunk size
    constexpr double HEALTH_CHECK_INTERVAL = 300.0;      // Health check interval (5 minutes)
    
    // Server version information
    constexpr const char* SERVER_VERSION = "WinDbg MCP Extension v1.1.0";
    constexpr const char* EXTENSION_NAME = "WinDbg MCP Extension";
    constexpr const char* EXTENSION_DESCRIPTION = "Enhanced WinDbg Extension with MCP Server Integration";
} 