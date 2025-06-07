#include "pch.h"
#include "command/enhanced_command_handlers.h"
#include "command/command_utilities.h"
#include "../ipc/mcp_server.h"  // Include MCPServer definition
#include <ctime>  // For std::time and gmtime_s
#include <algorithm>  // For std::max and std::min
#include <sstream>  // For std::istringstream

void EnhancedCommandHandlers::RegisterHandlers(MCPServer& server) {
    // Register enhanced command handlers
    server.RegisterHandler("execute_command", ExecuteCommandHandler);
    server.RegisterHandler("execute_command_enhanced", ExecuteCommandEnhancedHandler);
    server.RegisterHandler("execute_command_streaming", ExecuteCommandStreamingHandler);
    server.RegisterHandler("for_each_module", ForEachModuleHandler);
    
    // Register unified callback enumeration handler - NEW
    server.RegisterHandler("mcp_list_callbacks", UnifiedCallbackEnumerationHandler);
    

}

json EnhancedCommandHandlers::ExecuteCommandHandler(const json& message) {
    try {
        auto start_time = std::chrono::steady_clock::now();
        
        auto args = message.value("args", json::object());
        std::string command = args.value("command", "");
        unsigned int timeout = args.value("timeout_ms", 30000u);  // Increased default timeout to 30 seconds
        
        if (command.empty()) {
            return CommandUtilities::CreateDetailedErrorResponse(
                message.value("id", 0),
                "execute_command",
                "Command is required",
                ErrorCategory::CommandSyntax
            );
        }
        
        // Use timeout categorization for automatic timeout adjustment
        TimeoutCategory category = CommandUtilities::CategorizeCommand(command);
        unsigned int suggested_timeout = CommandUtilities::GetTimeoutForCategory(category);
        if (timeout < suggested_timeout) {
            timeout = suggested_timeout;
        }
        
        // Normalize command for prefix checking
        auto normalizeCommand = [](const std::string& cmd) -> std::string {
            std::string normalized = cmd;
            // Trim leading whitespace
            normalized.erase(0, normalized.find_first_not_of(" \t\n\r\f\v"));
            // Convert to lowercase
            std::transform(normalized.begin(), normalized.end(), normalized.begin(), ::tolower);
            return normalized;
        };
        
        std::string normalizedCmd = normalizeCommand(command);
        
        // Special handling for specific commands that need custom processing
        if (normalizedCmd.find("!process") == 0) {
            // Process-specific handling
            return HandleProcessCommand(message.value("id", 0), command, timeout);
        }
        else if (normalizedCmd.find("!dlls") == 0) {
            // DLLs-specific handling
            return HandleDllsCommand(message.value("id", 0), command, timeout);
        }
        else if (normalizedCmd.find("!address") == 0) {
            // Address-specific handling
            return HandleAddressCommand(message.value("id", 0), command, timeout);
        }
        
        try {
            std::string output = CommandUtilities::ExecuteWinDbgCommand(command, timeout);
            auto end_time = std::chrono::steady_clock::now();
            double execution_time = std::chrono::duration<double>(end_time - start_time).count();
            CommandUtilities::UpdateGlobalPerformanceMetrics(execution_time);
            
            // Check if this is a memory edit command that normally returns no output on success
            bool isMemoryEditCommand = false;
            std::string trimmedCommand = command;
            // Remove leading whitespace
            trimmedCommand.erase(0, trimmedCommand.find_first_not_of(" \t\n\r\f\v"));
            
            // Check for memory edit commands (eq, ed, eb, ew, etc.)
            if (trimmedCommand.length() >= 2) {
                std::string cmdPrefix = trimmedCommand.substr(0, 2);
                if (cmdPrefix == "eq" || cmdPrefix == "ed" || cmdPrefix == "eb" || 
                    cmdPrefix == "ew" || cmdPrefix == "ea" || cmdPrefix == "eu") {
                    // Verify it's actually a memory edit command (has address parameter)
                    size_t spacePos = trimmedCommand.find(' ');
                    if (spacePos != std::string::npos && spacePos == 2) {
                        isMemoryEditCommand = true;
                    }
                }
            }
            
            // Check if the output is empty or contains error messages
            if (output.empty() && !isMemoryEditCommand) {
                return CommandUtilities::CreateDetailedErrorResponse(
                    message.value("id", 0),
                    "execute_command",
                    "Command returned no output. The command might be invalid or unsupported.",
                    ErrorCategory::Unknown,
                    S_OK,
                    "Check if the command is valid in the current context."
                );
            }
            
            // For memory edit commands, empty output means success
            if (output.empty() && isMemoryEditCommand) {
                output = "Memory edit command completed successfully.";
            }
            
            return CommandUtilities::CreateSuccessResponseWithMetadata(
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
            ErrorCategory category = CommandUtilities::ClassifyError(errorMsg, hr);
            
            // Get suggestion for this error type
            std::string suggestion = CommandUtilities::GetSuggestionForError(category, command, hr);
            
            return CommandUtilities::CreateDetailedErrorResponse(
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
        return CommandUtilities::CreateDetailedErrorResponse(
            message.value("id", 0),
            "execute_command",
            std::string("Command failed: ") + e.what(),
            ErrorCategory::InternalError
        );
    }
}

json EnhancedCommandHandlers::ExecuteCommandEnhancedHandler(const json& message) {
    try {
        auto args = message.value("args", json::object());
        std::string command = args.value("command", "");
        unsigned int timeout = args.value("timeout_ms", 30000u);
        bool includeMetadata = args.value("include_metadata", true);
        
        if (command.empty()) {
            return CommandUtilities::CreateDetailedErrorResponse(
                message.value("id", 0),
                "execute_command_enhanced",
                "Command is required",
                ErrorCategory::CommandSyntax
            );
        }
        
        auto start_time = std::chrono::steady_clock::now();
        
        try {
            std::string output = CommandUtilities::ExecuteWinDbgCommand(command, timeout);
            auto end_time = std::chrono::steady_clock::now();
            double execution_time = std::chrono::duration<double>(end_time - start_time).count();
            CommandUtilities::UpdateGlobalPerformanceMetrics(execution_time);
            
            if (includeMetadata) {
                return CommandUtilities::CreateSuccessResponseWithMetadata(
                    message.value("id", 0),
                    command,
                    output,
                    execution_time
                );
            } else {
                return CommandUtilities::CreateSuccessResponse(
                    message.value("id", 0),
                    command,
                    output
                );
            }
        }
        catch (const std::exception& e) {
            std::string errorMsg = e.what();
            HRESULT hr = S_OK;
            
            // Extract HRESULT if present
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
            
            ErrorCategory category = CommandUtilities::ClassifyError(errorMsg, hr);
            std::string suggestion = CommandUtilities::GetSuggestionForError(category, command, hr);
            
            return CommandUtilities::CreateDetailedErrorResponse(
                message.value("id", 0),
                "execute_command_enhanced",
                errorMsg,
                category,
                hr,
                suggestion
            );
        }
    }
    catch (const std::exception& e) {
        return CommandUtilities::CreateDetailedErrorResponse(
            message.value("id", 0),
            "execute_command_enhanced",
            std::string("Enhanced command execution failed: ") + e.what(),
            ErrorCategory::InternalError
        );
    }
}

json EnhancedCommandHandlers::ExecuteCommandStreamingHandler(const json& message) {
    try {
        auto args = message.value("args", json::object());
        std::string command = args.value("command", "");
        unsigned int timeout = args.value("timeout_ms", 60000u);  // Default 60 seconds for streaming
        
        if (command.empty()) {
            return CommandUtilities::CreateDetailedErrorResponse(
                message.value("id", 0),
                "execute_command_streaming",
                "Command is required",
                ErrorCategory::CommandSyntax
            );
        }
        
        // For streaming commands, we'll execute and return with streaming indicators
        try {
            auto start_time = std::chrono::steady_clock::now();
            std::string output = CommandUtilities::ExecuteWinDbgCommand(command, timeout);
            auto end_time = std::chrono::steady_clock::now();
            double execution_time = std::chrono::duration<double>(end_time - start_time).count();
            CommandUtilities::UpdateGlobalPerformanceMetrics(execution_time);
            
            // Determine if the output is large enough to benefit from streaming
            size_t outputSize = output.length();
            bool shouldStream = outputSize > 50000;  // 50KB threshold
            
            json response = CommandUtilities::CreateSuccessResponseWithMetadata(
                message.value("id", 0),
                command,
                output,
                execution_time
            );
            
            // Add streaming metadata
            response["streaming"] = {
                {"enabled", shouldStream},
                {"output_size", outputSize},
                {"chunk_count", shouldStream ? (outputSize / 4096) + 1 : 1}
            };
            
            return response;
        }
        catch (const std::exception& e) {
            std::string errorMsg = e.what();
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
            
            ErrorCategory category = CommandUtilities::ClassifyError(errorMsg, hr);
            std::string suggestion = CommandUtilities::GetSuggestionForError(category, command, hr);
            
            return CommandUtilities::CreateDetailedErrorResponse(
                message.value("id", 0),
                "execute_command_streaming",
                errorMsg,
                category,
                hr,
                suggestion
            );
        }
    }
    catch (const std::exception& e) {
        return CommandUtilities::CreateDetailedErrorResponse(
            message.value("id", 0),
            "execute_command_streaming",
            std::string("Streaming command execution failed: ") + e.what(),
            ErrorCategory::InternalError
        );
    }
}

json EnhancedCommandHandlers::ForEachModuleHandler(const json& message) {
    try {
        auto args = message.value("args", json::object());
        std::string moduleCommand = args.value("command", "");
        unsigned int timeout = args.value("timeout_ms", 60000u);  // Default 60 seconds for bulk operations
        
        if (moduleCommand.empty()) {
            return CommandUtilities::CreateDetailedErrorResponse(
                message.value("id", 0),
                "for_each_module",
                "Module command is required",
                ErrorCategory::CommandSyntax
            );
        }
        
        try {
            // Build the for_each_module command
            std::string command = "!for_each_module " + moduleCommand;
            
            auto start_time = std::chrono::steady_clock::now();
            std::string output = CommandUtilities::ExecuteWinDbgCommand(command, timeout);
            auto end_time = std::chrono::steady_clock::now();
            double execution_time = std::chrono::duration<double>(end_time - start_time).count();
            CommandUtilities::UpdateGlobalPerformanceMetrics(execution_time);
            
            return CommandUtilities::CreateSuccessResponseWithMetadata(
                message.value("id", 0),
                command,
                output,
                execution_time
            );
        }
        catch (const std::exception& e) {
            std::string errorMsg = e.what();
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
            
            ErrorCategory category = CommandUtilities::ClassifyError(errorMsg, hr);
            std::string suggestion = CommandUtilities::GetSuggestionForError(category, moduleCommand, hr);
            
            return CommandUtilities::CreateDetailedErrorResponse(
                message.value("id", 0),
                "for_each_module",
                errorMsg,
                category,
                hr,
                suggestion
            );
        }
    }
    catch (const std::exception& e) {
        return CommandUtilities::CreateDetailedErrorResponse(
            message.value("id", 0),
            "for_each_module",
            std::string("For each module command failed: ") + e.what(),
            ErrorCategory::InternalError
        );
    }
}

json EnhancedCommandHandlers::UnifiedCallbackEnumerationHandler(const json& message) {
    std::vector<std::string> thirdPartyDrivers;  // Declare this before the lambda
    
    // Helper function to parse callback output
    auto parseCallbackList = [&](const std::string& output, const std::vector<std::string>& coreModules = {"nt", "hal", "ntoskrnl", "ndis", "tcpip"}) -> std::pair<json, int> {
        json parsedCallbacks = json::array();
        std::istringstream iss(output);
        std::string line;
        int callbackCount = 0;
        
        while (std::getline(iss, line)) {
            if (line.find("+0x") != std::string::npos && line.find("!") != std::string::npos) {
                json callbackEntry;
                callbackEntry["address"] = line.substr(0, line.find(" "));
                
                size_t moduleStart = line.find("!");
                if (moduleStart != std::string::npos) {
                    size_t moduleEnd = line.find("+", moduleStart);
                    if (moduleEnd == std::string::npos) {
                        moduleEnd = line.find(" ", moduleStart);
                    }
                    std::string moduleName = line.substr(0, moduleStart);
                    moduleName = moduleName.substr(moduleName.find_last_of(" ") + 1);
                    
                    callbackEntry["module"] = moduleName;
                    callbackEntry["function"] = line.substr(moduleStart + 1);
                    
                    // Check if it's a third-party driver (not in core modules list)
                    bool isThirdParty = std::find(coreModules.begin(), coreModules.end(), moduleName) == coreModules.end();
                    callbackEntry["third_party"] = isThirdParty;
                    
                    if (isThirdParty) {
                        thirdPartyDrivers.push_back(moduleName);
                    }
                }
                
                callbackEntry["full_line"] = line;
                parsedCallbacks.push_back(callbackEntry);
                callbackCount++;
            }
        }
        
        return std::make_pair(parsedCallbacks, callbackCount);
    };

    try {
        auto start_time = std::chrono::steady_clock::now();
        
        auto args = message.value("args", json::object());
        unsigned int timeout = args.value("timeout_ms", 60000u);  // Default 60 seconds for comprehensive enumeration
        bool include_addresses = args.value("include_addresses", true);
        bool resolve_modules = args.value("resolve_modules", true);
        std::string filter_type = args.value("callback_type", "all");  // all, process, thread, image, registry, object
        
        json response = {
            {"id", message.value("id", 0)},
            {"type", "success"},
            {"command", "mcp_list_callbacks"},
            {"callback_enumeration", json::object()},
            {"summary", json::object()},
            {"metadata", json::object()}
        };
        
        json& callbacks = response["callback_enumeration"];
        json& summary = response["summary"];
        int totalCallbacks = 0;
        
        // 1. Enumerate Process Creation Callbacks
        if (filter_type == "all" || filter_type == "process") {
            try {
                std::string processCallbackCmd = "dps nt!PspCreateProcessNotifyRoutine";
                std::string processOutput = CommandUtilities::ExecuteWinDbgCommand(processCallbackCmd, timeout);
                
                if (!processOutput.empty()) {
                    auto result = parseCallbackList(processOutput);
                    auto parsedCallbacks = result.first;
                    auto processCallbackCount = result.second;
                    
                    callbacks["process_creation"] = {
                        {"type", "Process Creation Callbacks"},
                        {"source_symbol", "nt!PspCreateProcessNotifyRoutine"},
                        {"raw_output", processOutput},
                        {"parsed_callbacks", parsedCallbacks},
                        {"count", processCallbackCount}
                    };
                    
                    totalCallbacks += processCallbackCount;
                }
            }
            catch (const std::exception& e) {
                callbacks["process_creation"] = {
                    {"type", "Process Creation Callbacks"},
                    {"error", std::string("Failed to enumerate process callbacks: ") + e.what()}
                };
            }
        }
        
        // 2. Enumerate Thread Creation Callbacks
        if (filter_type == "all" || filter_type == "thread") {
            try {
                std::string threadCallbackCmd = "dps nt!PspCreateThreadNotifyRoutine";
                std::string threadOutput = CommandUtilities::ExecuteWinDbgCommand(threadCallbackCmd, timeout);
                
                if (!threadOutput.empty()) {
                    auto result = parseCallbackList(threadOutput);
                    auto parsedCallbacks = result.first;
                    auto threadCallbackCount = result.second;
                    
                    callbacks["thread_creation"] = {
                        {"type", "Thread Creation Callbacks"},
                        {"source_symbol", "nt!PspCreateThreadNotifyRoutine"},
                        {"raw_output", threadOutput},
                        {"parsed_callbacks", parsedCallbacks},
                        {"count", threadCallbackCount}
                    };
                    
                    totalCallbacks += threadCallbackCount;
                }
            }
            catch (const std::exception& e) {
                callbacks["thread_creation"] = {
                    {"type", "Thread Creation Callbacks"},
                    {"error", std::string("Failed to enumerate thread callbacks: ") + e.what()}
                };
            }
        }
        
        // 3. Enumerate Image Load Callbacks
        if (filter_type == "all" || filter_type == "image") {
            try {
                std::string imageCallbackCmd = "dps nt!PspLoadImageNotifyRoutine";
                std::string imageOutput = CommandUtilities::ExecuteWinDbgCommand(imageCallbackCmd, timeout);
                
                if (!imageOutput.empty()) {
                    auto result = parseCallbackList(imageOutput, {"nt", "hal", "ntoskrnl", "ci"});
                    auto parsedCallbacks = result.first;
                    auto imageCallbackCount = result.second;
                    
                    callbacks["image_load"] = {
                        {"type", "Image Load Callbacks"},
                        {"source_symbol", "nt!PspLoadImageNotifyRoutine"},
                        {"raw_output", imageOutput},
                        {"parsed_callbacks", parsedCallbacks},
                        {"count", imageCallbackCount}
                    };
                    
                    totalCallbacks += imageCallbackCount;
                }
            }
            catch (const std::exception& e) {
                callbacks["image_load"] = {
                    {"type", "Image Load Callbacks"},
                    {"error", std::string("Failed to enumerate image callbacks: ") + e.what()}
                };
            }
        }
        
        // 4. Enumerate Registry Callbacks
        if (filter_type == "all" || filter_type == "registry") {
            try {
                std::string registryCallbackCmd = "!reg";  // Alternative approach for registry callbacks
                std::string registryOutput = CommandUtilities::ExecuteWinDbgCommand(registryCallbackCmd, timeout);
                
                if (registryOutput.empty() || registryOutput.find("Invalid") != std::string::npos) {
                    // Try alternative command
                    registryCallbackCmd = "dps nt!CmpCallBackVector";
                    registryOutput = CommandUtilities::ExecuteWinDbgCommand(registryCallbackCmd, timeout);
                }
                
                if (!registryOutput.empty()) {
                    callbacks["registry"] = {
                        {"type", "Registry Callbacks"},
                        {"source_symbol", "nt!CmpCallBackVector"},
                        {"raw_output", registryOutput},
                        {"parsed_callbacks", json::array()}
                    };
                    
                    // Parse registry callbacks
                    json& parsedCallbacks = callbacks["registry"]["parsed_callbacks"];
                    std::istringstream iss(registryOutput);
                    std::string line;
                    int registryCallbackCount = 0;
                    
                    while (std::getline(iss, line)) {
                        if (line.find("+0x") != std::string::npos && line.find("!") != std::string::npos) {
                            json callbackEntry;
                            callbackEntry["address"] = line.substr(0, line.find(" "));
                            
                            size_t moduleStart = line.find("!");
                            if (moduleStart != std::string::npos) {
                                std::string moduleName = line.substr(0, moduleStart);
                                moduleName = moduleName.substr(moduleName.find_last_of(" ") + 1);
                                
                                callbackEntry["module"] = moduleName;
                                callbackEntry["function"] = line.substr(moduleStart + 1);
                                callbackEntry["third_party"] = (moduleName != "nt" && moduleName != "hal" && 
                                                               moduleName != "ntoskrnl");
                                
                                if (callbackEntry["third_party"]) {
                                    thirdPartyDrivers.push_back(moduleName);
                                }
                            }
                            
                            callbackEntry["full_line"] = line;
                            parsedCallbacks.push_back(callbackEntry);
                            registryCallbackCount++;
                        }
                    }
                    
                    callbacks["registry"]["count"] = registryCallbackCount;
                    totalCallbacks += registryCallbackCount;
                }
            }
            catch (const std::exception& e) {
                callbacks["registry"] = {
                    {"type", "Registry Callbacks"},
                    {"error", std::string("Failed to enumerate registry callbacks: ") + e.what()}
                };
            }
        }
        
        // 5. Enumerate Object Manager Callbacks (Process and Thread object types)
        if (filter_type == "all" || filter_type == "object") {
            try {
                // Get Process Object Type callbacks
                std::string processObjectCmd = "dx @$ProcObj = *(nt!_OBJECT_TYPE **)&nt!PsProcessType; @$ProcObj->CallbackList";
                std::string processObjectOutput = CommandUtilities::ExecuteWinDbgCommand(processObjectCmd, timeout);
                
                callbacks["object_manager"] = {
                    {"type", "Object Manager Callbacks"},
                    {"process_callbacks", json::object()},
                    {"thread_callbacks", json::object()}
                };
                
                if (!processObjectOutput.empty()) {
                    callbacks["object_manager"]["process_callbacks"] = {
                        {"raw_output", processObjectOutput},
                        {"note", "Process object callbacks (handle operations)"}
                    };
                }
                
                // Get Thread Object Type callbacks
                std::string threadObjectCmd = "dx @$ThreadObj = *(nt!_OBJECT_TYPE **)&nt!PsThreadType; @$ThreadObj->CallbackList";
                std::string threadObjectOutput = CommandUtilities::ExecuteWinDbgCommand(threadObjectCmd, timeout);
                
                if (!threadObjectOutput.empty()) {
                    callbacks["object_manager"]["thread_callbacks"] = {
                        {"raw_output", threadObjectOutput},
                        {"note", "Thread object callbacks (handle operations)"}
                    };
                }
            }
            catch (const std::exception& e) {
                callbacks["object_manager"] = {
                    {"type", "Object Manager Callbacks"},
                    {"error", std::string("Failed to enumerate object manager callbacks: ") + e.what()}
                };
            }
        }
        
        // Create summary
        auto end_time = std::chrono::steady_clock::now();
        double execution_time = std::chrono::duration<double>(end_time - start_time).count();
        
        summary["total_callbacks"] = totalCallbacks;
        summary["execution_time_seconds"] = execution_time;
        summary["filter_applied"] = filter_type;
        
        // Remove duplicates from third-party drivers
        std::sort(thirdPartyDrivers.begin(), thirdPartyDrivers.end());
        thirdPartyDrivers.erase(std::unique(thirdPartyDrivers.begin(), thirdPartyDrivers.end()), thirdPartyDrivers.end());
        summary["third_party_drivers"] = thirdPartyDrivers;
        summary["unique_third_party_drivers"] = thirdPartyDrivers.size();
        
        // Add metadata
        response["metadata"] = {
            {"command_info", "Unified callback enumeration across all callback types"},
            {"supported_types", json::array({"process", "thread", "image", "registry", "object"})},
            {"edr_detection_note", "Third-party drivers may indicate EDR/AV presence"},
            {"execution_time", execution_time},
            {"timestamp", std::chrono::duration_cast<std::chrono::milliseconds>(
                std::chrono::system_clock::now().time_since_epoch()).count()}
        };
        
        CommandUtilities::UpdateGlobalPerformanceMetrics(execution_time);
        
        return response;
    }
    catch (const std::exception& e) {
        return CommandUtilities::CreateDetailedErrorResponse(
            message.value("id", 0),
            "mcp_list_callbacks",
            std::string("Unified callback enumeration failed: ") + e.what(),
            ErrorCategory::InternalError
        );
    }
}

// Helper methods for specific command types
json EnhancedCommandHandlers::HandleProcessCommand(int id, const std::string& command, unsigned int timeout) {
    try {
        // Extract the process address and flags from the command
        // Format typically: !process [address] [flags]
        std::string processCmd = command;
        std::string output = CommandUtilities::ExecuteWinDbgCommand(processCmd, timeout);
        
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
                output = CommandUtilities::ExecuteWinDbgCommand(alternateCmd, timeout);
                
                if (!output.empty()) {
                    return CommandUtilities::CreateSuccessResponse(id, "execute_command", output);
                }
            }
            
            return CommandUtilities::CreateDetailedErrorResponse(
                id,
                "execute_command",
                "Process command returned no output. The process address might be invalid.",
                ErrorCategory::ExecutionContext,
                E_INVALIDARG,
                "Check that the process address is valid and that you are in the correct debugging context."
            );
        }
        
        return CommandUtilities::CreateSuccessResponse(id, "execute_command", output);
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
        ErrorCategory category = CommandUtilities::ClassifyError(errorMsg, hr);
        
        return CommandUtilities::CreateDetailedErrorResponse(
            id, 
            "execute_command", 
            std::string("Process command failed: ") + e.what(),
            category,
            hr,
            CommandUtilities::GetSuggestionForError(category, command, hr)
        );
    }
}

json EnhancedCommandHandlers::HandleDllsCommand(int id, const std::string& command, unsigned int timeout) {
    try {
        std::string output = CommandUtilities::ExecuteWinDbgCommand(command, timeout);
        
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
                output = CommandUtilities::ExecuteWinDbgCommand(correctedCmd, timeout);
                
                if (!output.empty()) {
                    // Now extract dll information
                    std::string dllsCmd = "!dlls";
                    std::string dllOutput = CommandUtilities::ExecuteWinDbgCommand(dllsCmd, timeout);
                    output = "Process modules:\n" + dllOutput;
                }
            }
        }
        
        if (output.empty()) {
            return CommandUtilities::CreateDetailedErrorResponse(
                id,
                "execute_command",
                "DLLs command returned no output. Try using '!process <address>' first to set the context.",
                ErrorCategory::ExecutionContext,
                S_OK,
                "First set the process context with '!process <address>' or '.process /r /p <address>', then run '!dlls'"
            );
        }
        
        return CommandUtilities::CreateSuccessResponse(id, "execute_command", output);
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
        ErrorCategory category = CommandUtilities::ClassifyError(errorMsg, hr);
        
        return CommandUtilities::CreateDetailedErrorResponse(
            id, 
            "execute_command", 
            std::string("DLLs command failed: ") + e.what(),
            category,
            hr,
            CommandUtilities::GetSuggestionForError(category, command, hr)
        );
    }
}

json EnhancedCommandHandlers::HandleAddressCommand(int id, const std::string& command, unsigned int timeout) {
    try {
        std::string output = CommandUtilities::ExecuteWinDbgCommand(command, timeout);
        
        // Check for invalid arguments
        if (output.find("Invalid arguments") != std::string::npos) {
            // Try alternate command forms
            std::string alternateCmd;
            
            if (command.find("-f:PAGE_EXECUTE_READWRITE") != std::string::npos) {
                // Use !vprot instead which gives similar information
                alternateCmd = "!vprot";
                std::string altOutput = CommandUtilities::ExecuteWinDbgCommand(alternateCmd, timeout);
                if (!altOutput.empty()) {
                    output = "Memory pages with PAGE_EXECUTE_READWRITE:\n" + altOutput;
                    return CommandUtilities::CreateSuccessResponse(id, "execute_command", output);
                }
            }
            else if (command.find("-f:ExecuteEnable") != std::string::npos) {
                // Use a combination of commands to get executable memory
                alternateCmd = "!address";
                std::string altOutput = CommandUtilities::ExecuteWinDbgCommand(alternateCmd, timeout);
                if (!altOutput.empty()) {
                    // Filter for executable regions in the output
                    // This is simplified; in reality we would need more sophisticated parsing
                    output = "Executable memory regions:\n" + altOutput;
                    return CommandUtilities::CreateSuccessResponse(id, "execute_command", output);
                }
            }
            
            return CommandUtilities::CreateDetailedErrorResponse(
                id,
                "execute_command",
                "Address command has invalid arguments.",
                ErrorCategory::CommandSyntax,
                E_INVALIDARG,
                "Try using '!address' without flags first or check the command syntax with '!help address'"
            );
        }
        
        if (output.empty()) {
            return CommandUtilities::CreateDetailedErrorResponse(
                id,
                "execute_command",
                "Address command returned no output.",
                ErrorCategory::Unknown,
                S_OK,
                "The command might not be applicable in the current context."
            );
        }
        
        return CommandUtilities::CreateSuccessResponse(id, "execute_command", output);
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
        ErrorCategory category = CommandUtilities::ClassifyError(errorMsg, hr);
        
        return CommandUtilities::CreateDetailedErrorResponse(
            id, 
            "execute_command", 
            std::string("Address command failed: ") + e.what(),
            category,
            hr,
            CommandUtilities::GetSuggestionForError(category, command, hr)
        );
    }
}

 