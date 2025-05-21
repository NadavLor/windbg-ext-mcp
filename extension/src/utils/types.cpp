/**
 * @file types.cpp
 * @brief Implementation of the WinDbg extension initialization and command handlers.
 */
#include "pch.h"
#include <Windows.h>
#define KDEXT_64BIT
#include <DbgEng.h>
#include <WDBGEXTS.H>
#include <atlcomcli.h>
#include <memory>
#include <atomic>
#include "ipc/mcp_server.h"
#include "command/command_handlers.h"
#include "utils/constants.h"

#pragma comment(lib, "dbgeng")

// Define the ExtensionApis object here
WINDBG_EXTENSION_APIS64 ExtensionApis{ sizeof(ExtensionApis) };

// Global MCP server instance
std::unique_ptr<MCPServer> g_mcpServer;

// Flag to track if the DLL is being unloaded
std::atomic<bool> g_dllUnloading(false);

// Event to signal clean shutdown
HANDLE g_shutdownEvent = nullptr;

/**
 * @brief Cleanup routine called when the process is terminating.
 * 
 * This function ensures all resources are properly released.
 * 
 * @param Parameter Not used.
 * @param TimerOrWaitFired Not used.
 */
VOID CALLBACK CleanupRoutine(PVOID Parameter, BOOLEAN TimerOrWaitFired) {
	// If a clean shutdown hasn't already been performed, do it now
	if (!g_dllUnloading.exchange(true)) {
		dprintf("WinDbg MCP Extension: Process termination detected, cleaning up resources...\n");
		
		// Stop the MCP server and free resources
		if (g_mcpServer) {
			g_mcpServer->Stop();
			g_mcpServer.reset();
		}
		
		// Signal the shutdown event if it exists
		if (g_shutdownEvent != nullptr) {
			SetEvent(g_shutdownEvent);
			CloseHandle(g_shutdownEvent);
			g_shutdownEvent = nullptr;
		}
	}
}

/**
 * @brief Initialize the debug extension.
 * 
 * This function is called when the extension is loaded by WinDbg.
 * It initializes the MCP server and registers command handlers.
 * 
 * @param version Pointer to a version number to be set.
 * @param flags Pointer to flags to be set.
 * @return HRESULT indicating success or failure.
 */
HRESULT __stdcall DebugExtensionInitialize(PULONG version, PULONG flags) {
	if (!version || !flags) {
		return E_POINTER;
	}

	CComPtr<IDebugClient> client;
	HRESULT hr = DebugCreate(__uuidof(IDebugClient), (void**)&client);
	if (FAILED(hr)) {
		return hr;
	}

	CComQIPtr<IDebugControl> control(client);
	hr = control->GetWindbgExtensionApis64(&ExtensionApis);
	if (FAILED(hr)) {
		return hr;
	}

	*version = DEBUG_EXTENSION_VERSION(1, 0);
	*flags = 0;

	// Create shutdown event
	g_shutdownEvent = CreateEvent(nullptr, TRUE, FALSE, nullptr);
	if (g_shutdownEvent == nullptr) {
		dprintf("Warning: Failed to create shutdown event\n");
	}
	
	// Register process exit callback for cleanup
	PVOID token = nullptr;
	if (!RegisterWaitForSingleObject(&token, GetCurrentProcess(),
		CleanupRoutine, nullptr, INFINITE, WT_EXECUTEONLYONCE)) {
		dprintf("Warning: Failed to register process exit callback\n");
	}

	// Initialize MCP server
	g_mcpServer = std::make_unique<MCPServer>();
	
	// Register command handlers
	CommandHandlers::RegisterHandlers(*g_mcpServer);
	
	// Start the server
	if (!g_mcpServer->Start()) {
		dprintf("Failed to start MCP server\n");
	} else {
		dprintf("MCP server started on pipe: %s\n", Constants::DEFAULT_PIPE_NAME);
	}

	return S_OK;
}

/**
 * @brief Display help for the extension commands.
 * 
 * @param client Pointer to the debug client.
 * @param args Command arguments.
 * @return HRESULT indicating success or failure.
 */
STDAPI help(IDebugClient* client, PCSTR args) {
	dprintf("WinDBG MCP Extension Help\n");
	dprintf("  help - show this help\n");
	dprintf("  hello - display a test message\n");
	dprintf("  objecttypes [name] - display object types filtered by 'name'\n");
	dprintf("  mcpstart - start the MCP server if not already running\n");
	dprintf("  mcpstop - stop the MCP server if running\n");
	dprintf("  mcpstatus - show MCP server status\n");

	return S_OK;
}

/**
 * @brief Display kernel object types.
 * 
 * @param client Pointer to the debug client.
 * @param args Command arguments.
 * @return HRESULT indicating success or failure.
 */
STDAPI objecttypes(IDebugClient* client, PCSTR args) {
	auto types = GetExpression("nt!ObpObjectTypes");
	if (types == 0) {
		dprintf("Failed to locate nt!ObpObjectTypes\n");
		return E_UNEXPECTED;
	}

	int count = 0;
	ULONG nameOffset;
	GetFieldOffset("nt!_OBJECT_TYPE", "Name", &nameOffset);

	while (types) {
		ULONG64 type;
		if (!ReadPointer(types, &type)) {
			break;
		}

		if (type == 0) {
			break;
		}

		ULONG totalObjects, totalHandles;
		ULONG peakObjects, peakHandles;
		UCHAR index;
		GetFieldValue(type, "nt!_OBJECT_TYPE", "Index", index);
		GetFieldValue(type, "nt!_OBJECT_TYPE", "TotalNumberOfObjects", totalObjects);
		GetFieldValue(type, "nt!_OBJECT_TYPE", "TotalNumberOfHandles", totalHandles);
		GetFieldValue(type, "nt!_OBJECT_TYPE", "HighWaterNumberOfObjects", peakObjects);
		GetFieldValue(type, "nt!_OBJECT_TYPE", "HighWaterNumberOfHandles", peakHandles);

		CComQIPtr<IDebugControl> control(client);

		control->ControlledOutput(DEBUG_OUTCTL_DML, DEBUG_OUTPUT_NORMAL,
			"%-33msu <link cmd=\"dt nt!_OBJECT_TYPE %p\">0x%p</link> %3d %8u %8u %8u %8u\n",
			type + nameOffset, type, type, index, totalObjects, totalHandles, peakObjects, peakHandles);

		types += sizeof(void*);
		count++;
	}
	dprintf("Total objects: %d\n", count);

	return S_OK;
}

/**
 * @brief Start the MCP server.
 * 
 * @param client Pointer to the debug client.
 * @param args Command arguments.
 * @return HRESULT indicating success or failure.
 */
STDAPI mcpstart(IDebugClient* client, PCSTR args) {
	if (!g_mcpServer) {
		g_mcpServer = std::make_unique<MCPServer>();
		CommandHandlers::RegisterHandlers(*g_mcpServer);
	}
	
	if (g_mcpServer->IsRunning()) {
		dprintf("MCP server is already running\n");
		return S_OK;
	}
	
	if (!g_mcpServer->Start()) {
		dprintf("Failed to start MCP server\n");
		return E_FAIL;
	}
	
	dprintf("MCP server started on pipe: %s\n", Constants::DEFAULT_PIPE_NAME);
	return S_OK;
}

/**
 * @brief Stop the MCP server.
 * 
 * @param client Pointer to the debug client.
 * @param args Command arguments.
 * @return HRESULT indicating success or failure.
 */
STDAPI mcpstop(IDebugClient* client, PCSTR args) {
	if (!g_mcpServer || !g_mcpServer->IsRunning()) {
		dprintf("MCP server is not running\n");
		return S_OK;
	}
	
	dprintf("Stopping MCP server...\n");
	g_mcpServer->Stop();
	dprintf("MCP server stopped\n");
	return S_OK;
}

/**
 * @brief Display the MCP server status.
 * 
 * @param client Pointer to the debug client.
 * @param args Command arguments.
 * @return HRESULT indicating success or failure.
 */
STDAPI mcpstatus(IDebugClient* client, PCSTR args) {
	if (!g_mcpServer) {
		dprintf("MCP server has not been initialized\n");
		return S_OK;
	}
	
	if (g_mcpServer->IsRunning()) {
		dprintf("MCP server is running on pipe: %s\n", Constants::DEFAULT_PIPE_NAME);
	} else {
		dprintf("MCP server is not running\n");
	}

	return S_OK;
}

/**
 * @brief Uninitialize the debug extension.
 * 
 * This function is called when the extension is unloaded by WinDbg.
 * It cleans up resources used by the extension.
 */
extern "C"
void CALLBACK DebugExtensionUninitialize(void) {
	// Set flag to indicate unloading
	g_dllUnloading.store(true);
	
	// Wait for a short time to let other threads complete operations
	const DWORD CLEANUP_TIMEOUT_MS = 5000; // 5 seconds
	dprintf("WinDbg MCP Extension: Uninitializing...\n");
	
	// Stop the MCP server if it's running
	if (g_mcpServer && g_mcpServer->IsRunning()) {
		dprintf("Stopping MCP server...\n");
		g_mcpServer->Stop();
	}
	
	// Free the MCP server
	g_mcpServer.reset();
	
	// Signal the shutdown event and clean up
	if (g_shutdownEvent != nullptr) {
		SetEvent(g_shutdownEvent);
		
		// Wait for potential cleanup operations to complete
		WaitForSingleObject(g_shutdownEvent, CLEANUP_TIMEOUT_MS);
		
		CloseHandle(g_shutdownEvent);
		g_shutdownEvent = nullptr;
	}
	
	dprintf("WinDbg MCP Extension: Uninitialized\n");
}

/**
 * @brief Test function to verify the extension is working.
 */
extern "C"
void CALLBACK hello(_In_ HANDLE, _In_ HANDLE, _In_ ULONG, _In_ PCSTR /*args*/) {
	dprintf("Hello from WinDbg MCP Extension!\n");
}


