#pragma once

#include "pch.h"
#include <Windows.h>
#include <DbgEng.h>
#include <string>

// Maximum size for command output to prevent excessive memory usage
constexpr size_t MAX_OUTPUT_SIZE = 1024 * 1024; // 1MB

// Class to capture debugger output
class OutputCallbacks : public IDebugOutputCallbacks {
public:
    OutputCallbacks();
    virtual ~OutputCallbacks();

    // IUnknown methods
    STDMETHOD(QueryInterface)(
        __in REFIID InterfaceId,
        __out PVOID* Interface
    );
    STDMETHOD_(ULONG, AddRef)();
    STDMETHOD_(ULONG, Release)();

    // IDebugOutputCallbacks methods
    STDMETHOD(Output)(
        __in ULONG Mask,
        __in PCSTR Text
    );

    // Get the captured output
    std::string GetOutput() const;
    
    // Clear the captured output
    void Clear();

private:
    std::string m_output;
    LONG m_refCount;
    bool m_extensionError = false;
    bool m_exportError = false;
}; 