#include "pch.h"
#include "command/command_registry.h"
#include "command/basic_command_handlers.h"
#include "command/diagnostic_command_handlers.h"
#include "command/enhanced_command_handlers.h"
#include "../ipc/mcp_server.h"  // Include MCPServer definition
#include <vector>
#include <stdexcept>
#include <string>

void CommandRegistry::RegisterAllHandlers(MCPServer& server) {
    bool success = true;
    std::vector<std::string> failures;
    
    // Register basic command handlers
    try {
        BasicCommandHandlers::RegisterHandlers(server);
        // Log successful registration if needed
        // Could add logging here if logger is available
    }
    catch (const std::exception& e) {
        success = false;
        failures.push_back(std::string("BasicCommandHandlers: ") + e.what());
    }
    catch (...) {
        success = false;
        failures.push_back("BasicCommandHandlers: Unknown exception");
    }
    
    // Register diagnostic command handlers
    try {
        DiagnosticCommandHandlers::RegisterHandlers(server);
    }
    catch (const std::exception& e) {
        success = false;
        failures.push_back(std::string("DiagnosticCommandHandlers: ") + e.what());
    }
    catch (...) {
        success = false;
        failures.push_back("DiagnosticCommandHandlers: Unknown exception");
    }
    
    // Register enhanced command handlers
    try {
        EnhancedCommandHandlers::RegisterHandlers(server);
    }
    catch (const std::exception& e) {
        success = false;
        failures.push_back(std::string("EnhancedCommandHandlers: ") + e.what());
    }
    catch (...) {
        success = false;
        failures.push_back("EnhancedCommandHandlers: Unknown exception");
    }
    
    // If any registrations failed, throw an exception with details
    if (!success) {
        std::string error_message = "Handler registration failures: ";
        for (size_t i = 0; i < failures.size(); ++i) {
            if (i > 0) error_message += "; ";
            error_message += failures[i];
        }
        throw std::runtime_error(error_message);
    }
} 