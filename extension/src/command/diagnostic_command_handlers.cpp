#include "pch.h"
#include "command/diagnostic_command_handlers.h"
#include "command/command_utilities.h"
#include "../ipc/mcp_server.h"  // Include MCPServer definition

void DiagnosticCommandHandlers::RegisterHandlers(MCPServer& server) {
    // Register diagnostic command handlers
    server.RegisterHandler("health_check", HealthCheckHandler);
    server.RegisterHandler("performance_metrics", PerformanceMetricsHandler);
}

json DiagnosticCommandHandlers::HealthCheckHandler(const json& message) {
    try {
        // Perform basic health checks
        auto now = std::chrono::steady_clock::now();
        auto lastCommandTime = CommandUtilities::GetLastCommandTime();
        auto timeSinceLastCommand = std::chrono::duration_cast<std::chrono::seconds>(now - lastCommandTime).count();
        
        // Check basic WinDbg responsiveness
        std::string versionOutput;
        bool isResponsive = false;
        try {
            versionOutput = CommandUtilities::ExecuteWinDbgCommand("version", 5000);
            isResponsive = true;
        }
        catch (const std::exception& e) {
            versionOutput = std::string("Error: ") + e.what();
        }
        
        // Determine health status
        std::string status = "healthy";
        std::string message_text = "All systems operational";
        
        if (!isResponsive) {
            status = "unhealthy";
            message_text = "WinDbg is not responding";
        }
        else if (timeSinceLastCommand > 300) {  // 5 minutes
            status = "idle";
            message_text = "No commands executed recently";
        }
        
        return {
            {"type", "response"},
            {"id", message.value("id", 0)},
            {"status", "success"},
            {"health", {
                {"status", status},
                {"message", message_text},
                {"windbg_responsive", isResponsive},
                {"time_since_last_command", timeSinceLastCommand},
                {"last_execution_time", CommandUtilities::GetLastExecutionTime()},
                {"session_id", CommandUtilities::GetSessionId()},
                {"timestamp", CommandUtilities::GetCurrentTimestamp()}
            }}
        };
    }
    catch (const std::exception& e) {
        return CommandUtilities::CreateErrorResponse(
            message.value("id", 0),
            "health_check",
            std::string("Health check failed: ") + e.what()
        );
    }
}

// Removed duplicate handlers - connection_status and capture_session_state
// are now handled by enhanced_command_handlers.cpp to avoid conflicts

json DiagnosticCommandHandlers::PerformanceMetricsHandler(const json& message) {
    try {
        auto now = std::chrono::steady_clock::now();
        auto lastCommandTime = CommandUtilities::GetLastCommandTime();
        auto timeSinceLastCommand = std::chrono::duration_cast<std::chrono::milliseconds>(now - lastCommandTime).count();
        
        // Basic performance metrics
        json metrics = {
            {"last_execution_time_ms", CommandUtilities::GetLastExecutionTime() * 1000},
            {"time_since_last_command_ms", timeSinceLastCommand},
            {"session_id", CommandUtilities::GetSessionId()},
            {"uptime_seconds", std::chrono::duration_cast<std::chrono::seconds>(now.time_since_epoch()).count()},
            {"timestamp", CommandUtilities::GetCurrentTimestamp()}
        };
        
        // Test command execution performance
        auto testStart = std::chrono::steady_clock::now();
        try {
            CommandUtilities::ExecuteWinDbgCommand("version", 3000);
            auto testEnd = std::chrono::steady_clock::now();
            auto testDuration = std::chrono::duration<double>(testEnd - testStart).count();
            metrics["test_command_time_ms"] = testDuration * 1000;
            metrics["performance_status"] = testDuration < 1.0 ? "good" : (testDuration < 3.0 ? "fair" : "poor");
        }
        catch (const std::exception& e) {
            metrics["test_command_time_ms"] = -1;
            metrics["performance_status"] = "error";
            metrics["performance_error"] = e.what();
        }
        
        return {
            {"type", "response"},
            {"id", message.value("id", 0)},
            {"status", "success"},
            {"performance_metrics", metrics}
        };
    }
    catch (const std::exception& e) {
        return CommandUtilities::CreateErrorResponse(
            message.value("id", 0),
            "performance_metrics",
            std::string("Performance metrics collection failed: ") + e.what()
        );
    }
} 