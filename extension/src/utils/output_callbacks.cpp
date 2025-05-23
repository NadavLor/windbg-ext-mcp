/**
 * @file output_callbacks.cpp
 * @brief Implementation of OutputCallbacks class for capturing WinDbg output.
 */
#include "pch.h"
#include "utils/output_callbacks.h"
#include <algorithm>

OutputCallbacks::OutputCallbacks() : m_refCount(1) {
}

OutputCallbacks::~OutputCallbacks() = default;

// IUnknown methods
STDMETHODIMP OutputCallbacks::QueryInterface(
    __in REFIID InterfaceId,
    __out PVOID* Interface
) {
    if (!Interface) {
        return E_POINTER;
    }

    *Interface = nullptr;

    if (IsEqualIID(InterfaceId, __uuidof(IUnknown)) ||
        IsEqualIID(InterfaceId, __uuidof(IDebugOutputCallbacks))) {
        *Interface = this;
        AddRef();
        return S_OK;
    }

    return E_NOINTERFACE;
}

STDMETHODIMP_(ULONG) OutputCallbacks::AddRef() {
    return InterlockedIncrement(&m_refCount);
}

STDMETHODIMP_(ULONG) OutputCallbacks::Release() {
    LONG retVal = InterlockedDecrement(&m_refCount);
    if (retVal == 0) {
        delete this;
    }
    return retVal;
}

// IDebugOutputCallbacks methods
STDMETHODIMP OutputCallbacks::Output(
    __in ULONG Mask,
    __in PCSTR Text
) {
    // Append the output text to our buffer
    if (!Text) {
        return S_OK;
    }
    
    const std::string textStr(Text);

    // Check for various types of messages
    if (textStr.find("WARNING: .cache forcedecodeuser is not enabled") != std::string::npos) {
        // This is a common warning, not a fatal error - log but continue
        m_output += "Note: " + textStr + "\n";
    }
    else if (textStr.find("is not extension gallery command") != std::string::npos) {
        // Extract the command name
        const size_t pos = textStr.find(" is not extension gallery command");
        if (pos != std::string::npos) {
            const std::string cmdName = textStr.substr(0, pos);
            if (!m_extensionError) {
                // Provide a more helpful error message
                if (cmdName == "modinfo") {
                    m_output += "Note: The !modinfo command is not available. Using alternative lmv command instead.\n";
                } else {
                    m_output += "Error: Command '" + cmdName + "' is not available. Make sure the required extension is loaded.\n";
                }
                m_extensionError = true;
            }
        }
        else {
            m_output += textStr;
        }
    }
    else if (textStr.find("No export") != std::string::npos && textStr.find("found") != std::string::npos) {
        // Handle "No export" errors
        const size_t pos = textStr.find(" found");
        if (pos != std::string::npos) {
            const std::string cmdName = textStr.substr(9, pos - 9);  // Extract name after "No export "
            if (!m_exportError) {
                m_output += "Note: Command '" + cmdName + "' is not available in the current debugging context.\n";
                m_exportError = true;
            }
        }
        else {
            m_output += textStr;
        }
    }
    else {
        m_output += textStr;
    }
    
    return S_OK;
}

std::string OutputCallbacks::GetOutput() const {
    // If the output exceeds a reasonable size, truncate it and add a note
    if (m_output.size() > MAX_OUTPUT_SIZE) {
        std::string truncated = m_output.substr(0, MAX_OUTPUT_SIZE);
        truncated += "\n[Output truncated. Result too large (exceeded " + 
                     std::to_string(MAX_OUTPUT_SIZE) + " bytes)]";
        return truncated;
    }
    return m_output;
}

void OutputCallbacks::Clear() {
    m_output.clear();
    m_extensionError = false;
    m_exportError = false;
} 