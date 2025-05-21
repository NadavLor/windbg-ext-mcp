#pragma once

// MCP Server Class for WinDBG Extension
// Implements a named pipe server for IPC between the WinDBG extension and the MCP server

#include "pch.h"
#include <Windows.h>
#include <string>
#include <thread>
#include <atomic>
#include <mutex>
#include <queue>
#include <functional>
#include <condition_variable>
#include "../include/json.hpp"

using json = nlohmann::json;

// Message handler function type
using MessageHandler = std::function<json(const json&)>;

class MCPServer {
public:
    MCPServer();
    ~MCPServer();

    // Start the server
    bool Start(const std::string& pipeName = "\\\\.\\pipe\\windbgmcp");
    
    // Stop the server
    void Stop();
    
    // Check if server is running
    bool IsRunning() const;
    
    // Register a command handler
    void RegisterHandler(const std::string& command, MessageHandler handler);
    
    // Send a message to the client
    bool SendMessage(const json& message);

private:
    // Worker thread that handles pipe connections
    void PipeServerThread();
    
    // Handle a client connection
    void HandleClient(HANDLE hPipe);
    
    // Process incoming message
    json ProcessMessage(const json& message);
    
    // Create a new pipe instance
    HANDLE CreatePipeInstance();

    std::string m_pipeName;
    std::atomic<bool> m_running;
    std::thread m_serverThread;
    
    // Message handlers for different commands
    std::map<std::string, MessageHandler> m_handlers;
    
    // Queue for outgoing messages
    std::queue<json> m_outgoingMessages;
    std::mutex m_queueMutex;
    std::condition_variable m_queueCondition;
    
    // Current active pipe handle
    HANDLE m_activePipe;
    std::mutex m_pipeMutex;
}; 