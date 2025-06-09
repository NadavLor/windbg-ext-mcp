#pragma once

#include "pch.h"
#include "../include/json.hpp"
#include "../utils/constants.h"
#include <string>
#include <vector>
#include <chrono>
#include <mutex>

using json = nlohmann::json;

// Error categories for better error handling
enum class ErrorCategory {
    CommandSyntax,        // Syntax or usage errors
    PermissionDenied,     // Access denied errors
    ResourceExhaustion,   // Out of memory, resource issues
    ConnectionLost,       // Connection/RPC errors
    Timeout,              // Command timed out
    ExecutionContext,     // Wrong context (e.g., wrong mode, wrong state)
    InternalError,        // Internal errors in the extension
    Unknown               // Uncategorized errors
};

// Timeout categories for different command types
enum class TimeoutCategory {
    Quick,        // 5 seconds
    Normal,       // 15 seconds  
    Slow,         // 30 seconds
    Analysis,     // 60 seconds
    Bulk          // 300 seconds (5 minutes)
};

/**
 * @brief Command execution result structure.
 */
struct CommandResult {
    std::string output;
    HRESULT hr;
    bool hasTimedOut;
    double executionTime;
    
    CommandResult() : output(""), hr(S_OK), hasTimedOut(false), executionTime(0.0) {}
    CommandResult(const std::string& out, HRESULT result = S_OK, bool timedOut = false, double execTime = 0.0)
        : output(out), hr(result), hasTimedOut(timedOut), executionTime(execTime) {}
};

/**
 * @brief Utility functions for command handlers.
 * 
 * This class provides shared functionality used across all command handlers,
 * including error classification, timeout management, and response formatting.
 */
class CommandUtilities {
public:
    // Core command execution
    
    /**
     * @brief Execute a WinDbg command with timeout.
     * @param command Command to execute.
     * @param timeoutMs Timeout in milliseconds.
     * @return Command output as string.
     * @throws std::exception on execution failure.
     */
    static std::string ExecuteWinDbgCommand(const std::string& command, unsigned int timeoutMs = Constants::DEFAULT_TIMEOUT_MS);

    // Response creation methods
    
    /**
     * @brief Create a success response with basic information.
     * @param id Message ID.
     * @param command The executed command.
     * @param output Command output.
     * @return JSON success response.
     */
    static json CreateSuccessResponse(int id, const std::string& command, const std::string& output);
    
    /**
     * @brief Create a success response with metadata.
     * @param id Message ID.
     * @param command The executed command.
     * @param output Command output.
     * @param executionTime Execution time in seconds.
     * @param debuggingMode Current debugging mode.
     * @return JSON success response with metadata.
     */
    static json CreateSuccessResponseWithMetadata(
        int id, 
        const std::string& command, 
        const std::string& output,
        double executionTime = 0.0, 
        const std::string& debuggingMode = ""
    );
    
    /**
     * @brief Create a basic error response.
     * @param id Message ID.
     * @param command The failed command.
     * @param error Error message.
     * @return JSON error response.
     */
    static json CreateErrorResponse(int id, const std::string& command, const std::string& error);
    
    /**
     * @brief Create an enhanced error response with categorization and suggestions.
     * @param id Message ID.
     * @param command The failed command.
     * @param error Error message.
     * @param category Error category.
     * @param suggestion Suggestion for fixing the error.
     * @return JSON enhanced error response.
     */
    static json CreateEnhancedErrorResponse(
        int id, 
        const std::string& command,
        const std::string& error, 
        ErrorCategory category,
        const std::string& suggestion = ""
    );
    
    /**
     * @brief Create a detailed error response with HRESULT information.
     * @param id Message ID.
     * @param command The failed command.
     * @param error Error message.
     * @param category Error category.
     * @param errorCode HRESULT error code.
     * @param suggestion Single suggestion string.
     * @return JSON detailed error response.
     */
    static json CreateDetailedErrorResponse(
        int id,
        const std::string& command,
        const std::string& error,
        ErrorCategory category,
        HRESULT errorCode = S_OK,
        const std::string& suggestion = ""
    );

    // Timeout management
    
    /**
     * @brief Categorize a command for timeout optimization.
     * @param command The command to categorize.
     * @return TimeoutCategory for the command.
     */
    static TimeoutCategory CategorizeCommand(const std::string& command);
    
    /**
     * @brief Get timeout value for a category.
     * @param category The timeout category.
     * @return Timeout in milliseconds.
     */
    static unsigned int GetTimeoutForCategory(TimeoutCategory category);
    
    // Error classification and handling
    
    /**
     * @brief Classify an error based on message and error code.
     * @param errorMessage The error message to analyze.
     * @param errorCode HRESULT error code.
     * @return ErrorCategory classification.
     */
    static ErrorCategory ClassifyError(const std::string& errorMessage, HRESULT errorCode);
    
    /**
     * @brief Get string representation of error category.
     * @param category The error category.
     * @return String name of the category.
     */
    static std::string GetErrorCategoryString(ErrorCategory category);
    
    /**
     * @brief Get suggestion for fixing an error.
     * @param category Error category.
     * @param command The failed command.
     * @param errorCode HRESULT error code.
     * @return Suggestion string.
     */
    static std::string GetSuggestionForError(ErrorCategory category, const std::string& command, HRESULT errorCode);
    
    // System information utilities
    
    /**
     * @brief Get current timestamp in ISO format.
     * @return ISO timestamp string.
     */
    static std::string GetCurrentTimestamp();
    
    /**
     * @brief Get current debugging mode string.
     * @return Debugging mode description.
     */
    static std::string GetDebuggingMode();
    
    /**
     * @brief Get extension version information.
     * @return Extension version string.
     */
    static std::string GetExtensionVersion();
    
    /**
     * @brief Get WinDbg version information.
     * @return WinDbg version string.
     */
    static std::string GetWinDbgVersion();
    
    /**
     * @brief Generate a unique session ID.
     * @return Unique session identifier.
     */
    static std::string GenerateSessionId();
    
    // Performance tracking
    
    /**
     * @brief Update global performance metrics.
     * @param executionTime Execution time in seconds.
     */
    static void UpdateGlobalPerformanceMetrics(double executionTime);
    
    /**
     * @brief Get last command execution time.
     * @return Execution time in seconds.
     */
    static double GetLastExecutionTime();
    
    /**
     * @brief Get current session ID.
     * @return Session ID string.
     */
    static std::string GetSessionId();
    
    /**
     * @brief Get last command time as timepoint.
     * @return Last command execution timepoint.
     */
    static std::chrono::steady_clock::time_point GetLastCommandTime();
    
    // Command execution helper
    
    /**
     * @brief Execute a command with timeout and performance tracking.
     * @param command The command to execute.
     * @param timeoutMs Timeout in milliseconds.
     * @return CommandResult with output and metadata.
     */
    static CommandResult ExecuteWithTimeout(const std::string& command, unsigned int timeoutMs);
    
private:
    // Internal state tracking (protected by mutex for thread safety)
    static std::mutex s_staticMembersMutex;
    static std::chrono::steady_clock::time_point g_lastCommandTime;
    static double g_lastExecutionTime;
    static std::string g_sessionId;
    
    /**
     * @brief Initialize session ID if not already set.
     */
    static void EnsureSessionId();
}; 