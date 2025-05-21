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
#include <vector>
#include <map>
#include <memory>
#include "../include/json.hpp"

using json = nlohmann::json;

// Message handler function type
using MessageHandler = std::function<json(const json&)>;

// Client connection structure
struct ClientConnection {
    HANDLE hPipe;
    std::thread thread;
    std::atomic<bool> active;
    std::queue<json> outgoingMessages;
    std::mutex queueMutex;
    std::condition_variable queueCondition;
    
    ClientConnection(HANDLE pipe) : hPipe(pipe), active(true) {}
    ~ClientConnection() {
        if (hPipe != INVALID_HANDLE_VALUE) {
            DisconnectNamedPipe(hPipe);
            CloseHandle(hPipe);
        }
    }
};

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
    
    // Send a message to a specific client
    bool SendMessage(const json& message, HANDLE clientPipe);
    
    // Send a message to all clients
    bool BroadcastMessage(const json& message);

private:
    // Worker thread that handles pipe connections
    void PipeServerThread();
    
    // Handle a client connection
    void HandleClient(std::shared_ptr<ClientConnection> client);
    
    // Process incoming message
    json ProcessMessage(const json& message);
    
    // Create a new pipe instance
    HANDLE CreatePipeInstance();
    
    // Clean up disconnected clients
    void CleanupDisconnectedClients();

    std::string m_pipeName;
    std::atomic<bool> m_running;
    std::thread m_serverThread;
    
    // Message handlers for different commands
    std::map<std::string, MessageHandler> m_handlers;
    
    // Active client connections
    std::vector<std::shared_ptr<ClientConnection>> m_clients;
    std::mutex m_clientsMutex;
}; 