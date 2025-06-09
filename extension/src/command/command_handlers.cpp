#include "pch.h"
#include "command_handlers.h"
#include "command_registry.h"
#include "basic_command_handlers.h"
#include "diagnostic_command_handlers.h"
#include "enhanced_command_handlers.h"
#include "command_utilities.h"
#include "../ipc/mcp_server.h"  // Include MCPServer definition

// Main CommandHandlers class now delegates to modular implementations
void CommandHandlers::RegisterHandlers(MCPServer& server) {
    // Use the centralized command registry
    CommandRegistry::RegisterAllHandlers(server);
}

// Delegate basic command handlers to BasicCommandHandlers
json CommandHandlers::CheckConnectionHandler(const json& message) {
    return BasicCommandHandlers::CheckConnectionHandler(message);
}

json CommandHandlers::VersionHandler(const json& message) {
    return BasicCommandHandlers::VersionHandler(message);
}

json CommandHandlers::GetMetadataHandler(const json& message) {
    return BasicCommandHandlers::GetMetadataHandler(message);
}

json CommandHandlers::ListModulesHandler(const json& message) {
    return BasicCommandHandlers::ListModulesHandler(message);
}

json CommandHandlers::DisplayTypeHandler(const json& message) {
    return BasicCommandHandlers::DisplayTypeHandler(message);
}

json CommandHandlers::DisplayMemoryHandler(const json& message) {
    return BasicCommandHandlers::DisplayMemoryHandler(message);
}

// Delegate diagnostic command handlers to DiagnosticCommandHandlers
json CommandHandlers::HealthCheckHandler(const json& message) {
    return DiagnosticCommandHandlers::HealthCheckHandler(message);
}

json CommandHandlers::PerformanceMetricsHandler(const json& message) {
    return DiagnosticCommandHandlers::PerformanceMetricsHandler(message);
}



// Delegate enhanced command handlers to EnhancedCommandHandlers
json CommandHandlers::ExecuteCommandHandler(const json& message) {
    return EnhancedCommandHandlers::ExecuteCommandHandler(message);
}

json CommandHandlers::ExecuteCommandEnhancedHandler(const json& message) {
    return EnhancedCommandHandlers::ExecuteCommandEnhancedHandler(message);
}

json CommandHandlers::ExecuteCommandStreamingHandler(const json& message) {
    return EnhancedCommandHandlers::ExecuteCommandStreamingHandler(message);
}

json CommandHandlers::ForEachModuleHandler(const json& message) {
    return EnhancedCommandHandlers::ForEachModuleHandler(message);
}

// Delegate utility functions to CommandUtilities
std::string CommandHandlers::ExecuteWinDbgCommand(const std::string& command, unsigned int timeoutMs) {
    return CommandUtilities::ExecuteWinDbgCommand(command, timeoutMs);
}

json CommandHandlers::CreateSuccessResponse(int id, const std::string& command, const std::string& output) {
    return CommandUtilities::CreateSuccessResponse(id, command, output);
}

json CommandHandlers::CreateSuccessResponseWithMetadata(int id, const std::string& command, const std::string& output, 
                                                      double execution_time, const std::string& debugging_mode) {
    return CommandUtilities::CreateSuccessResponseWithMetadata(id, command, output, execution_time, debugging_mode);
}

json CommandHandlers::CreateEnhancedErrorResponse(int id, const std::string& command, 
                                                 const std::string& error, 
                                                 ErrorCategory category,
                                                 const std::string& suggestion) {
    return CommandUtilities::CreateEnhancedErrorResponse(id, command, error, category, suggestion);
}

json CommandHandlers::CreateErrorResponse(int id, const std::string& command, const std::string& error) {
    return CommandUtilities::CreateErrorResponse(id, command, error);
}

json CommandHandlers::CreateDetailedErrorResponse(
    int id,
    const std::string& command,
    const std::string& error,
    ErrorCategory category,
    HRESULT errorCode,
    const std::string& suggestion) {
    return CommandUtilities::CreateDetailedErrorResponse(id, command, error, category, errorCode, suggestion);
}

ErrorCategory CommandHandlers::ClassifyError(const std::string& errorMessage, HRESULT errorCode) {
    return CommandUtilities::ClassifyError(errorMessage, errorCode);
}

std::string CommandHandlers::GetErrorCategoryString(ErrorCategory category) {
    return CommandUtilities::GetErrorCategoryString(category);
}

std::string CommandHandlers::GetSuggestionForError(ErrorCategory category, const std::string& command, HRESULT errorCode) {
    return CommandUtilities::GetSuggestionForError(category, command, errorCode);
}

TimeoutCategory CommandHandlers::CategorizeCommand(const std::string& command) {
    return CommandUtilities::CategorizeCommand(command);
}

unsigned int CommandHandlers::GetTimeoutForCategory(TimeoutCategory category) {
    return CommandUtilities::GetTimeoutForCategory(category);
}

// Helper methods for specific command types (delegate to EnhancedCommandHandlers)
json CommandHandlers::HandleProcessCommand(int id, const std::string& command, unsigned int timeout) {
    return EnhancedCommandHandlers::HandleProcessCommand(id, command, timeout);
}

json CommandHandlers::HandleDllsCommand(int id, const std::string& command, unsigned int timeout) {
    return EnhancedCommandHandlers::HandleDllsCommand(id, command, timeout);
}

json CommandHandlers::HandleAddressCommand(int id, const std::string& command, unsigned int timeout) {
    return EnhancedCommandHandlers::HandleAddressCommand(id, command, timeout);
} 