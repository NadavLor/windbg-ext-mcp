#pragma once

#include "pch.h"
#include "../include/json.hpp"
#include "command_utilities.h"  // Include for ErrorCategory and TimeoutCategory enums
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
 * @brief Main command handlers class - refactored for modularity.
 * 
 * This class now serves as the main entry point for command handling,
 * delegating to specialized handler classes for better organization.
 * 
 * The actual command implementations have been moved to:
 * - BasicCommandHandlers: Basic operations (version, connection, etc.)
 * - EnhancedCommandHandlers: Command execution with advanced features
 * - DiagnosticCommandHandlers: Health checks and diagnostics
 * - CommandUtilities: Shared utilities and helpers
 */
class CommandHandlers {
public:
    /**
     * @brief Register all command handlers with the MCP server.
     * @param server The MCP server instance.
     * 
     * This method delegates to CommandRegistry for better organization.
     */
    static void RegisterHandlers(MCPServer& server);
    
    // Basic command handlers (delegate to BasicCommandHandlers)
    static json CheckConnectionHandler(const json& message);
    static json VersionHandler(const json& message);
    static json GetMetadataHandler(const json& message);
    static json ListModulesHandler(const json& message);
    static json DisplayTypeHandler(const json& message);
    static json DisplayMemoryHandler(const json& message);
    
    // Diagnostic command handlers (delegate to DiagnosticCommandHandlers)
    static json HealthCheckHandler(const json& message);                    // -> DiagnosticCommandHandlers
    static json PerformanceMetricsHandler(const json& message);             // -> DiagnosticCommandHandlers
    
    // Enhanced command handlers (delegate to EnhancedCommandHandlers)
    static json ExecuteCommandHandler(const json& message);
    static json ExecuteCommandEnhancedHandler(const json& message);
    static json ExecuteCommandStreamingHandler(const json& message);
    static json ForEachModuleHandler(const json& message);
    
    // Utility methods (delegate to CommandUtilities)
    static std::string ExecuteWinDbgCommand(const std::string& command, unsigned int timeoutMs = 10000);
    
    // Response creation methods
    static json CreateSuccessResponse(int id, const std::string& command, const std::string& output);
    static json CreateSuccessResponseWithMetadata(int id, const std::string& command, const std::string& output, 
                                                  double execution_time, const std::string& debugging_mode = "");
    static json CreateEnhancedErrorResponse(int id, const std::string& command, 
                                            const std::string& error,
                                            ErrorCategory category,
                                            const std::string& suggestion = "");
    static json CreateErrorResponse(int id, const std::string& command, const std::string& error);
    static json CreateDetailedErrorResponse(int id, const std::string& command, const std::string& error,
                                            ErrorCategory category, HRESULT errorCode = S_OK,
                                            const std::string& suggestion = "");
    
    // Error handling methods
    static ErrorCategory ClassifyError(const std::string& errorMessage, HRESULT errorCode = S_OK);
    static std::string GetErrorCategoryString(ErrorCategory category);
    static std::string GetSuggestionForError(ErrorCategory category, const std::string& command, HRESULT errorCode = S_OK);
    
    // Timeout management methods
    static TimeoutCategory CategorizeCommand(const std::string& command);
    static unsigned int GetTimeoutForCategory(TimeoutCategory category);
    
    // Helper methods for specific command types
    static json HandleProcessCommand(int id, const std::string& command, unsigned int timeout);
    static json HandleDllsCommand(int id, const std::string& command, unsigned int timeout);
    static json HandleAddressCommand(int id, const std::string& command, unsigned int timeout);

private:
    // This class now primarily serves as a compatibility layer
    // The actual implementations are in the specialized handler classes
}; 