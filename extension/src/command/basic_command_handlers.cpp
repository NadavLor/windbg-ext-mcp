#include "pch.h"
#include "command/basic_command_handlers.h"
#include "command/command_utilities.h"
#include "../ipc/mcp_server.h"  // Include MCPServer definition

void BasicCommandHandlers::RegisterHandlers(MCPServer& server) {
    // Register basic command handlers
    server.RegisterHandler("check_connection", CheckConnectionHandler);
    server.RegisterHandler("version", VersionHandler);
    server.RegisterHandler("get_metadata", GetMetadataHandler);
    server.RegisterHandler("lm", ListModulesHandler);
    server.RegisterHandler("dt", DisplayTypeHandler);
    server.RegisterHandler("dd", DisplayMemoryHandler);
}

json BasicCommandHandlers::CheckConnectionHandler(const json& message) {
    return CommandUtilities::CreateSuccessResponse(
        message.value("id", 0),
        "check_connection",
        "Connection verified successfully"
    );
}

json BasicCommandHandlers::VersionHandler(const json& message) {
    // Get WinDBG version
    std::string version = "WinDbg Extension v1.0.0";
    
    return CommandUtilities::CreateSuccessResponse(
        message.value("id", 0),
        "version",
        version
    );
}

json BasicCommandHandlers::GetMetadataHandler(const json& message) {
    // Get basic metadata about the debugging session
    std::string targetInfo;
    std::string modules;
    
    // Maximum output size to prevent excessive memory usage (64KB)
    const size_t MAX_OUTPUT_SIZE = 65536;
    
    // Try to execute basic WinDBG commands to gather metadata
    try {
        auto args = message.value("args", json::object());
        unsigned int timeout = args.value("timeout_ms", 15000u); // 15 second default for metadata
        
        targetInfo = CommandUtilities::ExecuteWinDbgCommand("!target", timeout);
        modules = CommandUtilities::ExecuteWinDbgCommand("lm", timeout);
        
        // Limit output size to prevent excessive memory usage
        if (targetInfo.size() > MAX_OUTPUT_SIZE) {
            targetInfo = targetInfo.substr(0, MAX_OUTPUT_SIZE) + 
                        "\n... [Output truncated due to size limit]";
        }
        
        if (modules.size() > MAX_OUTPUT_SIZE) {
            modules = modules.substr(0, MAX_OUTPUT_SIZE) + 
                     "\n... [Output truncated due to size limit]";
        }
        
        // Create combined metadata output
        std::string metadata = "Target Information:\n" + targetInfo + 
                              "\n\nModules:\n" + modules;
        
        return CommandUtilities::CreateSuccessResponse(
            message.value("id", 0),
            "get_metadata",
            metadata
        );
    }
    catch (const std::exception& e) {
        return CommandUtilities::CreateErrorResponse(
            message.value("id", 0),
            "get_metadata",
            std::string("Failed to get metadata: ") + e.what()
        );
    }
}

json BasicCommandHandlers::ListModulesHandler(const json& message) {
    try {
        auto args = message.value("args", json::object());
        unsigned int timeout = args.value("timeout_ms", 10000u);
        
        // Maximum output size to prevent excessive memory usage (64KB)
        const size_t MAX_OUTPUT_SIZE = 65536;
        
        std::string output = CommandUtilities::ExecuteWinDbgCommand("lm", timeout);
        
        // Limit output size to prevent excessive memory usage
        if (output.size() > MAX_OUTPUT_SIZE) {
            output = output.substr(0, MAX_OUTPUT_SIZE) + 
                    "\n... [Output truncated due to size limit - use more specific lm options for full listing]";
        }
        
        return CommandUtilities::CreateSuccessResponse(
            message.value("id", 0),
            "lm",
            output
        );
    }
    catch (const std::exception& e) {
        return CommandUtilities::CreateErrorResponse(
            message.value("id", 0),
            "lm",
            std::string("Command failed: ") + e.what()
        );
    }
}

json BasicCommandHandlers::DisplayTypeHandler(const json& message) {
    try {
        auto args = message.value("args", json::object());
        std::string typeName = args.value("type_name", "");
        std::string address = args.value("address", "");
        unsigned int timeout = args.value("timeout_ms", 10000u);
        
        if (typeName.empty()) {
            return CommandUtilities::CreateErrorResponse(
                message.value("id", 0),
                "dt",
                "Type name is required"
            );
        }
        
        std::string command = "dt " + typeName;
        if (!address.empty()) {
            command += " " + address;
        }
        
        std::string output = CommandUtilities::ExecuteWinDbgCommand(command, timeout);
        return CommandUtilities::CreateSuccessResponse(
            message.value("id", 0),
            "dt",
            output
        );
    }
    catch (const std::exception& e) {
        return CommandUtilities::CreateErrorResponse(
            message.value("id", 0),
            "dt",
            std::string("Command failed: ") + e.what()
        );
    }
}

json BasicCommandHandlers::DisplayMemoryHandler(const json& message) {
    try {
        auto args = message.value("args", json::object());
        std::string address = args.value("address", "");
        int length = args.value("length", 32);
        unsigned int timeout = args.value("timeout_ms", 10000u);
        
        if (address.empty()) {
            return CommandUtilities::CreateErrorResponse(
                message.value("id", 0),
                "dd",
                "Address is required"
            );
        }
        
        std::string command = "dd " + address + " " + std::to_string(length);
        std::string output = CommandUtilities::ExecuteWinDbgCommand(command, timeout);
        return CommandUtilities::CreateSuccessResponse(
            message.value("id", 0),
            "dd",
            output
        );
    }
    catch (const std::exception& e) {
        return CommandUtilities::CreateErrorResponse(
            message.value("id", 0),
            "dd",
            std::string("Command failed: ") + e.what()
        );
    }
} 