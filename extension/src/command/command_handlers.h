#pragma once

#include "pch.h"
#include "ipc/mcp_server.h"
#include <Windows.h>
#include <DbgEng.h>
#include <WDBGEXTS.H>
#include <string>
#include <map>

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

// Command handler registration for the MCP server
class CommandHandlers {
public:
    // Register all command handlers with the MCP server
    static void RegisterHandlers(MCPServer& server);

private:
    // Command handlers
    static json CheckConnectionHandler(const json& message);
    static json VersionHandler(const json& message);
    static json GetMetadataHandler(const json& message);
    static json ListModulesHandler(const json& message);
    static json DisplayTypeHandler(const json& message);
    static json DisplayMemoryHandler(const json& message);
    static json ExecuteCommandHandler(const json& message);
    static json ForEachModuleHandler(const json& message);
    
    // New specialized command handlers
    static json HandleProcessCommand(int id, const std::string& command, unsigned int timeout);
    static json HandleDllsCommand(int id, const std::string& command, unsigned int timeout);
    static json HandleAddressCommand(int id, const std::string& command, unsigned int timeout);
    
    // Helper functions
    static std::string ExecuteWinDbgCommand(const std::string& command, unsigned int timeoutMs = 10000);
    static json CreateSuccessResponse(int id, const std::string& command, const std::string& output);
    static json CreateErrorResponse(int id, const std::string& command, const std::string& error);
    
    // Enhanced error response methods
    static json CreateDetailedErrorResponse(
        int id, 
        const std::string& command, 
        const std::string& error,
        ErrorCategory category,
        HRESULT errorCode = S_OK,
        const std::string& suggestion = ""
    );
    
    // Error classification helpers
    static ErrorCategory ClassifyError(const std::string& errorMessage, HRESULT errorCode);
    static std::string GetErrorCategoryString(ErrorCategory category);
    static std::string GetSuggestionForError(ErrorCategory category, const std::string& command, HRESULT errorCode);
}; 