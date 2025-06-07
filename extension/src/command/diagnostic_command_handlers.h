#pragma once

#include "pch.h"
#include "../include/json.hpp"
#include "command_utilities.h"  // Include for utility functions and types
#include "../ipc/mcp_server.h"
#include <Windows.h>
#include <DbgEng.h>
#include <WDBGEXTS.H>
#include <string>
#include <vector>
#include <chrono>

using json = nlohmann::json;

// Forward declarations
class MCPServer;

/**
 * @brief Diagnostic command handlers for health monitoring and troubleshooting.
 * 
 * This class provides handlers for diagnostic operations including:
 * - Health checks and system status
 * - Connection status monitoring
 * - Session state capture
 * - Performance metrics collection
 * - Error diagnostics and recovery
 */
class DiagnosticCommandHandlers {
public:
    /**
     * @brief Register diagnostic command handlers with the MCP server.
     * @param server The MCP server instance.
     */
    static void RegisterHandlers(MCPServer& server);
    
    // Diagnostic command handlers
    
    /**
     * @brief Perform comprehensive health check.
     * @param message JSON message (no parameters required).
     * @return JSON response with health status and metrics.
     */
    static json HealthCheckHandler(const json& message);
    
    // Removed duplicate handlers - connection_status and capture_session_state
    // are now handled by enhanced_command_handlers.h to avoid conflicts
    
    /**
     * @brief Collect performance metrics.
     * @param message JSON message (no parameters required).
     * @return JSON response with performance data and statistics.
     */
    static json PerformanceMetricsHandler(const json& message);

private:
    // Private helper methods for diagnostic operations
    
    /**
     * @brief Test WinDbg responsiveness with a quick command.
     * @return True if WinDbg responds within timeout.
     */
    static bool TestWinDbgResponsiveness();
    
    /**
     * @brief Get current system resource usage.
     * @return JSON object with resource metrics.
     */
    static json GetSystemResourceMetrics();
    
    /**
     * @brief Assess overall system health.
     * @return Health status string (healthy/degraded/unhealthy).
     */
    static std::string AssessSystemHealth();
    
    /**
     * @brief Get detailed connection diagnostics.
     * @return JSON object with connection diagnostic data.
     */
    static json GetConnectionDiagnostics();
}; 