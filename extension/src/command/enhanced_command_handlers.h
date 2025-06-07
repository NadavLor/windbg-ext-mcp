#pragma once

#include "pch.h"
#include "../include/json.hpp"
#include "../ipc/mcp_server.h"
#include "command_handlers.h"  // For ErrorCategory enum
#include "command_utilities.h"  // Include for ErrorCategory and TimeoutCategory enums
#include <Windows.h>
#include <DbgEng.h>
#include <WDBGEXTS.H>
#include <string>
#include <vector>
#include <chrono>

using json = nlohmann::json;

/**
 * @brief Enhanced command handlers for WinDbg command execution.
 * 
 * This class contains handlers for executing WinDbg commands with advanced
 * features like error classification, timeout optimization, and specialized
 * command handling for different types of debugging operations.
 */
class EnhancedCommandHandlers {
public:
    /**
     * @brief Register all enhanced command handlers with the MCP server.
     * @param server The MCP server instance to register handlers with.
     */
    static void RegisterHandlers(MCPServer& server);

    /**
     * @brief Handle standard command execution requests.
     * @param message The incoming JSON message.
     * @return JSON response with command output or error information.
     */
    static json ExecuteCommandHandler(const json& message);
    
    /**
     * @brief Handle enhanced command execution with metadata.
     * @param message The incoming JSON message.
     * @return JSON response with command output and execution metadata.
     */
    static json ExecuteCommandEnhancedHandler(const json& message);
    
    /**
     * @brief Handle streaming command execution for large outputs.
     * @param message The incoming JSON message.
     * @return JSON response with streaming command output.
     */
    static json ExecuteCommandStreamingHandler(const json& message);
    
    /**
     * @brief Handle for-each module requests.
     * @param message The incoming JSON message.
     * @return JSON response with module enumeration results.
     */
    static json ForEachModuleHandler(const json& message);



    /**
     * @brief Handle process-specific commands with specialized logic.
     * @param id Message ID for response correlation.
     * @param command The process command to execute.
     * @param timeout Timeout in milliseconds.
     * @return JSON response with process command output.
     */
    static json HandleProcessCommand(int id, const std::string& command, unsigned int timeout);
    
    /**
     * @brief Handle DLLs-specific commands with specialized logic.
     * @param id Message ID for response correlation.
     * @param command The DLLs command to execute.
     * @param timeout Timeout in milliseconds.
     * @return JSON response with DLLs command output.
     */
    static json HandleDllsCommand(int id, const std::string& command, unsigned int timeout);
    
    /**
     * @brief Handle address-specific commands with specialized logic.
     * @param id Message ID for response correlation.
     * @param command The address command to execute.
     * @param timeout Timeout in milliseconds.
     * @return JSON response with address command output.
     */
    static json HandleAddressCommand(int id, const std::string& command, unsigned int timeout);

    /**
     * @brief Handle unified callback enumeration requests.
     * @param message The incoming JSON message.
     * @return JSON response with consolidated callback enumeration results.
     */
    static json UnifiedCallbackEnumerationHandler(const json& message);

private:
    // Private helper methods can be added here in the future
}; 