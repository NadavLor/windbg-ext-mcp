#pragma once

#include "pch.h"
#include "../ipc/mcp_server.h"
#include <functional>
#include <string>
#include <map>

/**
 * @brief Command registry for managing WinDbg extension commands.
 * 
 * This class provides a centralized registry for all command handlers,
 * allowing for better organization and modularity. It replaces the
 * large monolithic command handler registration.
 */
class CommandRegistry {
public:
    /**
     * @brief Register all command handlers with the MCP server.
     * @param server The MCP server instance to register handlers with.
     */
    static void RegisterAllHandlers(MCPServer& server);

private:
    /**
     * @brief Register basic command handlers.
     * @param server The MCP server instance.
     */
    static void RegisterBasicHandlers(MCPServer& server);
    
    /**
     * @brief Register enhanced command handlers.
     * @param server The MCP server instance.
     */
    static void RegisterEnhancedHandlers(MCPServer& server);
    
    /**
     * @brief Register diagnostic command handlers.
     * @param server The MCP server instance.
     */
    static void RegisterDiagnosticHandlers(MCPServer& server);
    
    /**
     * @brief Register specialized command handlers.
     * @param server The MCP server instance.
     */
    static void RegisterSpecializedHandlers(MCPServer& server);
}; 