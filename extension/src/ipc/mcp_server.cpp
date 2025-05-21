#include "pch.h"
#include "ipc/mcp_server.h"
#include <sstream>
#include <WDBGEXTS.H>

// Buffer size for reading from the pipe
constexpr DWORD BUFFER_SIZE = 4096;

MCPServer::MCPServer() : m_running(false), m_activePipe(INVALID_HANDLE_VALUE) {
}

MCPServer::~MCPServer() {
    Stop();
}

bool MCPServer::Start(const std::string& pipeName) {
    if (m_running) {
        // Server already running
        return true;
    }

    m_pipeName = pipeName;
    m_running = true;
    
    // Start server thread
    m_serverThread = std::thread(&MCPServer::PipeServerThread, this);
    
    return true;
}

void MCPServer::Stop() {
    m_running = false;
    
    // Wake up any waiting threads
    m_queueCondition.notify_all();
    
    // Wait for server thread to terminate
    if (m_serverThread.joinable()) {
        m_serverThread.join();
    }
    
    // Close active pipe if any
    std::lock_guard<std::mutex> lock(m_pipeMutex);
    if (m_activePipe != INVALID_HANDLE_VALUE) {
        DisconnectNamedPipe(m_activePipe);
        CloseHandle(m_activePipe);
        m_activePipe = INVALID_HANDLE_VALUE;
    }
}

bool MCPServer::IsRunning() const {
    return m_running;
}

void MCPServer::RegisterHandler(const std::string& command, MessageHandler handler) {
    m_handlers[command] = handler;
}

bool MCPServer::SendMessage(const json& message) {
    std::lock_guard<std::mutex> lock(m_queueMutex);
    m_outgoingMessages.push(message);
    m_queueCondition.notify_one();
    return true;
}

HANDLE MCPServer::CreatePipeInstance() {
    // Create a new pipe instance with message-read mode
    HANDLE hPipe = CreateNamedPipeA(
        m_pipeName.c_str(),                // Pipe name
        PIPE_ACCESS_DUPLEX,                // Read/write access
        PIPE_TYPE_MESSAGE |                // Message type pipe
        PIPE_READMODE_MESSAGE |            // Message-read mode
        PIPE_WAIT,                         // Blocking mode
        PIPE_UNLIMITED_INSTANCES,          // Max instances
        BUFFER_SIZE,                       // Output buffer size
        BUFFER_SIZE,                       // Input buffer size
        0,                                 // Default time-out (50 ms)
        NULL);                             // Default security attributes

    if (hPipe == INVALID_HANDLE_VALUE) {
        dprintf("MCPServer: CreateNamedPipe failed with error %d\n", GetLastError());
    }

    return hPipe;
}

void MCPServer::PipeServerThread() {
    while (m_running) {
        // Create a pipe instance
        HANDLE hPipe = CreatePipeInstance();
        if (hPipe == INVALID_HANDLE_VALUE) {
            // Failed to create pipe, sleep and retry
            Sleep(1000);
            continue;
        }

        // Wait for a client to connect
        dprintf("MCPServer: Waiting for client connection on %s\n", m_pipeName.c_str());
        BOOL connected = ConnectNamedPipe(hPipe, NULL) ? TRUE : (GetLastError() == ERROR_PIPE_CONNECTED);
        
        if (connected) {
            dprintf("MCPServer: Client connected\n");
            
            // Set active pipe
            {
                std::lock_guard<std::mutex> lock(m_pipeMutex);
                m_activePipe = hPipe;
            }
            
            // Handle client connection
            HandleClient(hPipe);
            
            // Reset active pipe
            {
                std::lock_guard<std::mutex> lock(m_pipeMutex);
                m_activePipe = INVALID_HANDLE_VALUE;
            }
            
            // Disconnect and close
            FlushFileBuffers(hPipe);
            DisconnectNamedPipe(hPipe);
            CloseHandle(hPipe);
            
            dprintf("MCPServer: Client disconnected\n");
        } else {
            // Failed to connect, close pipe and retry
            CloseHandle(hPipe);
        }
    }
}

void MCPServer::HandleClient(HANDLE hPipe) {
    char buffer[BUFFER_SIZE];
    DWORD bytesRead;
    std::string messageBuffer;
    
    // Keep processing until client disconnects or server stops
    while (m_running) {
        // Process outgoing messages first
        {
            std::unique_lock<std::mutex> lock(m_queueMutex);
            
            // Wait for outgoing messages with a timeout
            m_queueCondition.wait_for(lock, std::chrono::milliseconds(100), 
                [this] { return !m_outgoingMessages.empty() || !m_running; });
            
            // Check if we have messages to send
            if (!m_outgoingMessages.empty()) {
                json message = m_outgoingMessages.front();
                m_outgoingMessages.pop();
                lock.unlock();
                
                // Serialize the message
                std::string messageStr = message.dump() + "\n";
                
                // Send the message
                DWORD bytesWritten;
                BOOL success = WriteFile(
                    hPipe,                   // Pipe handle
                    messageStr.c_str(),      // Message buffer
                    (DWORD)messageStr.size(),// Message size
                    &bytesWritten,           // Bytes written
                    NULL);                   // Not overlapped
                
                if (!success || bytesWritten != messageStr.size()) {
                    printf("MCPServer: Failed to write to pipe, error %d\n", GetLastError());
                    return; // Disconnect on error
                }
            }
        }
        
        // Check if there's data to read
        DWORD bytesAvail = 0;
        BOOL success = PeekNamedPipe(
            hPipe,         // Pipe handle
            NULL,          // Buffer (not needed for peek)
            0,             // Buffer size
            NULL,          // Bytes read (not needed)
            &bytesAvail,   // Bytes available
            NULL);         // Bytes left (not needed)
        
        if (!success) {
            DWORD error = GetLastError();
            if (error == ERROR_BROKEN_PIPE || error == ERROR_PIPE_NOT_CONNECTED) {
                // Client disconnected
                return;
            }
            dprintf("MCPServer: PeekNamedPipe failed with error %d\n", error);
            return;
        }
        
        // If no data available, continue to process outgoing messages
        if (bytesAvail == 0) {
            continue;
        }
        
        // Read data from the pipe
        success = ReadFile(
            hPipe,         // Pipe handle
            buffer,        // Buffer
            BUFFER_SIZE,   // Buffer size
            &bytesRead,    // Bytes read
            NULL);         // Not overlapped
        
        if (!success || bytesRead == 0) {
            DWORD error = GetLastError();
            if (error == ERROR_BROKEN_PIPE || error == ERROR_PIPE_NOT_CONNECTED) {
                // Client disconnected
                return;
            }
            dprintf("MCPServer: ReadFile failed with error %d\n", error);
            return;
        }
        
        // Append to message buffer
        messageBuffer.append(buffer, bytesRead);
        
        // Check for complete messages (terminated by newline)
        size_t pos = 0;
        while ((pos = messageBuffer.find('\n')) != std::string::npos) {
            std::string message = messageBuffer.substr(0, pos);
            messageBuffer.erase(0, pos + 1);
            
            try {
                // Parse the message as JSON
                json jsonMessage = json::parse(message);
                
                // Process the message
                json response = ProcessMessage(jsonMessage);
                
                // Send the response
                std::string responseStr = response.dump() + "\n";
                DWORD bytesWritten;
                success = WriteFile(
                    hPipe,                    // Pipe handle
                    responseStr.c_str(),      // Response buffer
                    (DWORD)responseStr.size(),// Response size
                    &bytesWritten,            // Bytes written
                    NULL);                    // Not overlapped
                
                if (!success || bytesWritten != responseStr.size()) {
                    dprintf("MCPServer: Failed to write response, error %d\n", GetLastError());
                    return; // Disconnect on error
                }
            }
            catch (const std::exception& e) {
                dprintf("MCPServer: Error processing message: %s\n", e.what());
                
                // Send error response
                json errorResponse = {
                    {"type", "error"},
                    {"error_code", "invalid_message"},
                    {"error_message", std::string("Error processing message: ") + e.what()}
                };
                
                std::string errorStr = errorResponse.dump() + "\n";
                DWORD bytesWritten;
                WriteFile(
                    hPipe,                  // Pipe handle
                    errorStr.c_str(),       // Error buffer
                    (DWORD)errorStr.size(), // Error size
                    &bytesWritten,          // Bytes written
                    NULL);                  // Not overlapped
            }
        }
    }
}

json MCPServer::ProcessMessage(const json& message) {
    // Extract message fields
    std::string messageType = message.value("type", "");
    
    if (messageType != "command") {
        // Only command messages are supported for now
        return {
            {"id", message.value("id", 0)},
            {"type", "error"},
            {"error_code", "invalid_message_type"},
            {"error_message", "Only command messages are supported"}
        };
    }
    
    std::string command = message.value("command", "");
    int id = message.value("id", 0);
    
    // Check if we have a handler for this command
    auto handlerIt = m_handlers.find(command);
    if (handlerIt == m_handlers.end()) {
        // No handler found
        return {
            {"id", id},
            {"type", "error"},
            {"error_code", "invalid_command"},
            {"error_message", "Unknown command: " + command}
        };
    }
    
    try {
        // Execute the command handler
        json response = handlerIt->second(message);
        
        // Make sure the response has the correct ID and command
        response["id"] = id;
        response["command"] = command;
        
        return response;
    }
    catch (const std::exception& e) {
        // Command execution failed
        return {
            {"id", id},
            {"type", "error"},
            {"error_code", "command_failed"},
            {"error_message", std::string("Command execution failed: ") + e.what()}
        };
    }
} 