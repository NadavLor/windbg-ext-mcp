#include "pch.h"
#include <Windows.h>
#define KDEXT_64BIT
#include <DbgEng.h>
#include <WDBGEXTS.H>
#include <atlcomcli.h>
#include "ipc/mcp_server.h"
#include "command/command_handlers.h"

#pragma comment(lib, "dbgeng")

// Define the ExtensionApis object here (no redeclaration needed)
WINDBG_EXTENSION_APIS64 ExtensionApis{ sizeof(ExtensionApis) };

// Global MCP server instance
std::unique_ptr<MCPServer> g_mcpServer;

// Flag to track if the DLL is being unloaded
std::atomic<bool> g_dllUnloading(false);

// Event to signal clean shutdown
HANDLE g_shutdownEvent = NULL;

// Function to ensure cleanup on process exit
// Signature for WAITORTIMERCALLBACK is VOID CALLBACK (PVOID, BOOLEAN)
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
		if (g_shutdownEvent != NULL) {
			SetEvent(g_shutdownEvent);
			CloseHandle(g_shutdownEvent);
			g_shutdownEvent = NULL;
		}
	}
}

HRESULT __stdcall DebugExtensionInitialize(PULONG version, PULONG flags) {
	CComPtr<IDebugClient> client;
	auto hr = DebugCreate(__uuidof(IDebugClient), (void**)&client);
	if (FAILED(hr))
		return hr;

	CComQIPtr<IDebugControl> control(client);
	hr = control->GetWindbgExtensionApis64(&ExtensionApis);
	if (FAILED(hr))
		return hr;

	*version = DEBUG_EXTENSION_VERSION(1, 0);
	*flags = 0;

	// Create shutdown event
	g_shutdownEvent = CreateEvent(NULL, TRUE, FALSE, NULL);
	if (g_shutdownEvent == NULL) {
		dprintf("Warning: Failed to create shutdown event\n");
	}
	
	// Register process exit callback for cleanup
	PVOID token = NULL;
	if (!RegisterWaitForSingleObject(&token, GetCurrentProcess(),
		CleanupRoutine, NULL, INFINITE, WT_EXECUTEONLYONCE)) {
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
		dprintf("MCP server started on pipe: \\\\.\\pipe\\windbgmcp\n");
	}

	return S_OK;
}

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
		if (!ReadPointer(types, &type))
			break;

		if (type == 0)
			break;

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

// Function to start the MCP server
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
	
	dprintf("MCP server started on pipe: \\\\.\\pipe\\windbgmcp\n");
	return S_OK;
}

// Function to stop the MCP server
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

// Function to check MCP server status
STDAPI mcpstatus(IDebugClient* client, PCSTR args) {
	if (!g_mcpServer) {
		dprintf("MCP server has not been initialized\n");
		return S_OK;
	}
	
	if (g_mcpServer->IsRunning()) {
		dprintf("MCP server is running on pipe: \\\\.\\pipe\\windbgmcp\n");
	} else {
		dprintf("MCP server is not running\n");
	}

	return S_OK;
}

extern "C"
void CALLBACK DebugExtensionUninitialize(void) {
	// Set flag to indicate unloading
	g_dllUnloading.store(true);
	
	// Wait for a short time to let other threads complete operations
	const DWORD CLEANUP_TIMEOUT_MS = 5000; // 5 seconds
	dprintf("WinDbg MCP Extension: Uninitializing...\n");
	
	// Clean up MCP server
	if (g_mcpServer) {
		dprintf("WinDbg MCP Extension: Stopping MCP server...\n");
		g_mcpServer->Stop();
		g_mcpServer.reset();
		dprintf("WinDbg MCP Extension: MCP server stopped\n");
	}
	
	// Signal and wait on shutdown event if it exists
	if (g_shutdownEvent != NULL) {
		SetEvent(g_shutdownEvent);
		
		// Wait briefly for pending operations to complete
		WaitForSingleObject(g_shutdownEvent, CLEANUP_TIMEOUT_MS);
		
		// Close the event handle
		CloseHandle(g_shutdownEvent);
		g_shutdownEvent = NULL;
	}
	
	dprintf("WinDbg MCP Extension: Uninitialized\n");
}

extern "C"
void CALLBACK hello(_In_ HANDLE, _In_ HANDLE, _In_ ULONG, _In_ PCSTR /*args*/) {
	dprintf("windbgmcp-extension: hello from the MCP prototype!\n");
}


