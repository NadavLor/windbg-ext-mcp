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
	// Clean up MCP server
	if (g_mcpServer) {
		g_mcpServer->Stop();
		g_mcpServer.reset();
	}
}

extern "C"
void CALLBACK hello(_In_ HANDLE, _In_ HANDLE, _In_ ULONG, _In_ PCSTR /*args*/) {
	dprintf("windbgmcp-extension: hello from the MCP prototype!\n");
}


