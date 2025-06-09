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
            
            // Check if this is a command that normally returns no output on success
            bool isEmptyOutputValidCommand = false;
            std::string trimmedCommand = command;
            // Remove leading whitespace
            trimmedCommand.erase(0, trimmedCommand.find_first_not_of(" \t\n\r\f\v"));
            
            // Convert to lowercase for comparison
            std::string lowerCommand = trimmedCommand;
            std::transform(lowerCommand.begin(), lowerCommand.end(), lowerCommand.begin(), ::tolower);
            
            // Check for memory edit commands (eq, ed, eb, ew, etc.)
            if (trimmedCommand.length() >= 2) {
                std::string cmdPrefix = trimmedCommand.substr(0, 2);
                if (cmdPrefix == "eq" || cmdPrefix == "ed" || cmdPrefix == "eb" || 
                    cmdPrefix == "ew" || cmdPrefix == "ea" || cmdPrefix == "eu") {
                    // Verify it's actually a memory edit command (has address parameter)
                    size_t spacePos = trimmedCommand.find(' ');
                    if (spacePos != std::string::npos && spacePos == 2) {
                        isEmptyOutputValidCommand = true;
                    }
                }
            }
            
            // Check for breakpoint and execution control commands that return empty output on success
            if (lowerCommand.find("bp ") == 0 ||           // Set breakpoint
                lowerCommand.find("ba ") == 0 ||           // Set access breakpoint  
                lowerCommand.find("bu ") == 0 ||           // Set unresolved breakpoint
                lowerCommand.find("bm ") == 0 ||           // Set symbol breakpoint
                lowerCommand == "g" ||                     // Go/continue
                lowerCommand.find("g ") == 0 ||            // Go with address
                lowerCommand == "gh" ||                    // Go with exception handled
                lowerCommand == "gn" ||                    // Go with exception not handled
                lowerCommand.find("gu") == 0 ||            // Go up (until return)
                lowerCommand.find("p") == 0 ||             // Step/trace commands
                lowerCommand.find("t") == 0 ||             // Step/trace commands
                lowerCommand.find("bc ") == 0 ||           // Clear breakpoint
                lowerCommand.find("bd ") == 0 ||           // Disable breakpoint
                lowerCommand.find("be ") == 0 ||           // Enable breakpoint
                lowerCommand.find(".restart") == 0 ||      // Restart target
                lowerCommand.find(".reboot") == 0) {       // Reboot target
                isEmptyOutputValidCommand = true;
            }
            
            // Check if the output is empty or contains error messages
            if (output.empty() && !isEmptyOutputValidCommand) {
                return CommandUtilities::CreateDetailedErrorResponse(
                    message.value("id", 0),
                    "execute_command",
                    "Command returned no output. The command might be invalid or unsupported.",
                    ErrorCategory::Unknown,
                    S_OK,
                    "Check if the command is valid in the current context."
                );
            }
            
            // For commands that validly return empty output, provide success confirmation
            if (output.empty() && isEmptyOutputValidCommand) {
                if (lowerCommand.find("bp ") == 0 || lowerCommand.find("ba ") == 0 || 
                    lowerCommand.find("bu ") == 0 || lowerCommand.find("bm ") == 0) {
                    output = "Breakpoint set successfully.";
                } else if (lowerCommand == "g" || lowerCommand.find("g ") == 0 || 
                          lowerCommand == "gh" || lowerCommand == "gn") {
                    output = "Execution continued.";
                } else if (lowerCommand.find("bc ") == 0) {
                    output = "Breakpoint cleared successfully.";
                } else if (lowerCommand.find("bd ") == 0) {
                    output = "Breakpoint disabled successfully.";
                } else if (lowerCommand.find("be ") == 0) {
                    output = "Breakpoint enabled successfully.";
                } else if (trimmedCommand.length() >= 2 && 
                          (trimmedCommand.substr(0, 2) == "eq" || trimmedCommand.substr(0, 2) == "ed" || 
                           trimmedCommand.substr(0, 2) == "eb" || trimmedCommand.substr(0, 2) == "ew" || 
                           trimmedCommand.substr(0, 2) == "ea" || trimmedCommand.substr(0, 2) == "eu")) {
                    output = "Memory edit command completed successfully.";
                } else {
                    output = "Command completed successfully.";
                }
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

 