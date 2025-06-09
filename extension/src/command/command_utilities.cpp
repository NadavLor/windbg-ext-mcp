#include "pch.h"
#include "command/command_utilities.h"
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

// Global variables for tracking performance and health (protected by mutex)
std::mutex CommandUtilities::s_staticMembersMutex;

// Static member definitions
std::chrono::steady_clock::time_point CommandUtilities::g_lastCommandTime = std::chrono::steady_clock::now();
std::string CommandUtilities::g_sessionId;
double CommandUtilities::g_lastExecutionTime = 0.0;

// CommandExecutor class implementation
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
        
        // Create a promise/future for the command execution
        std::promise<CommandResult> promise;
        auto future = promise.get_future();
        
        // Shared pointer to control interface for interrupt capability
        std::shared_ptr<CComQIPtr<IDebugControl>> sharedControl = std::make_shared<CComQIPtr<IDebugControl>>();
        
        // Launch the command execution in a separate thread
        std::thread executionThread([&promise, command, sharedControl]() {
            bool promiseSet = false;
            try {
                CComPtr<IDebugClient> client;
                HRESULT hr = DebugCreate(__uuidof(IDebugClient), (void**)&client);
                if (FAILED(hr)) {
                    promise.set_value(CommandResult("Failed to create debug client", hr));
                    promiseSet = true;
                    return;
                }
                
                CComQIPtr<IDebugControl> control(client);
                if (!control) {
                    promise.set_value(CommandResult("Failed to get debug control interface", E_FAIL));
                    promiseSet = true;
                    return;
                }
                
                // Store the control interface for potential interrupt
                *sharedControl = control;
                
                // Create our custom output callback - use CComPtr for proper management
                CComPtr<OutputCallbacks> callbacks;
                callbacks = new OutputCallbacks();  // Don't use Attach() - new already sets refcount to 1
                
                // Set the output callbacks
                hr = client->SetOutputCallbacks(callbacks);
                if (FAILED(hr)) {
                    promise.set_value(CommandResult("Failed to set output callbacks", hr));
                    promiseSet = true;
                    return;
                }
                
                // Execute the command
                hr = control->Execute(DEBUG_OUTCTL_THIS_CLIENT, command.c_str(), DEBUG_EXECUTE_DEFAULT);
                
                // Get the output
                std::string output = callbacks->GetOutput();
                
                // Clean up by removing our callback
                client->SetOutputCallbacks(nullptr);
                
                promise.set_value(CommandResult(output, hr));
                promiseSet = true;
                
            } catch (const std::exception& e) {
                if (!promiseSet) {
                    promise.set_value(CommandResult(std::string("Exception: ") + e.what(), E_FAIL));
                    promiseSet = true;
                }
            } catch (...) {
                if (!promiseSet) {
                    promise.set_value(CommandResult("Unknown exception", E_FAIL));
                    promiseSet = true;
                }
            }
            
            // Final safety net - ensure promise is always set
            if (!promiseSet) {
                promise.set_value(CommandResult("Internal error: Promise not set", E_FAIL));
            }
        });
        
        // Wait for either completion or timeout
        auto status = future.wait_for(std::chrono::milliseconds(timeoutMs));
        
        if (status == std::future_status::timeout) {
            result.hasTimedOut = true;
            result.output = "Command timed out";
            result.hr = E_ABORT;
            
            // Try to interrupt the command gracefully using SetInterrupt
            if (*sharedControl) {
                (*sharedControl)->SetInterrupt(DEBUG_INTERRUPT_ACTIVE);
            }
            
            // Give the command a brief opportunity to respond to the interrupt
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
            
            // Check if the command completed after interrupt
            auto interruptStatus = future.wait_for(std::chrono::milliseconds(500));
            if (interruptStatus == std::future_status::ready) {
                // Command completed after interrupt, get the result
                auto interruptedResult = future.get();
                result.output += " (interrupted)";
                
                // Wait for thread to complete safely since command finished
                if (executionThread.joinable()) {
                    executionThread.join();
                }
            } else {
                // Command still running despite interrupt, detach thread to avoid blocking
                if (executionThread.joinable()) {
                    executionThread.detach();
                }
            }
        } else {
            // Command completed normally
            result = future.get();
            
            // Wait for thread to complete safely
            if (executionThread.joinable()) {
                executionThread.join();
            }
        }
        
        return result;
    }
};

std::string CommandUtilities::ExecuteWinDbgCommand(const std::string& command, unsigned int timeoutMs) {
    // Validate command
    if (command.empty()) {
        throw std::invalid_argument("Command cannot be empty");
    }
    
    try {
        auto result = CommandExecutor::ExecuteWithTimeout(command, timeoutMs);
        
        if (result.hasTimedOut) {
            throw std::runtime_error("Command timed out after " + std::to_string(timeoutMs) + " ms");
        }
        
        if (FAILED(result.hr)) {
            std::ostringstream oss;
            oss << "Command failed with HRESULT: 0x" << std::hex << result.hr;
            if (!result.output.empty()) {
                oss << " - " << result.output;
            }
            throw std::runtime_error(oss.str());
        }
        
        return result.output;
    }
    catch (const std::exception& e) {
        throw std::runtime_error(std::string("Command execution failed: ") + e.what());
    }
}

json CommandUtilities::CreateSuccessResponse(int id, const std::string& command, const std::string& output) {
    return {
        {"type", "response"},
        {"id", id},
        {"status", "success"},
        {"command", command},
        {"output", output},
        {"timestamp", GetCurrentTimestamp()}
    };
}

json CommandUtilities::CreateSuccessResponseWithMetadata(int id, const std::string& command, const std::string& output, 
                                                      double execution_time, const std::string& debugging_mode) {
    // Parse modules from output if it contains module listing
    json modules = json::array();
    std::string modulesOutput = output;
    
    // Basic module parsing for commands like 'lm'
    if (command.find("lm") == 0 || command.find("modules") != std::string::npos) {
        std::istringstream moduleStream(modulesOutput);
        std::string line;
        while (std::getline(moduleStream, line)) {
            if (!line.empty() && line.find("start    end") == std::string::npos) {
                modules.push_back(line);
            }
        }
    }
    
    return {
        {"type", "response"},
        {"id", id},
        {"status", "success"},
        {"command", command},
        {"output", output},
        {"metadata", {
            {"execution_time", execution_time},
            {"debugging_mode", debugging_mode},
            {"modules", modules},
            {"timestamp", GetCurrentTimestamp()}
        }}
    };
}

json CommandUtilities::CreateEnhancedErrorResponse(int id, const std::string& command, 
                                                 const std::string& error,
                                                 ErrorCategory category,
                                                 const std::string& suggestion) {
    return {
        {"type", "response"},
        {"id", id},
        {"status", "error"},
        {"command", command},
        {"error", error},
        {"error_category", GetErrorCategoryString(category)},
        {"suggestion", suggestion},
        {"timestamp", GetCurrentTimestamp()}
    };
}

json CommandUtilities::CreateErrorResponse(int id, const std::string& command, const std::string& error) {
    return {
        {"type", "response"},
        {"id", id},
        {"status", "error"},
        {"command", command},
        {"error", error},
        {"timestamp", GetCurrentTimestamp()}
    };
}

json CommandUtilities::CreateDetailedErrorResponse(
    int id,
    const std::string& command,
    const std::string& error,
    ErrorCategory category,
    HRESULT errorCode,
    const std::string& suggestion) {
    
    return {
        {"type", "response"},
        {"id", id},
        {"status", "error"},
        {"command", command},
        {"error", error},
        {"error_category", GetErrorCategoryString(category)},
        {"error_code", static_cast<unsigned int>(errorCode)},
        {"suggestion", suggestion},
        {"timestamp", GetCurrentTimestamp()}
    };
}

ErrorCategory CommandUtilities::ClassifyError(const std::string& errorMessage, HRESULT errorCode) {
    // Convert to lowercase for case-insensitive comparison
    std::string lowerError = errorMessage;
    std::transform(lowerError.begin(), lowerError.end(), lowerError.begin(), 
                   [](char c) { return static_cast<char>(std::tolower(static_cast<unsigned char>(c))); });
    
    // Check for specific HRESULT codes
    if (errorCode == E_INVALIDARG) {
        return ErrorCategory::CommandSyntax;
    } else if (errorCode == E_ACCESSDENIED) {
        return ErrorCategory::PermissionDenied;
    } else if (errorCode == E_OUTOFMEMORY) {
        return ErrorCategory::ResourceExhaustion;
    } else if (errorCode == RPC_E_DISCONNECTED || errorCode == RPC_E_SERVER_DIED) {
        return ErrorCategory::ConnectionLost;
    }
    
    // Check for specific error message patterns
    if (lowerError.find("syntax error") != std::string::npos ||
        lowerError.find("invalid command") != std::string::npos ||
        lowerError.find("unknown command") != std::string::npos) {
        return ErrorCategory::CommandSyntax;
    }
    
    if (lowerError.find("access denied") != std::string::npos ||
        lowerError.find("permission denied") != std::string::npos) {
        return ErrorCategory::PermissionDenied;
    }
    
    if (lowerError.find("out of memory") != std::string::npos ||
        lowerError.find("memory allocation") != std::string::npos) {
        return ErrorCategory::ResourceExhaustion;
    }
    
    if (lowerError.find("connection") != std::string::npos ||
        lowerError.find("disconnect") != std::string::npos ||
        lowerError.find("rpc") != std::string::npos) {
        return ErrorCategory::ConnectionLost;
    }
    
    if (lowerError.find("timeout") != std::string::npos ||
        lowerError.find("timed out") != std::string::npos) {
        return ErrorCategory::Timeout;
    }
    
    if (lowerError.find("process") != std::string::npos ||
        lowerError.find("thread") != std::string::npos ||
        lowerError.find("context") != std::string::npos) {
        return ErrorCategory::ExecutionContext;
    }
    
    return ErrorCategory::Unknown;
}

std::string CommandUtilities::GetErrorCategoryString(ErrorCategory category) {
    switch (category) {
        case ErrorCategory::CommandSyntax: return "CommandSyntax";
        case ErrorCategory::PermissionDenied: return "PermissionDenied";
        case ErrorCategory::ResourceExhaustion: return "ResourceExhaustion";
        case ErrorCategory::ConnectionLost: return "ConnectionLost";
        case ErrorCategory::Timeout: return "Timeout";
        case ErrorCategory::ExecutionContext: return "ExecutionContext";
        case ErrorCategory::InternalError: return "InternalError";
        case ErrorCategory::Unknown: return "Unknown";
        default: return "Unknown";
    }
}

std::string CommandUtilities::GetSuggestionForError(ErrorCategory category, const std::string& command, HRESULT errorCode) {
    switch (category) {
        case ErrorCategory::CommandSyntax:
            return "Check the command syntax. Use '.help " + command.substr(0, command.find(' ')) + "' for help.";
        
        case ErrorCategory::PermissionDenied:
            return "The command requires elevated privileges. Ensure WinDbg is running as administrator.";
        
        case ErrorCategory::ResourceExhaustion:
            return "The system is low on resources. Close unnecessary applications and try again.";
        
        case ErrorCategory::ConnectionLost:
            return "The connection to the debugger was lost. Try reconnecting to the target.";
        
        case ErrorCategory::Timeout:
            return "The command timed out. Try increasing the timeout or breaking the command into smaller parts.";
        
        case ErrorCategory::ExecutionContext:
            return "The command failed due to execution context. Ensure you are in the correct process/thread context.";
        
        case ErrorCategory::InternalError:
            return "An internal error occurred. Check the debugger state and try again.";
        
        case ErrorCategory::Unknown:
        default:
            return "An unknown error occurred. Check the command syntax and execution context.";
    }
}

TimeoutCategory CommandUtilities::CategorizeCommand(const std::string& command) {
    std::string lowerCommand = command;
    std::transform(lowerCommand.begin(), lowerCommand.end(), lowerCommand.begin(), 
                   [](char c) { return static_cast<char>(std::tolower(static_cast<unsigned char>(c))); });
    
    // Quick commands (usually complete in <5 seconds)
    if (lowerCommand.find("version") == 0 ||
        lowerCommand.find("r") == 0 ||
        lowerCommand.find("k") == 0 ||
        lowerCommand.find("u") == 0 ||
        lowerCommand.find("db") == 0 ||
        lowerCommand.find("dd") == 0 ||
        lowerCommand.find("dw") == 0 ||
        lowerCommand.find("dq") == 0) {
        return TimeoutCategory::Quick;
    }
    
    // Analysis commands (can take 30-60 seconds)
    if (lowerCommand.find("!analyze") == 0 ||
        lowerCommand.find("!pool") == 0 ||
        lowerCommand.find("!heap") == 0 ||
        lowerCommand.find("!handle") == 0) {
        return TimeoutCategory::Analysis;
    }
    
    // Bulk operations (can take several minutes)
    if (lowerCommand.find("!for_each") == 0 ||
        lowerCommand.find("lm") == 0 ||
        lowerCommand.find("!process 0 0") == 0) {
        return TimeoutCategory::Bulk;
    }
    
    // Slow commands (10-30 seconds)
    if (lowerCommand.find("!process") == 0 ||
        lowerCommand.find("!thread") == 0 ||
        lowerCommand.find("!dlls") == 0 ||
        lowerCommand.find("!address") == 0) {
        return TimeoutCategory::Slow;
    }
    
    // Default to normal timeout
    return TimeoutCategory::Normal;
}

unsigned int CommandUtilities::GetTimeoutForCategory(TimeoutCategory category) {
    switch (category) {
        case TimeoutCategory::Quick: return 5000;    // 5 seconds
        case TimeoutCategory::Normal: return 15000;  // 15 seconds
        case TimeoutCategory::Slow: return 30000;    // 30 seconds
        case TimeoutCategory::Analysis: return 60000; // 1 minute
        case TimeoutCategory::Bulk: return 300000;   // 5 minutes
        default: return 15000;
    }
}

std::string CommandUtilities::GetCurrentTimestamp() {
    auto now = std::chrono::system_clock::now();
    auto time_t = std::chrono::system_clock::to_time_t(now);
    
    struct tm tm_info;
    #ifdef _WIN32
    localtime_s(&tm_info, &time_t);
    #else
    localtime_r(&time_t, &tm_info);
    #endif
    
    std::ostringstream oss;
    oss << std::put_time(&tm_info, "%Y-%m-%d %H:%M:%S");
    return oss.str();
}

std::string CommandUtilities::GenerateSessionId() {
    auto now = std::chrono::system_clock::now();
    auto time_t = std::chrono::system_clock::to_time_t(now);
    
    struct tm tm_info;
    #ifdef _WIN32
    localtime_s(&tm_info, &time_t);
    #else
    localtime_r(&time_t, &tm_info);
    #endif
    
    std::ostringstream oss;
    oss << "windbg_session_" << std::put_time(&tm_info, "%Y%m%d_%H%M%S");
    
    // Add random component
    std::random_device rd;
    std::mt19937 gen(rd());
    std::uniform_int_distribution<> dis(1000, 9999);
    oss << "_" << dis(gen);
    
    return oss.str();
}

void CommandUtilities::UpdateGlobalPerformanceMetrics(double execution_time) {
    std::lock_guard<std::mutex> lock(s_staticMembersMutex);
    g_lastCommandTime = std::chrono::steady_clock::now();
    g_lastExecutionTime = execution_time;
}

double CommandUtilities::GetLastExecutionTime() {
    std::lock_guard<std::mutex> lock(s_staticMembersMutex);
    return g_lastExecutionTime;
}

std::string CommandUtilities::GetSessionId() {
    std::lock_guard<std::mutex> lock(s_staticMembersMutex);
    if (g_sessionId.empty()) {
        g_sessionId = GenerateSessionId();
    }
    return g_sessionId;
}

std::chrono::steady_clock::time_point CommandUtilities::GetLastCommandTime() {
    std::lock_guard<std::mutex> lock(s_staticMembersMutex);
    return g_lastCommandTime;
}

std::string CommandUtilities::GetDebuggingMode() {
    try {
        // Execute a simple command to determine the debugging mode
        std::string output = ExecuteWinDbgCommand("version", 5000);
        
        if (output.find("kernel") != std::string::npos || output.find("Kernel") != std::string::npos) {
            return "Kernel Mode";
        } else if (output.find("user") != std::string::npos || output.find("User") != std::string::npos) {
            return "User Mode";
        } else if (output.find("dump") != std::string::npos || output.find("Dump") != std::string::npos) {
            return "Dump Analysis";
        } else {
            return "Unknown";
        }
    } catch (...) {
        return "Unknown";
    }
}

std::string CommandUtilities::GetExtensionVersion() {
    // Return the extension version information
    return "WinDbg MCP Extension v1.0.0";
}

std::string CommandUtilities::GetWinDbgVersion() {
    try {
        // Execute version command to get WinDbg version
        std::string output = ExecuteWinDbgCommand("version", 5000);
        
        // Extract version information from output
        std::istringstream iss(output);
        std::string line;
        while (std::getline(iss, line)) {
            if (line.find("Microsoft") != std::string::npos && line.find("Debugging") != std::string::npos) {
                return line;
            }
        }
        
        return "WinDbg (version unknown)";
    } catch (...) {
        return "WinDbg (version unavailable)";
    }
}

CommandResult CommandUtilities::ExecuteWithTimeout(const std::string& command, unsigned int timeoutMs) {
    try {
        auto result = CommandExecutor::ExecuteWithTimeout(command, timeoutMs);
        
        // Convert CommandExecutor::CommandResult to global CommandResult
        CommandResult utilsResult;
        utilsResult.output = result.output;
        utilsResult.hr = result.hr;
        utilsResult.hasTimedOut = result.hasTimedOut;
        utilsResult.executionTime = 0.0;  // CommandExecutor doesn't track this
        
        return utilsResult;
    } catch (const std::exception& e) {
        CommandResult errorResult;
        errorResult.output = std::string("Exception: ") + e.what();
        errorResult.hr = E_FAIL;
        errorResult.hasTimedOut = false;
        errorResult.executionTime = 0.0;
        return errorResult;
    }
}

void CommandUtilities::EnsureSessionId() {
    std::lock_guard<std::mutex> lock(s_staticMembersMutex);
    if (g_sessionId.empty()) {
        g_sessionId = GenerateSessionId();
    }
} 