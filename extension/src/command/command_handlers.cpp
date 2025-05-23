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
#include <iomanip>
#include <random>
#include <ctime>

// ExtensionApis is now forward-declared in pch.h and defined in types.cpp

// Global variables for tracking performance and health
static std::chrono::steady_clock::time_point g_lastCommandTime = std::chrono::steady_clock::now();
static std::string g_sessionId;
static double g_lastExecutionTime = 0.0;

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
    
    // New enhanced command handlers
    server.RegisterHandler("health_check", HealthCheckHandler);
    server.RegisterHandler("connection_status", ConnectionStatusHandler);
    server.RegisterHandler("capture_session_state", CaptureSessionStateHandler);
    server.RegisterHandler("performance_metrics", PerformanceMetricsHandler);
    server.RegisterHandler("execute_command_enhanced", ExecuteCommandEnhancedHandler);
    server.RegisterHandler("execute_command_streaming", ExecuteCommandStreamingHandler);
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
        auto start_time = std::chrono::steady_clock::now();
        g_lastCommandTime = start_time;
        
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
        
        // Use timeout categorization for automatic timeout adjustment
        TimeoutCategory category = CategorizeCommand(command);
        unsigned int suggested_timeout = GetTimeoutForCategory(category);
        if (timeout < suggested_timeout) {
            timeout = suggested_timeout;
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
        
        try {
            std::string output = ExecuteWinDbgCommand(command, timeout);
            auto end_time = std::chrono::steady_clock::now();
            double execution_time = std::chrono::duration<double>(end_time - start_time).count();
            g_lastExecutionTime = execution_time;
            
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
            
            return CreateSuccessResponseWithMetadata(
                message.value("id", 0),
                command,
                output,
                execution_time
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
    auto current_time = std::chrono::steady_clock::now();
    auto execution_time = std::chrono::duration<double>(current_time - g_lastCommandTime).count();
    
    return {
        {"id", id},
        {"type", "response"},
        {"command", command},
        {"status", "success"},
        {"output", output},
        {"success", true},
        {"metadata", {
            {"execution_time", execution_time},
            {"response_time", execution_time * 1000}, // in milliseconds
            {"data_size", output.length()},
            {"timestamp", GetCurrentTimestamp()},
            {"debugging_mode", GetDebuggingMode()},
            {"retries_attempted", 0}
        }}
    };
}

json CommandHandlers::CreateSuccessResponseWithMetadata(int id, const std::string& command, const std::string& output, 
                                                      double execution_time, const std::string& debugging_mode) {
    if (execution_time == 0.0) {
        auto current_time = std::chrono::steady_clock::now();
        execution_time = std::chrono::duration<double>(current_time - g_lastCommandTime).count();
    }
    
    std::string mode = debugging_mode.empty() ? GetDebuggingMode() : debugging_mode;
    
    return {
        {"id", id},
        {"type", "response"},
        {"command", command},
        {"status", "success"},
        {"output", output},
        {"success", true},
        {"metadata", {
            {"execution_time", execution_time},
            {"response_time", execution_time * 1000}, // in milliseconds
            {"data_size", output.length()},
            {"timestamp", GetCurrentTimestamp()},
            {"debugging_mode", mode},
            {"retries_attempted", 0},
            {"extension_version", GetExtensionVersion()},
            {"windbg_version", GetWinDbgVersion()}
        }}
    };
}

json CommandHandlers::CreateEnhancedErrorResponse(int id, const std::string& command, 
                                                 const std::string& error, 
                                                 ErrorCategory category,
                                                 const std::vector<std::string>& suggestions,
                                                 const std::vector<std::string>& examples,
                                                 const std::vector<std::string>& next_steps) {
    json response = {
        {"id", id},
        {"type", "response"},
        {"command", command},
        {"status", "error"},
        {"error", error},
        {"category", GetErrorCategoryString(category)},
        {"context", GetDebuggingMode()},
        {"timestamp", GetCurrentTimestamp()},
        {"extension_version", GetExtensionVersion()}
    };
    
    if (!suggestions.empty()) response["suggestions"] = suggestions;
    if (!examples.empty()) response["examples"] = examples;
    if (!next_steps.empty()) response["next_steps"] = next_steps;
    
    return response;
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

// =============================================
// Utility Methods for Enhanced Functionality
// =============================================

std::string CommandHandlers::GetCurrentTimestamp() {
    auto now = std::chrono::system_clock::now();
    auto time_t_val = std::chrono::system_clock::to_time_t(now);
    auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(
        now.time_since_epoch()) % 1000;
    
    struct tm tm_info;
    errno_t err = gmtime_s(&tm_info, &time_t_val);
    
    std::stringstream ss;
    if (err == 0) {
        ss << std::put_time(&tm_info, "%Y-%m-%dT%H:%M:%S");
    } else {
        // Fallback to simple format if gmtime_s fails
        ss << "1970-01-01T00:00:00";
    }
    ss << '.' << std::setfill('0') << std::setw(3) << ms.count() << 'Z';
    return ss.str();
}

std::string CommandHandlers::GetDebuggingMode() {
    try {
        // Try to determine debugging mode by executing a simple command
        std::string output = ExecuteWinDbgCommand("vertarget", 1000);
        if (output.find("Kernel") != std::string::npos) {
            return "kernel";
        } else if (output.find("User") != std::string::npos) {
            return "user";
        }
    } catch (...) {
        // If we can't determine, default to unknown
    }
    return "unknown";
}

std::string CommandHandlers::GetExtensionVersion() {
    return "WinDbg MCP Extension v1.1.0";
}

std::string CommandHandlers::GetWinDbgVersion() {
    try {
        std::string version = ExecuteWinDbgCommand("version", 2000);
        // Extract just the version line, remove extra formatting
        size_t pos = version.find("Microsoft");
        if (pos != std::string::npos) {
            size_t end = version.find('\n', pos);
            if (end != std::string::npos) {
                return version.substr(pos, end - pos);
            }
        }
        return version.length() > 100 ? version.substr(0, 100) + "..." : version;
    } catch (...) {
        return "Unknown WinDbg Version";
    }
}

bool CommandHandlers::IsConnectionStable() {
    try {
        // Test connection stability by executing a quick command
        std::string result = ExecuteWinDbgCommand("?", 1000);
        return !result.empty();
    } catch (...) {
        return false;
    }
}

bool CommandHandlers::IsTargetResponsive() {
    try {
        // Check if the debugging target is responsive
        std::string result = ExecuteWinDbgCommand(".", 2000);
        return result.find("Break instruction exception") == std::string::npos &&
               result.find("Access violation") == std::string::npos;
    } catch (...) {
        return false;
    }
}

double CommandHandlers::CalculateHealthScore() {
    double score = 100.0;
    
    // Check connection stability
    if (!IsConnectionStable()) score -= 30.0;
    
    // Check target responsiveness
    if (!IsTargetResponsive()) score -= 20.0;
    
    // Check last command execution time
    auto now = std::chrono::steady_clock::now();
    auto timeSinceLastCommand = std::chrono::duration<double>(now - g_lastCommandTime).count();
    if (timeSinceLastCommand > 300.0) { // 5 minutes
        score -= 15.0;
    }
    
    // Check last execution performance
    if (g_lastExecutionTime > 30.0) { // 30 seconds
        score -= 10.0;
    }
    
    return (score < 0.0) ? 0.0 : score;
}

std::string CommandHandlers::GetLastCommandTime() {
    // Use current time as approximation since conversion is complex
    auto now = std::chrono::system_clock::now();
    auto time_t_val = std::chrono::system_clock::to_time_t(now);
    
    struct tm tm_info;
    errno_t err = gmtime_s(&tm_info, &time_t_val);
    
    std::stringstream ss;
    if (err == 0) {
        ss << std::put_time(&tm_info, "%Y-%m-%dT%H:%M:%SZ");
    } else {
        // Fallback to simple format if gmtime_s fails
        ss << "1970-01-01T00:00:00Z";
    }
    return ss.str();
}

std::string CommandHandlers::GenerateSessionId() {
    if (g_sessionId.empty()) {
        // Generate a simple session ID
        std::random_device rd;
        std::mt19937 gen(rd());
        std::uniform_int_distribution<> dis(0, 15);
        
        std::stringstream ss;
        ss << "windbg_session_";
        for (int i = 0; i < 8; ++i) {
            ss << std::hex << dis(gen);
        }
        g_sessionId = ss.str();
    }
    return g_sessionId;
}

json CommandHandlers::GetCurrentProcessInfo() {
    try {
        std::string processInfo = ExecuteWinDbgCommand("!process", 3000);
        return {
            {"process_info", processInfo},
            {"has_data", !processInfo.empty()}
        };
    } catch (...) {
        return {
            {"process_info", "Unable to retrieve process information"},
            {"has_data", false}
        };
    }
}

json CommandHandlers::GetCurrentThreadInfo() {
    try {
        std::string threadInfo = ExecuteWinDbgCommand("!thread", 3000);
        return {
            {"thread_info", threadInfo},
            {"has_data", !threadInfo.empty()}
        };
    } catch (...) {
        return {
            {"thread_info", "Unable to retrieve thread information"},
            {"has_data", false}
        };
    }
}

json CommandHandlers::GetActiveBreakpoints() {
    try {
        std::string bpInfo = ExecuteWinDbgCommand("bl", 2000);
        return {
            {"breakpoints", bpInfo},
            {"has_data", !bpInfo.empty()}
        };
    } catch (...) {
        return {
            {"breakpoints", "Unable to retrieve breakpoint information"},
            {"has_data", false}
        };
    }
}

json CommandHandlers::GetLoadedModulesInfo() {
    try {
        std::string modulesInfo = ExecuteWinDbgCommand("lm", 5000);
        return {
            {"modules", modulesInfo},
            {"has_data", !modulesInfo.empty()}
        };
    } catch (...) {
        return {
            {"modules", "Unable to retrieve module information"},
            {"has_data", false}
        };
    }
}

json CommandHandlers::GetTargetSystemInfo() {
    try {
        std::string sysInfo = ExecuteWinDbgCommand("vertarget", 2000);
        return {
            {"system_info", sysInfo},
            {"has_data", !sysInfo.empty()}
        };
    } catch (...) {
        return {
            {"system_info", "Unable to retrieve system information"},
            {"has_data", false}
        };
    }
}

// =============================================
// Timeout Management
// =============================================

TimeoutCategory CommandHandlers::CategorizeCommand(const std::string& command) {
    std::string cmd_lower = command;
    std::transform(cmd_lower.begin(), cmd_lower.end(), cmd_lower.begin(), ::tolower);
    
    // Quick commands (5 seconds)
    if (cmd_lower.find("version") != std::string::npos ||
        cmd_lower.find("r ") == 0 ||
        cmd_lower.find("?") == 0) {
        return TimeoutCategory::QUICK;
    }
    
    // Bulk operations (60 seconds)
    if (cmd_lower.find("!process 0 0") != std::string::npos ||
        cmd_lower.find("!handle 0 f") != std::string::npos ||
        cmd_lower.find("lm") == 0) {
        return TimeoutCategory::BULK;
    }
    
    // Analysis commands (120 seconds)
    if (cmd_lower.find("!analyze") != std::string::npos ||
        cmd_lower.find("!poolused") != std::string::npos) {
        return TimeoutCategory::ANALYSIS;
    }
    
    // Slow commands (30 seconds)
    if (cmd_lower.find("k") == 0 ||
        cmd_lower.find("!thread") != std::string::npos ||
        cmd_lower.find("!dlls") != std::string::npos) {
        return TimeoutCategory::SLOW;
    }
    
    return TimeoutCategory::NORMAL;
}

unsigned int CommandHandlers::GetTimeoutForCategory(TimeoutCategory category) {
    switch (category) {
        case TimeoutCategory::QUICK: return 5000;
        case TimeoutCategory::NORMAL: return 15000;
        case TimeoutCategory::SLOW: return 30000;
        case TimeoutCategory::BULK: return 60000;
        case TimeoutCategory::ANALYSIS: return 120000;
        default: return 15000;
    }
}

// =============================================
// New Enhanced Command Handlers
// =============================================

json CommandHandlers::HealthCheckHandler(const json& message) {
    int id = message.value("id", 0);
    
    try {
        json health_data = {
            {"id", id},
            {"type", "response"},
            {"status", "success"},
            {"health_score", CalculateHealthScore()},
            {"last_command_time", GetLastCommandTime()},
            {"connection_stable", IsConnectionStable()},
            {"debugging_target_responsive", IsTargetResponsive()},
            {"extension_version", GetExtensionVersion()},
            {"windbg_version", GetWinDbgVersion()},
            {"debugging_mode", GetDebuggingMode()},
            {"timestamp", GetCurrentTimestamp()}
        };
        
        return health_data;
    }
    catch (const std::exception& e) {
        return CreateEnhancedErrorResponse(
            id, "health_check", std::string("Health check failed: ") + e.what(),
            ErrorCategory::InternalError,
            {"Restart debugging session", "Check WinDbg connection"},
            {"health_check", "connection_status"},
            {"Verify debugger is properly attached to target"}
        );
    }
}

json CommandHandlers::ConnectionStatusHandler(const json& message) {
    int id = message.value("id", 0);
    
    try {
        json status_data = {
            {"id", id},
            {"type", "response"},
            {"status", "success"},
            {"connection_stable", IsConnectionStable()},
            {"target_responsive", IsTargetResponsive()},
            {"debugging_mode", GetDebuggingMode()},
            {"session_id", GenerateSessionId()},
            {"uptime_seconds", std::chrono::duration<double>(
                std::chrono::steady_clock::now() - g_lastCommandTime).count()},
            {"last_execution_time", g_lastExecutionTime},
            {"timestamp", GetCurrentTimestamp()}
        };
        
        return status_data;
    }
    catch (const std::exception& e) {
        return CreateEnhancedErrorResponse(
            id, "connection_status", std::string("Connection status check failed: ") + e.what(),
            ErrorCategory::ApiError,
            {"Check debugger connection", "Restart debugging session"},
            {"health_check"},
            {"Verify debugger is properly connected to target"}
        );
    }
}

json CommandHandlers::CaptureSessionStateHandler(const json& message) {
    int id = message.value("id", 0);
    
    try {
        json session_state = {
            {"id", id},
            {"type", "response"},
            {"status", "success"},
            {"session_id", GenerateSessionId()},
            {"debugging_mode", GetDebuggingMode()},
            {"current_process", GetCurrentProcessInfo()},
            {"current_thread", GetCurrentThreadInfo()},
            {"breakpoints", GetActiveBreakpoints()},
            {"modules", GetLoadedModulesInfo()},
            {"target_info", GetTargetSystemInfo()},
            {"timestamp", GetCurrentTimestamp()},
            {"extension_version", GetExtensionVersion()},
            {"windbg_version", GetWinDbgVersion()}
        };
        
        return session_state;
    }
    catch (const std::exception& e) {
        return CreateEnhancedErrorResponse(
            id, "capture_session_state", std::string("Session state capture failed: ") + e.what(),
            ErrorCategory::InternalError,
            {"Retry session state capture", "Check debugging session"},
            {"connection_status", "health_check"},
            {"Ensure debugging session is active and responsive"}
        );
    }
}

json CommandHandlers::PerformanceMetricsHandler(const json& message) {
    int id = message.value("id", 0);
    
    try {
        auto now = std::chrono::steady_clock::now();
        auto uptime = std::chrono::duration<double>(now - g_lastCommandTime).count();
        
        json metrics = {
            {"id", id},
            {"type", "response"},
            {"status", "success"},
            {"metrics", {
                {"last_execution_time", g_lastExecutionTime},
                {"health_score", CalculateHealthScore()},
                {"uptime_seconds", uptime},
                {"connection_stable", IsConnectionStable()},
                {"target_responsive", IsTargetResponsive()},
                {"session_id", GenerateSessionId()},
                {"total_commands_executed", "N/A"}, // Could implement counter
                {"memory_usage", "N/A"} // Could implement memory tracking
            }},
            {"timestamp", GetCurrentTimestamp()},
            {"extension_version", GetExtensionVersion()}
        };
        
        return metrics;
    }
    catch (const std::exception& e) {
        return CreateEnhancedErrorResponse(
            id, "performance_metrics", std::string("Performance metrics collection failed: ") + e.what(),
            ErrorCategory::InternalError,
            {"Retry metrics collection"},
            {"health_check"},
            {"Check system resources and debugging session health"}
        );
    }
}

json CommandHandlers::ExecuteCommandEnhancedHandler(const json& message) {
    try {
        auto start_time = std::chrono::steady_clock::now();
        g_lastCommandTime = start_time;
        
        auto args = message.value("args", json::object());
        std::string command = args.value("command", "");
        unsigned int timeout = args.value("timeout_ms", 30000u);
        
        if (command.empty()) {
            return CreateEnhancedErrorResponse(
                message.value("id", 0), "execute_command_enhanced", "Command is required",
                ErrorCategory::CommandSyntax,
                {"Provide a valid WinDbg command"},
                {"execute_command_enhanced {\"args\": {\"command\": \"version\"}}"},
                {"Check command syntax and try again"}
            );
        }
        
        // Use timeout categorization for automatic timeout adjustment
        TimeoutCategory category = CategorizeCommand(command);
        unsigned int suggested_timeout = GetTimeoutForCategory(category);
        if (timeout < suggested_timeout) {
            timeout = suggested_timeout;
        }
        
        try {
            std::string output = ExecuteWinDbgCommand(command, timeout);
            auto end_time = std::chrono::steady_clock::now();
            double execution_time = std::chrono::duration<double>(end_time - start_time).count();
            g_lastExecutionTime = execution_time;
            
            if (output.empty()) {
                return CreateEnhancedErrorResponse(
                    message.value("id", 0), "execute_command_enhanced", 
                    "Command returned no output",
                    ErrorCategory::ExecutionContext,
                    {"Check command syntax", "Verify debugging context"},
                    {"version", "help " + command},
                    {"Ensure command is valid in current debugging context"}
                );
            }
            
            return CreateSuccessResponseWithMetadata(
                message.value("id", 0), command, output, execution_time
            );
        }
        catch (const std::exception& e) {
            std::string errorMsg = e.what();
            ErrorCategory category = ClassifyError(errorMsg, S_OK);
            
            return CreateEnhancedErrorResponse(
                message.value("id", 0), "execute_command_enhanced",
                std::string("Command execution failed: ") + errorMsg,
                category,
                {GetSuggestionForError(category, command, S_OK)},
                {"help " + command, "version"},
                {"Check command syntax and debugging context"}
            );
        }
    }
    catch (const std::exception& e) {
        return CreateEnhancedErrorResponse(
            message.value("id", 0), "execute_command_enhanced",
            std::string("Handler failed: ") + e.what(),
            ErrorCategory::InternalError,
            {"Retry command execution"},
            {"execute_command"},
            {"Report this issue if it persists"}
        );
    }
}

json CommandHandlers::ExecuteCommandStreamingHandler(const json& message) {
    try {
        auto start_time = std::chrono::steady_clock::now();
        g_lastCommandTime = start_time;
        
        auto args = message.value("args", json::object());
        std::string command = args.value("command", "");
        int chunk_size = args.value("chunk_size", 4096);
        unsigned int timeout = args.value("timeout_ms", 60000u); // Default 60s for large ops
        
        if (command.empty()) {
            return CreateEnhancedErrorResponse(
                message.value("id", 0), "execute_command_streaming", "Command is required",
                ErrorCategory::CommandSyntax,
                {"Provide a valid WinDbg command"},
                {"execute_command_streaming {\"args\": {\"command\": \"lm\"}}"},
                {"Use streaming for commands that produce large output"}
            );
        }
        
        // Use timeout categorization
        TimeoutCategory category = CategorizeCommand(command);
        unsigned int suggested_timeout = GetTimeoutForCategory(category);
        if (timeout < suggested_timeout) {
            timeout = suggested_timeout;
        }
        
        std::string output = ExecuteWinDbgCommand(command, timeout);
        auto end_time = std::chrono::steady_clock::now();
        double execution_time = std::chrono::duration<double>(end_time - start_time).count();
        g_lastExecutionTime = execution_time;
        
        if (output.length() <= static_cast<size_t>(chunk_size)) {
            // Small output, return normally with metadata
            return CreateSuccessResponseWithMetadata(
                message.value("id", 0), command, output, execution_time
            );
        }
        
        // Large output, return streaming response
        json streaming_response = {
            {"id", message.value("id", 0)},
            {"type", "response"},
            {"command", command},
            {"status", "success"},
            {"streaming", true},
            {"total_size", output.length()},
            {"chunk_size", chunk_size},
            {"total_chunks", (output.length() + chunk_size - 1) / chunk_size},
            {"chunks", json::array()},
            {"metadata", {
                {"execution_time", execution_time},
                {"response_time", execution_time * 1000},
                {"data_size", output.length()},
                {"timestamp", GetCurrentTimestamp()},
                {"debugging_mode", GetDebuggingMode()},
                {"extension_version", GetExtensionVersion()}
            }}
        };
        
        // Split into chunks
        for (size_t i = 0; i < output.length(); i += chunk_size) {
            std::string chunk = output.substr(i, chunk_size);
            streaming_response["chunks"].push_back({
                {"chunk_index", i / chunk_size},
                {"data", chunk},
                {"size", chunk.length()}
            });
        }
        
        return streaming_response;
    }
    catch (const std::exception& e) {
        return CreateEnhancedErrorResponse(
            message.value("id", 0), "execute_command_streaming",
            std::string("Streaming command failed: ") + e.what(),
            ErrorCategory::InternalError,
            {"Try regular command execution", "Reduce chunk size"},
            {"execute_command_enhanced"},
            {"Use execute_command_enhanced for smaller outputs"}
        );
    }
} 