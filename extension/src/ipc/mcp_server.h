/**
 * @file mcp_server.h
 * @brief MCP Server Class for WinDBG Extension.
 *
 * Implements a named pipe server for IPC between the WinDBG extension and the MCP server.
 */
#pragma once

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
#include "../utils/constants.h"

using json = nlohmann::json;

// Message handler function type
using MessageHandler = std::function<json(const json&)>;

/**
 * @struct ClientConnection
 * @brief Represents a client connection to the MCP server.
 */
struct ClientConnection {
    HANDLE hPipe;                        ///< Handle to the named pipe
    std::thread thread;                  ///< Thread handling this connection
    std::atomic<bool> active;            ///< Flag indicating if the connection is active
    std::queue<json> outgoingMessages;   ///< Queue of messages to be sent to the client
    std::mutex queueMutex;               ///< Mutex for thread-safe access to the queue
    std::condition_variable queueCondition; ///< Condition variable for signaling new messages
    
    /**
     * @brief Constructor.
     * @param pipe Handle to the named pipe.
     */
    explicit ClientConnection(HANDLE pipe) : hPipe(pipe), active(true) {}
    
    /**
     * @brief Destructor. Cleans up the pipe handle.
     */
    ~ClientConnection() {
        if (hPipe != INVALID_HANDLE_VALUE) {
            DisconnectNamedPipe(hPipe);
            CloseHandle(hPipe);
        }
    }
    
    // Prevent copying
    ClientConnection(const ClientConnection&) = delete;
    ClientConnection& operator=(const ClientConnection&) = delete;
};

/**
 * @class MCPServer
 * @brief Implements a server for the Model Context Protocol.
 */
class MCPServer {
public:
    /**
     * @brief Constructor.
     */
    MCPServer();
    
    /**
     * @brief Destructor. Ensures the server is stopped.
     */
    ~MCPServer();

    /**
     * @brief Start the server.
     * @param pipeName Name of the named pipe to use.
     * @return true if started successfully, false otherwise.
     */
    bool Start(const std::string& pipeName = Constants::DEFAULT_PIPE_NAME);
    
    /**
     * @brief Stop the server.
     */
    void Stop();
    
    /**
     * @brief Check if server is running.
     * @return true if the server is running, false otherwise.
     */
    [[nodiscard]] bool IsRunning() const;
    
    /**
     * @brief Register a command handler.
     * @param command The command name.
     * @param handler The handler function.
     */
    void RegisterHandler(const std::string& command, MessageHandler handler);
    
    /**
     * @brief Send a message to a specific client.
     * @param message The message to send.
     * @param clientPipe The client pipe handle.
     * @return true if the message was sent successfully, false otherwise.
     */
    bool SendMessage(const json& message, HANDLE clientPipe);
    
    /**
     * @brief Send a message to all connected clients.
     * @param message The message to send.
     * @return true if the message was sent to at least one client, false otherwise.
     */
    bool BroadcastMessage(const json& message);

private:
    /**
     * @brief Worker thread that handles pipe connections.
     */
    void PipeServerThread();
    
    /**
     * @brief Handle a client connection.
     * @param client The client connection.
     */
    void HandleClient(std::shared_ptr<ClientConnection> client);
    
    /**
     * @brief Process an incoming message.
     * @param message The message to process.
     * @return The response message.
     */
    json ProcessMessage(const json& message);
    
    /**
     * @brief Create a new pipe instance.
     * @return Handle to the new pipe instance.
     */
    HANDLE CreatePipeInstance();
    
    /**
     * @brief Clean up disconnected clients.
     */
    void CleanupDisconnectedClients();

    std::string m_pipeName;                                 ///< Name of the named pipe
    std::atomic<bool> m_running{false};                     ///< Flag indicating if the server is running
    std::thread m_serverThread;                             ///< Server thread
    
    std::map<std::string, MessageHandler> m_handlers;       ///< Message handlers for different commands
    
    std::vector<std::shared_ptr<ClientConnection>> m_clients; ///< Active client connections
    std::mutex m_clientsMutex;                              ///< Mutex for thread-safe access to the clients vector
}; 