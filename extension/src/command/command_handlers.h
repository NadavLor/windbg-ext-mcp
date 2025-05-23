#pragma once

#include "pch.h"
#include "ipc/mcp_server.h"
#include <Windows.h>
#include <DbgEng.h>
#include <WDBGEXTS.H>
#include <string>
#include <map>
#include <vector>
#include <chrono>

// Error categories and codes for better error handling
enum class ErrorCategory {
    None,
    CommandSyntax,    // Syntax or usage errors
    ExecutionContext, // Wrong context (e.g., wrong mode, wrong state)
    Timeout,          // Command timed out
    SymbolResolution, // Symbol or type not found
    MemoryAccess,     // Memory access issues
    ExtensionLoad,    // Extension not loaded
    InternalError,    // Internal errors in the extension
    ApiError,         // WinDbg API errors
    Unknown           // Uncategorized errors
};

// Timeout categories for different command types
enum class TimeoutCategory {
    QUICK,      // 5 seconds
    NORMAL,     // 15 seconds  
    SLOW,       // 30 seconds
    BULK,       // 60 seconds
    ANALYSIS    // 120 seconds
};

// Command handler registration for the MCP server
class CommandHandlers {
public:
    // Register all command handlers with the MCP server
    static void RegisterHandlers(MCPServer& server);

private:
    // Existing command handlers
    static json CheckConnectionHandler(const json& message);
    static json VersionHandler(const json& message);
    static json GetMetadataHandler(const json& message);
    static json ListModulesHandler(const json& message);
    static json DisplayTypeHandler(const json& message);
    static json DisplayMemoryHandler(const json& message);
    static json ExecuteCommandHandler(const json& message);
    static json ForEachModuleHandler(const json& message);
    
    // New command handlers for enhanced features
    static json HealthCheckHandler(const json& message);
    static json ConnectionStatusHandler(const json& message);
    static json CaptureSessionStateHandler(const json& message);
    static json PerformanceMetricsHandler(const json& message);
    static json ExecuteCommandEnhancedHandler(const json& message);
    static json ExecuteCommandStreamingHandler(const json& message);
    
    // Specialized command handlers
    static json HandleProcessCommand(int id, const std::string& command, unsigned int timeout);
    static json HandleDllsCommand(int id, const std::string& command, unsigned int timeout);
    static json HandleAddressCommand(int id, const std::string& command, unsigned int timeout);
    
    // Helper functions
    static std::string ExecuteWinDbgCommand(const std::string& command, unsigned int timeoutMs = 10000);
    
    // Enhanced response creation methods
    static json CreateSuccessResponse(int id, const std::string& command, const std::string& output);
    static json CreateSuccessResponseWithMetadata(int id, const std::string& command, const std::string& output, 
                                                 double execution_time = 0.0, const std::string& debugging_mode = "");
    static json CreateErrorResponse(int id, const std::string& command, const std::string& error);
    static json CreateEnhancedErrorResponse(int id, const std::string& command, 
                                          const std::string& error, 
                                          ErrorCategory category,
                                          const std::vector<std::string>& suggestions = {},
                                          const std::vector<std::string>& examples = {},
                                          const std::vector<std::string>& next_steps = {});
    
    // Enhanced error response methods (backward compatibility)
    static json CreateDetailedErrorResponse(
        int id, 
        const std::string& command, 
        const std::string& error,
        ErrorCategory category,
        HRESULT errorCode = S_OK,
        const std::string& suggestion = ""
    );
    
    // Utility methods
    static std::string GetCurrentTimestamp();
    static std::string GetDebuggingMode();
    static std::string GetExtensionVersion();
    static std::string GetWinDbgVersion();
    static bool IsConnectionStable();
    static bool IsTargetResponsive();
    static double CalculateHealthScore();
    static std::string GetLastCommandTime();
    static std::string GenerateSessionId();
    static json GetCurrentProcessInfo();
    static json GetCurrentThreadInfo();
    static json GetActiveBreakpoints();
    static json GetLoadedModulesInfo();
    static json GetTargetSystemInfo();
    
    // Timeout management
    static TimeoutCategory CategorizeCommand(const std::string& command);
    static unsigned int GetTimeoutForCategory(TimeoutCategory category);
    
    // Error classification helpers
    static ErrorCategory ClassifyError(const std::string& errorMessage, HRESULT errorCode);
    static std::string GetErrorCategoryString(ErrorCategory category);
    static std::string GetSuggestionForError(ErrorCategory category, const std::string& command, HRESULT errorCode);
}; 