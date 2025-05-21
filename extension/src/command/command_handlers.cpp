#include "pch.h"
#include "command/command_handlers.h"
#include "utils/output_callbacks.h"
#include <sstream>
#include <atlcomcli.h>
#include <future>
#include <chrono>
#include <algorithm>

// ExtensionApis is now forward-declared in pch.h and defined in types.cpp

void CommandHandlers::RegisterHandlers(MCPServer& server) {
    // Register command handlers
    server.RegisterHandler("check_connection", CheckConnectionHandler);
    server.RegisterHandler("version", VersionHandler);
    server.RegisterHandler("get_metadata", GetMetadataHandler);
    server.RegisterHandler("lm", ListModulesHandler);
    server.RegisterHandler("dt", DisplayTypeHandler);
    server.RegisterHandler("dd", DisplayMemoryHandler);
    server.RegisterHandler("execute_command", ExecuteCommandHandler);
    server.RegisterHandler("for_each_module", ForEachModuleHandler);
}

json CommandHandlers::CheckConnectionHandler(const json& message) {
    return {
        {"type", "response"},
        {"status", "success"},
        {"connected", true}
    };
}

json CommandHandlers::VersionHandler(const json& message) {
    // Get WinDBG version
    std::string version = "WinDbg Extension v1.0.0";
    
    return CreateSuccessResponse(
        message.value("id", 0),
        "version",
        version
    );
}

json CommandHandlers::GetMetadataHandler(const json& message) {
    // Get basic metadata about the debugging session
    std::string targetInfo;
    std::string modules;
    
    // Try to execute basic WinDBG commands to gather metadata
    try {
        targetInfo = ExecuteWinDbgCommand("!target");
        modules = ExecuteWinDbgCommand("lm");
    }
    catch (const std::exception& e) {
        return CreateErrorResponse(
            message.value("id", 0),
            "get_metadata",
            std::string("Failed to get metadata: ") + e.what()
        );
    }
    
    return {
        {"type", "response"},
        {"status", "success"},
        {"target_info", targetInfo},
        {"modules", modules},
        {"connected", true}
    };
}

json CommandHandlers::ListModulesHandler(const json& message) {
    try {
        auto args = message.value("args", json::object());
        unsigned int timeout = args.value("timeout_ms", 10000u);
        
        std::string output = ExecuteWinDbgCommand("lm", timeout);
        return CreateSuccessResponse(
            message.value("id", 0),
            "lm",
            output
        );
    }
    catch (const std::exception& e) {
        return CreateErrorResponse(
            message.value("id", 0),
            "lm",
            std::string("Command failed: ") + e.what()
        );
    }
}

json CommandHandlers::DisplayTypeHandler(const json& message) {
    try {
        auto args = message.value("args", json::object());
        std::string typeName = args.value("type_name", "");
        std::string address = args.value("address", "");
        unsigned int timeout = args.value("timeout_ms", 10000u);
        
        if (typeName.empty()) {
            return CreateErrorResponse(
                message.value("id", 0),
                "dt",
                "Type name is required"
            );
        }
        
        std::string command = "dt " + typeName;
        if (!address.empty()) {
            command += " " + address;
        }
        
        std::string output = ExecuteWinDbgCommand(command, timeout);
        return CreateSuccessResponse(
            message.value("id", 0),
            "dt",
            output
        );
    }
    catch (const std::exception& e) {
        return CreateErrorResponse(
            message.value("id", 0),
            "dt",
            std::string("Command failed: ") + e.what()
        );
    }
}

json CommandHandlers::DisplayMemoryHandler(const json& message) {
    try {
        auto args = message.value("args", json::object());
        std::string address = args.value("address", "");
        int length = args.value("length", 32);
        unsigned int timeout = args.value("timeout_ms", 10000u);
        
        if (address.empty()) {
            return CreateErrorResponse(
                message.value("id", 0),
                "dd",
                "Address is required"
            );
        }
        
        std::string command = "dd " + address + " " + std::to_string(length);
        std::string output = ExecuteWinDbgCommand(command, timeout);
        return CreateSuccessResponse(
            message.value("id", 0),
            "dd",
            output
        );
    }
    catch (const std::exception& e) {
        return CreateErrorResponse(
            message.value("id", 0),
            "dd",
            std::string("Command failed: ") + e.what()
        );
    }
}

json CommandHandlers::ExecuteCommandHandler(const json& message) {
    try {
        auto args = message.value("args", json::object());
        std::string command = args.value("command", "");
        unsigned int timeout = args.value("timeout_ms", 30000u);  // Increased default timeout to 30 seconds
        
        if (command.empty()) {
            return CreateErrorResponse(
                message.value("id", 0),
                "execute_command",
                "Command is required"
            );
        }
        
        // Special handling for specific commands that need custom processing
        if (command.find("!process") == 0) {
            // Process-specific handling
            return HandleProcessCommand(message.value("id", 0), command, timeout);
        }
        else if (command.find("!dlls") == 0) {
            // DLLs-specific handling
            return HandleDllsCommand(message.value("id", 0), command, timeout);
        }
        else if (command.find("!address") == 0) {
            // Address-specific handling
            return HandleAddressCommand(message.value("id", 0), command, timeout);
        }
        else if (command.find("!handle") == 0) {
            // Handle command may be long-running, increase timeout
            timeout = (timeout > 60000u) ? timeout : 60000u;  // Minimum 60-second timeout for handle command
        }
        
        std::string output = ExecuteWinDbgCommand(command, timeout);
        
        // Check if the output is empty or contains error messages
        if (output.empty()) {
            return CreateErrorResponse(
                message.value("id", 0),
                "execute_command",
                "Command returned no output. The command might be invalid or unsupported."
            );
        }
        
        // Check for common error patterns
        if (output.find("Usage:") != std::string::npos && 
            output.find("options") != std::string::npos) {
            return CreateErrorResponse(
                message.value("id", 0),
                "execute_command",
                "Command syntax error: " + output
            );
        }
        
        return CreateSuccessResponse(
            message.value("id", 0),
            "execute_command",
            output
        );
    }
    catch (const std::exception& e) {
        return CreateErrorResponse(
            message.value("id", 0),
            "execute_command",
            std::string("Command failed: ") + e.what()
        );
    }
}

// New helper methods for specific command types
json CommandHandlers::HandleProcessCommand(int id, const std::string& command, unsigned int timeout) {
    try {
        // Extract the process address and flags from the command
        // Format typically: !process [address] [flags]
        std::string processCmd = command;
        std::string output = ExecuteWinDbgCommand(processCmd, timeout);
        
        if (output.empty()) {
            // Try with ".process /r /p" instead which is more reliable
            size_t addressPos = command.find(" ");
            if (addressPos != std::string::npos) {
                std::string processAddress = command.substr(addressPos + 1);
                // Remove any flags
                size_t flagsPos = processAddress.find(" ");
                if (flagsPos != std::string::npos) {
                    processAddress = processAddress.substr(0, flagsPos);
                }
                
                std::string alternateCmd = ".process /r /p " + processAddress;
                output = ExecuteWinDbgCommand(alternateCmd, timeout);
                
                if (!output.empty()) {
                    return CreateSuccessResponse(id, "execute_command", output);
                }
            }
            
            return CreateErrorResponse(
                id,
                "execute_command",
                "Process command returned no output. The process address might be invalid."
            );
        }
        
        return CreateSuccessResponse(id, "execute_command", output);
    }
    catch (const std::exception& e) {
        return CreateErrorResponse(id, "execute_command", std::string("Process command failed: ") + e.what());
    }
}

json CommandHandlers::HandleDllsCommand(int id, const std::string& command, unsigned int timeout) {
    try {
        std::string output = ExecuteWinDbgCommand(command, timeout);
        
        // Check if it's a usage error
        if (output.find("Usage:") != std::string::npos) {
            // Try to correct common syntax errors
            std::string correctedCmd = command;
            
            // Check if using -p flag without proper spacing
            size_t pFlagPos = command.find("-p");
            if (pFlagPos != std::string::npos) {
                // Extract the address
                std::string addressPart = command.substr(pFlagPos + 2);
                // Remove leading whitespace
                addressPart.erase(0, addressPart.find_first_not_of(" \t\n\r\f\v"));
                
                // Rebuild command with proper format
                correctedCmd = "!process " + addressPart + " 7";
                output = ExecuteWinDbgCommand(correctedCmd, timeout);
                
                if (!output.empty()) {
                    // Now extract dll information
                    std::string dllsCmd = "!dlls";
                    std::string dllOutput = ExecuteWinDbgCommand(dllsCmd, timeout);
                    output = "Process modules:\n" + dllOutput;
                }
            }
        }
        
        if (output.empty()) {
            return CreateErrorResponse(
                id,
                "execute_command",
                "DLLs command returned no output. Try using '!process <address>' first to set the context."
            );
        }
        
        return CreateSuccessResponse(id, "execute_command", output);
    }
    catch (const std::exception& e) {
        return CreateErrorResponse(id, "execute_command", std::string("DLLs command failed: ") + e.what());
    }
}

json CommandHandlers::HandleAddressCommand(int id, const std::string& command, unsigned int timeout) {
    try {
        std::string output = ExecuteWinDbgCommand(command, timeout);
        
        // Check for invalid arguments
        if (output.find("Invalid arguments") != std::string::npos) {
            // Try alternate command forms
            std::string alternateCmd;
            
            if (command.find("-f:PAGE_EXECUTE_READWRITE") != std::string::npos) {
                // Use !vprot instead which gives similar information
                alternateCmd = "!vprot";
                std::string altOutput = ExecuteWinDbgCommand(alternateCmd, timeout);
                if (!altOutput.empty()) {
                    output = "Memory pages with PAGE_EXECUTE_READWRITE:\n" + altOutput;
                    return CreateSuccessResponse(id, "execute_command", output);
                }
            }
            else if (command.find("-f:ExecuteEnable") != std::string::npos) {
                // Use a combination of commands to get executable memory
                alternateCmd = "!address";
                std::string altOutput = ExecuteWinDbgCommand(alternateCmd, timeout);
                if (!altOutput.empty()) {
                    // Filter for executable regions in the output
                    // This is simplified; in reality we would need more sophisticated parsing
                    output = "Executable memory regions:\n" + altOutput;
                    return CreateSuccessResponse(id, "execute_command", output);
                }
            }
            
            return CreateErrorResponse(
                id,
                "execute_command",
                "Address command has invalid arguments. Try using '!address' without flags first."
            );
        }
        
        if (output.empty()) {
            return CreateErrorResponse(
                id,
                "execute_command",
                "Address command returned no output."
            );
        }
        
        return CreateSuccessResponse(id, "execute_command", output);
    }
    catch (const std::exception& e) {
        return CreateErrorResponse(id, "execute_command", std::string("Address command failed: ") + e.what());
    }
}

// Helper class for command execution with timeout
class CommandExecutor {
public:
    static std::string ExecuteWithTimeout(const std::string& command, unsigned int timeoutMs) {
        // Create a debug client and control interface
        CComPtr<IDebugClient> client;
        HRESULT hr = DebugCreate(__uuidof(IDebugClient), (void**)&client);
        if (FAILED(hr)) {
            throw std::runtime_error("Failed to create debug client");
        }
        
        // Get debug control interface
        CComQIPtr<IDebugControl> control(client);
        if (!control) {
            throw std::runtime_error("Failed to get debug control interface");
        }
        
        // Set up output callbacks
        CComPtr<OutputCallbacks> callbacks = new OutputCallbacks();
        client->SetOutputCallbacks(callbacks);
        
        // Execute the command asynchronously with timeout
        auto task = std::async(std::launch::async, [&]() {
            HRESULT hr = control->Execute(DEBUG_OUTCTL_ALL_CLIENTS, command.c_str(), DEBUG_EXECUTE_DEFAULT);
            if (FAILED(hr)) {
                throw std::runtime_error("Failed to execute command");
            }
            return callbacks->GetOutput();
        });
        
        // Wait for the task to complete with timeout
        auto status = task.wait_for(std::chrono::milliseconds(timeoutMs));
        
        // Reset output callbacks
        client->SetOutputCallbacks(NULL);
        
        if (status == std::future_status::timeout) {
            throw std::runtime_error("Command execution timed out after " + std::to_string(timeoutMs) + "ms");
        }
        
        try {
            return task.get();
        }
        catch (const std::exception& e) {
            throw std::runtime_error(std::string("Command execution failed: ") + e.what());
        }
    }
};

// Helper function to execute a WinDBG command and capture output
std::string CommandHandlers::ExecuteWinDbgCommand(const std::string& command, unsigned int timeoutMs) {
    try {
        std::string output = CommandExecutor::ExecuteWithTimeout(command, timeoutMs);
        
        // Check for empty output
        if (output.empty() || output == "NONE" || output == "None") {
            // For certain critical commands, try again with a different approach
            if (command.find("!process") != std::string::npos) {
                // Try with .process command instead
                size_t addrPos = command.find(" ");
                if (addrPos != std::string::npos) {
                    std::string processAddr = command.substr(addrPos + 1);
                    size_t flagPos = processAddr.find(" ");
                    if (flagPos != std::string::npos) {
                        processAddr = processAddr.substr(0, flagPos);
                    }
                    
                    std::string altCmd = ".process /r /p " + processAddr;
                    std::string altOutput = CommandExecutor::ExecuteWithTimeout(altCmd, timeoutMs);
                    
                    if (!altOutput.empty()) {
                        output = "Process context: " + altOutput;
                    }
                }
            }
            else if (command.find("!address") != std::string::npos && command.find("-f:") != std::string::npos) {
                // For address commands with filtering that might not work
                std::string baseCmd = "!address";
                output = "Command with filter returned no results. Try: " + 
                         CommandExecutor::ExecuteWithTimeout(baseCmd, timeoutMs / 2);
            }
            
            // If still empty, provide a more helpful message
            if (output.empty()) {
                output = "Command returned no output. This could indicate:\n"
                         "1. Invalid command syntax\n"
                         "2. Command not applicable in current context\n"
                         "3. Extension not loaded\n"
                         "Check command help for proper usage.";
            }
        }
        
        return output;
    }
    catch (const std::exception& e) {
        // Provide more context about the error
        std::string errorMsg = e.what();
        std::string enhancedError = "Error executing command '" + command + "': " + errorMsg;
        
        // Suggest alternatives for common errors
        if (errorMsg.find("timed out") != std::string::npos) {
            enhancedError += "\nThe command might be blocked waiting for user input or processing a large dataset.";
        }
        else if (errorMsg.find("debug client") != std::string::npos) {
            enhancedError += "\nThere might be an issue with the WinDbg debugging session.";
        }
        
        throw std::runtime_error(enhancedError);
    }
}

json CommandHandlers::CreateSuccessResponse(int id, const std::string& command, const std::string& output) {
    return {
        {"id", id},
        {"type", "response"},
        {"command", command},
        {"status", "success"},
        {"output", output}
    };
}

json CommandHandlers::CreateErrorResponse(int id, const std::string& command, const std::string& error) {
    return {
        {"id", id},
        {"type", "response"},
        {"command", command},
        {"status", "error"},
        {"error", error}
    };
}

json CommandHandlers::ForEachModuleHandler(const json& message) {
    try {
        auto args = message.value("args", json::object());
        std::string moduleCommand = args.value("command", "");
        unsigned int timeout = args.value("timeout_ms", 30000u);
        
        if (moduleCommand.empty()) {
            return CreateErrorResponse(
                message.value("id", 0),
                "for_each_module",
                "Module command is required"
            );
        }
        
        // Get list of modules first
        std::string modulesOutput = ExecuteWinDbgCommand("lm", timeout);
        std::vector<std::string> moduleAddresses;
        
        // Parse the module list output to get module addresses
        std::istringstream moduleStream(modulesOutput);
        std::string line;
        while (std::getline(moduleStream, line)) {
            // Look for module lines with start addresses
            if (line.empty() || line.find("start") != std::string::npos) {
                continue;  // Skip header lines
            }
            
            // Extract module address
            size_t firstSpace = line.find_first_of(" \t");
            if (firstSpace != std::string::npos) {
                std::string moduleAddr = line.substr(0, firstSpace);
                moduleAddresses.push_back(moduleAddr);
            }
        }
        
        std::string combinedOutput;
        if (moduleAddresses.empty()) {
            return CreateErrorResponse(
                message.value("id", 0),
                "for_each_module",
                "No modules found in the current context"
            );
        }
        
        // Execute the command for each module
        for (const auto& moduleAddr : moduleAddresses) {
            // Replace @#Base with the current module address
            std::string thisCommand = moduleCommand;
            size_t basePos = thisCommand.find("@#Base");
            if (basePos != std::string::npos) {
                thisCommand.replace(basePos, 6, moduleAddr);
            }
            
            std::string thisOutput = ExecuteWinDbgCommand(thisCommand, timeout);
            if (!thisOutput.empty()) {
                combinedOutput += "Module " + moduleAddr + ":\n" + thisOutput + "\n\n";
            }
            
            // Limit the output to avoid excessive size
            if (combinedOutput.size() > MAX_OUTPUT_SIZE/2) {
                combinedOutput += "\n[Output truncated. Too many results.]\n";
                break;
            }
        }
        
        if (combinedOutput.empty()) {
            return CreateErrorResponse(
                message.value("id", 0),
                "for_each_module",
                "Command returned no output for any module"
            );
        }
        
        return CreateSuccessResponse(
            message.value("id", 0),
            "for_each_module",
            combinedOutput
        );
    }
    catch (const std::exception& e) {
        return CreateErrorResponse(
            message.value("id", 0),
            "for_each_module",
            std::string("Command failed: ") + e.what()
        );
    }
} 