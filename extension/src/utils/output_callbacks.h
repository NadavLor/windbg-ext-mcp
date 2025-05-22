/**
 * @file output_callbacks.h
 * @brief Defines a class to capture WinDbg debugger output.
 */
#pragma once

#include "pch.h"
#include <Windows.h>
#include <DbgEng.h>
#include <string>

// Maximum size for command output to prevent excessive memory usage
constexpr size_t MAX_OUTPUT_SIZE = 1024 * 1024; // 1MB

/**
 * @class OutputCallbacks
 * @brief Implements IDebugOutputCallbacks to capture debugger output.
 * 
 * This class is used to intercept and store output from WinDbg commands.
 */
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

    /**
     * @brief Get the captured output.
     * @return A string containing the captured output.
     */
    [[nodiscard]] std::string GetOutput() const;
    
    /**
     * @brief Clear the captured output buffer.
     */
    void Clear();

private:
    std::string m_output;        ///< Buffer storing captured output
    LONG m_refCount;             ///< Reference count for COM interface
    bool m_extensionError{false}; ///< Flag indicating if an extension error occurred
    bool m_exportError{false};    ///< Flag indicating if an export error occurred
}; 