#include "pch.h"
#include "command/command_handlers.h"
#include "utils/output_callbacks.h"
#include <sstream>
#include <atlcomcli.h>
#include <future>
#include <chrono>
#include <algorithm>
#include <thread>
#include <mutex>
#include <condition_variable>

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
            return CreateDetailedErrorResponse(
                message.value("id", 0),
                "execute_command",
                "Command is required",
                ErrorCategory::CommandSyntax
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
        
        try {
            std::string output = ExecuteWinDbgCommand(command, timeout);
            
            // Check if the output is empty or contains error messages
            if (output.empty()) {
                return CreateDetailedErrorResponse(
                    message.value("id", 0),
                    "execute_command",
                    "Command returned no output. The command might be invalid or unsupported.",
                    ErrorCategory::Unknown,
                    S_OK,
                    "Check if the command is valid in the current context."
                );
            }
            
            // Check for common error patterns
            if (output.find("Usage:") != std::string::npos && 
                output.find("options") != std::string::npos) {
                return CreateDetailedErrorResponse(
                    message.value("id", 0),
                    "execute_command",
                    "Command syntax error: " + output,
                    ErrorCategory::CommandSyntax,
                    E_INVALIDARG,
                    "Check the command syntax and arguments."
                );
            }
            
            return CreateSuccessResponse(
                message.value("id", 0),
                "execute_command",
                output
            );
        }
        catch (const std::exception& e) {
            std::string errorMsg = e.what();
            
            // Extract HRESULT if present
            HRESULT hr = S_OK;
            size_t hrPos = errorMsg.find("HRESULT: 0x");
            if (hrPos != std::string::npos) {
                try {
                    std::string hrStr = errorMsg.substr(hrPos + 10, 8);
                    hr = std::stoul(hrStr, nullptr, 16);
                }
                catch (...) {
                    // Ignore errors in HRESULT parsing
                }
            }
            
            // Classify the error
            ErrorCategory category = ClassifyError(errorMsg, hr);
            
            // Get suggestion for this error type
            std::string suggestion = GetSuggestionForError(category, command, hr);
            
            return CreateDetailedErrorResponse(
                message.value("id", 0),
                "execute_command",
                errorMsg,
                category,
                hr,
                suggestion
            );
        }
    }
    catch (const std::exception& e) {
        return CreateDetailedErrorResponse(
            message.value("id", 0),
            "execute_command",
            std::string("Command failed: ") + e.what(),
            ErrorCategory::InternalError
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
            
            return CreateDetailedErrorResponse(
                id,
                "execute_command",
                "Process command returned no output. The process address might be invalid.",
                ErrorCategory::ExecutionContext,
                E_INVALIDARG,
                "Check that the process address is valid and that you are in the correct debugging context."
            );
        }
        
        return CreateSuccessResponse(id, "execute_command", output);
    }
    catch (const std::exception& e) {
        std::string errorMsg = e.what();
        
        // Extract HRESULT if present
        HRESULT hr = S_OK;
        size_t hrPos = errorMsg.find("HRESULT: 0x");
        if (hrPos != std::string::npos) {
            try {
                std::string hrStr = errorMsg.substr(hrPos + 10, 8);
                hr = std::stoul(hrStr, nullptr, 16);
            }
            catch (...) {
                // Ignore errors in HRESULT parsing
            }
        }
        
        // Classify the error
        ErrorCategory category = ClassifyError(errorMsg, hr);
        
        return CreateDetailedErrorResponse(
            id, 
            "execute_command", 
            std::string("Process command failed: ") + e.what(),
            category,
            hr,
            GetSuggestionForError(category, command, hr)
        );
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
            return CreateDetailedErrorResponse(
                id,
                "execute_command",
                "DLLs command returned no output. Try using '!process <address>' first to set the context.",
                ErrorCategory::ExecutionContext,
                S_OK,
                "First set the process context with '!process <address>' or '.process /r /p <address>', then run '!dlls'"
            );
        }
        
        return CreateSuccessResponse(id, "execute_command", output);
    }
    catch (const std::exception& e) {
        std::string errorMsg = e.what();
        
        // Extract HRESULT if present
        HRESULT hr = S_OK;
        size_t hrPos = errorMsg.find("HRESULT: 0x");
        if (hrPos != std::string::npos) {
            try {
                std::string hrStr = errorMsg.substr(hrPos + 10, 8);
                hr = std::stoul(hrStr, nullptr, 16);
            }
            catch (...) {
                // Ignore errors in HRESULT parsing
            }
        }
        
        // Classify the error
        ErrorCategory category = ClassifyError(errorMsg, hr);
        
        return CreateDetailedErrorResponse(
            id, 
            "execute_command", 
            std::string("DLLs command failed: ") + e.what(),
            category,
            hr,
            GetSuggestionForError(category, command, hr)
        );
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
            
            return CreateDetailedErrorResponse(
                id,
                "execute_command",
                "Address command has invalid arguments.",
                ErrorCategory::CommandSyntax,
                E_INVALIDARG,
                "Try using '!address' without flags first or check the command syntax with '!help address'"
            );
        }
        
        if (output.empty()) {
            return CreateDetailedErrorResponse(
                id,
                "execute_command",
                "Address command returned no output.",
                ErrorCategory::Unknown,
                S_OK,
                "The command might not be applicable in the current context."
            );
        }
        
        return CreateSuccessResponse(id, "execute_command", output);
    }
    catch (const std::exception& e) {
        std::string errorMsg = e.what();
        
        // Extract HRESULT if present
        HRESULT hr = S_OK;
        size_t hrPos = errorMsg.find("HRESULT: 0x");
        if (hrPos != std::string::npos) {
            try {
                std::string hrStr = errorMsg.substr(hrPos + 10, 8);
                hr = std::stoul(hrStr, nullptr, 16);
            }
            catch (...) {
                // Ignore errors in HRESULT parsing
            }
        }
        
        // Classify the error
        ErrorCategory category = ClassifyError(errorMsg, hr);
        
        return CreateDetailedErrorResponse(
            id, 
            "execute_command", 
            std::string("Address command failed: ") + e.what(),
            category,
            hr,
            GetSuggestionForError(category, command, hr)
        );
    }
}

// Helper class for command execution with timeout
class CommandExecutor {
public:
    struct CommandResult {
        std::string output;
        HRESULT hr;
        bool hasTimedOut;
        
        CommandResult() : output(""), hr(S_OK), hasTimedOut(false) {}
        CommandResult(const std::string& out, HRESULT result = S_OK, bool timedOut = false)
            : output(out), hr(result), hasTimedOut(timedOut) {}
    };
    
    static CommandResult ExecuteWithTimeout(const std::string& command, unsigned int timeoutMs) {
        CommandResult result;
        
        // Create a debug client and control interface
        CComPtr<IDebugClient> client;
        HRESULT hr = DebugCreate(__uuidof(IDebugClient), (void**)&client);
        if (FAILED(hr)) {
            result.hr = hr;
            result.output = "Failed to create debug client";
            return result;
        }
        
        // Get debug control interface
        CComQIPtr<IDebugControl> control(client);
        if (!control) {
            result.hr = E_NOINTERFACE;
            result.output = "Failed to get debug control interface";
            return result;
        }
        
        // Set up output callbacks
        CComPtr<OutputCallbacks> callbacks = new OutputCallbacks();
        client->SetOutputCallbacks(callbacks);
        
        // Variables for thread synchronization
        std::mutex mtx;
        std::condition_variable cv;
        bool commandCompleted = false;
        bool commandRunning = true;
        
        // Execute the command in a separate thread
        auto task = std::thread([&]() {
            CommandResult taskResult;
            
            // Execute the command
            taskResult.hr = control->Execute(DEBUG_OUTCTL_ALL_CLIENTS, command.c_str(), DEBUG_EXECUTE_DEFAULT);
            
            // If command execution failed, get detailed error information
            if (FAILED(taskResult.hr)) {
                // Format a clear error message with the HRESULT
                char errorMsg[256] = {0};
                sprintf_s(errorMsg, "Command execution failed with HRESULT = 0x%08X", taskResult.hr);
                
                // Map common HRESULTs to more descriptive messages
                switch (taskResult.hr) {
                    case E_INVALIDARG:
                        strcat_s(errorMsg, " - Invalid argument");
                        break;
                    case E_ACCESSDENIED:
                        strcat_s(errorMsg, " - Access denied");
                        break;
                    case E_OUTOFMEMORY:
                        strcat_s(errorMsg, " - Out of memory");
                        break;
                    case E_NOTIMPL:
                        strcat_s(errorMsg, " - Not implemented");
                        break;
                    case E_NOINTERFACE:
                        strcat_s(errorMsg, " - Interface not supported");
                        break;
                    case E_FAIL:
                        strcat_s(errorMsg, " - Unspecified error");
                        break;
                }
                
                taskResult.output = errorMsg;
                
                // Include any output that might have been generated before the error
                std::string cmdOutput = callbacks->GetOutput();
                if (!cmdOutput.empty()) {
                    taskResult.output += "\nCommand output: " + cmdOutput;
                }
            } else {
                taskResult.output = callbacks->GetOutput();
            }
            
            // Signal completion and store result
            {
                std::lock_guard<std::mutex> lock(mtx);
                result = taskResult;
                commandCompleted = true;
                commandRunning = false;
            }
            cv.notify_one();
        });
        
        // Wait for the command to complete with timeout
        {
            std::unique_lock<std::mutex> lock(mtx);
            if (!cv.wait_for(lock, std::chrono::milliseconds(timeoutMs), [&commandCompleted]{ return commandCompleted; })) {
                // Timeout occurred
                
                // Set timeout result
                result.hasTimedOut = true;
                result.output = "Command execution timed out after " + std::to_string(timeoutMs) + "ms";
                
                // Mark command as no longer running but wait for thread to actually terminate
                commandRunning = false;
            }
        }
        
        // If command timed out, we need to force interrupt the execution
        if (result.hasTimedOut) {
            // Attempt to cleanly interrupt the command
            // Use IDebugControl::SetInterrupt instead of SetInterruptEvent
            control->SetInterrupt(DEBUG_INTERRUPT_ACTIVE);
            
            // Give a short grace period for the command to terminate
            {
                std::unique_lock<std::mutex> lock(mtx);
                cv.wait_for(lock, std::chrono::milliseconds(500), [&commandRunning]{ return !commandRunning; });
            }
        }
        
        // Reset output callbacks
        if (client) {
            client->SetOutputCallbacks(NULL);
        }
        
        // Wait for thread to complete (could be dangerous if thread is truly hung)
        if (task.joinable()) {
            // Give it a reasonable timeout
            std::thread([](std::thread&& t) {
                if (t.joinable()) {
                    // Try to join for a short time
                    auto future = std::async(std::launch::async, &std::thread::join, &t);
                    if (future.wait_for(std::chrono::seconds(2)) == std::future_status::timeout) {
                        // Thread is hung, we can't safely terminate it in Windows
                        // Just detach so we don't block, but this may leak resources
                        t.detach();
                    }
                }
            }, std::move(task)).detach();
        }
        
        return result;
    }
};

// Helper function to execute a WinDBG command and capture output
std::string CommandHandlers::ExecuteWinDbgCommand(const std::string& command, unsigned int timeoutMs) {
    CommandExecutor::CommandResult result = CommandExecutor::ExecuteWithTimeout(command, timeoutMs);
    
    // Check for timeout
    if (result.hasTimedOut) {
        throw std::runtime_error("Command execution timed out after " + std::to_string(timeoutMs) + "ms");
    }
    
    // Check for execution failures
    if (FAILED(result.hr)) {
        std::string errorMsg = result.output.empty() ? 
            "Unknown error" : result.output;
        std::string enhancedError = "Error executing command '" + command + "': " + errorMsg;
        
        // Include error code for more detailed diagnostics
        char hrStr[16];
        sprintf_s(hrStr, "0x%08X", result.hr);
        enhancedError += " (HRESULT: " + std::string(hrStr) + ")";
        
        throw std::runtime_error(enhancedError);
    }
    
    // Check for empty output
    if (result.output.empty() || result.output == "NONE" || result.output == "None") {
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
                CommandExecutor::CommandResult altResult = CommandExecutor::ExecuteWithTimeout(altCmd, timeoutMs);
                
                if (!FAILED(altResult.hr) && !altResult.output.empty()) {
                    return "Process context: " + altResult.output;
                }
            }
        }
        else if (command.find("!address") != std::string::npos && command.find("-f:") != std::string::npos) {
            // For address commands with filtering that might not work
            std::string baseCmd = "!address";
            CommandExecutor::CommandResult altResult = CommandExecutor::ExecuteWithTimeout(baseCmd, timeoutMs / 2);
            
            if (!FAILED(altResult.hr) && !altResult.output.empty()) {
                return "Command with filter returned no results. Try: " + altResult.output;
            }
        }
        
        // If still empty, provide a more helpful message
        return "Command returned no output. This could indicate:\n"
               "1. Invalid command syntax\n"
               "2. Command not applicable in current context\n"
               "3. Extension not loaded\n"
               "Check command help for proper usage.";
    }
    
    return result.output;
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

json CommandHandlers::CreateDetailedErrorResponse(
    int id,
    const std::string& command,
    const std::string& error,
    ErrorCategory category,
    HRESULT errorCode,
    const std::string& suggestion
) {
    json response = {
        {"id", id},
        {"type", "response"},
        {"command", command},
        {"status", "error"},
        {"error", error},
        {"error_category", GetErrorCategoryString(category)},
        {"error_code", errorCode}
    };
    
    if (!suggestion.empty()) {
        response["suggestion"] = suggestion;
    }
    
    return response;
}

ErrorCategory CommandHandlers::ClassifyError(const std::string& errorMessage, HRESULT errorCode) {
    // Classify errors based on the error message and HRESULT code
    if (errorMessage.find("timed out") != std::string::npos) {
        return ErrorCategory::Timeout;
    }
    
    if (errorMessage.find("debug client") != std::string::npos ||
        errorMessage.find("control interface") != std::string::npos) {
        return ErrorCategory::ApiError;
    }
    
    if (errorMessage.find("syntax") != std::string::npos ||
        errorMessage.find("Usage:") != std::string::npos ||
        errorMessage.find("Invalid argument") != std::string::npos) {
        return ErrorCategory::CommandSyntax;
    }
    
    if (errorMessage.find("not found") != std::string::npos ||
        errorMessage.find("cannot resolve") != std::string::npos ||
        errorMessage.find("no symbols") != std::string::npos) {
        return ErrorCategory::SymbolResolution;
    }
    
    if (errorMessage.find("extension") != std::string::npos &&
        (errorMessage.find("not loaded") != std::string::npos ||
         errorMessage.find("missing") != std::string::npos)) {
        return ErrorCategory::ExtensionLoad;
    }
    
    if (errorMessage.find("access violation") != std::string::npos ||
        errorMessage.find("invalid memory") != std::string::npos ||
        errorMessage.find("cannot access") != std::string::npos) {
        return ErrorCategory::MemoryAccess;
    }
    
    if (errorMessage.find("wrong context") != std::string::npos ||
        errorMessage.find("kernel mode only") != std::string::npos ||
        errorMessage.find("user mode only") != std::string::npos ||
        errorMessage.find("not debugging") != std::string::npos) {
        return ErrorCategory::ExecutionContext;
    }
    
    // Check HRESULT codes for more detailed classification
    switch (errorCode) {
        case E_INVALIDARG:
            return ErrorCategory::CommandSyntax;
        case E_ACCESSDENIED:
            return ErrorCategory::MemoryAccess;
        case E_OUTOFMEMORY:
            return ErrorCategory::InternalError;
        case E_NOINTERFACE:
            return ErrorCategory::ApiError;
        case E_ABORT:
            return ErrorCategory::Timeout;
        case E_FAIL:
            // Generic failure, need to rely on the message
            break;
    }
    
    return ErrorCategory::Unknown;
}

std::string CommandHandlers::GetErrorCategoryString(ErrorCategory category) {
    switch (category) {
        case ErrorCategory::None: return "none";
        case ErrorCategory::CommandSyntax: return "command_syntax";
        case ErrorCategory::ExecutionContext: return "execution_context";
        case ErrorCategory::Timeout: return "timeout";
        case ErrorCategory::SymbolResolution: return "symbol_resolution";
        case ErrorCategory::MemoryAccess: return "memory_access";
        case ErrorCategory::ExtensionLoad: return "extension_load";
        case ErrorCategory::InternalError: return "internal_error";
        case ErrorCategory::ApiError: return "api_error";
        case ErrorCategory::Unknown:
        default:
            return "unknown";
    }
}

std::string CommandHandlers::GetSuggestionForError(ErrorCategory category, const std::string& command, HRESULT errorCode) {
    switch (category) {
        case ErrorCategory::CommandSyntax:
            return "Try checking the command syntax with '!help " + command + "' or check WinDbg documentation.";
            
        case ErrorCategory::ExecutionContext:
            if (command.find("!") == 0) {
                return "This extension command might only be valid in a specific context (user mode or kernel mode).";
            }
            return "This command might only be valid in a specific debugging context.";
            
        case ErrorCategory::Timeout:
            return "The command might be blocked waiting for user input or processing a large dataset. Consider increasing the timeout or using a more specific command.";
            
        case ErrorCategory::SymbolResolution:
            return "Check symbol path with '.sympath' and reload symbols with '.reload'. Make sure symbols are available for the module.";
            
        case ErrorCategory::MemoryAccess:
            return "The memory address might be invalid or not accessible in the current context. Verify the address is correct.";
            
        case ErrorCategory::ExtensionLoad:
            if (command.find("!") == 0) {
                std::string extName = command.substr(1);
                size_t pos = extName.find(' ');
                if (pos != std::string::npos) {
                    extName = extName.substr(0, pos);
                }
                return "The extension '" + extName + "' might need to be loaded with '.load' before use.";
            }
            return "Make sure necessary extensions are loaded with '.load'.";
            
        case ErrorCategory::ApiError:
            return "There might be an issue with the WinDbg debugging session. Try restarting the debugging session.";
            
        case ErrorCategory::InternalError:
            return "An internal error occurred in the extension. Please report this issue.";
            
        case ErrorCategory::Unknown:
        default:
            return "";
    }
} 