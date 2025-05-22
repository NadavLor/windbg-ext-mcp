// pch.h: This is a precompiled header file.
// Files listed below are compiled only once, improving build performance for future builds.
// This also affects IntelliSense performance, including code completion and many code browsing features.
// However, files listed here are ALL re-compiled if any one of them is updated between builds.
// Do not add files here that you will be updating frequently as this negates the performance advantage.

#ifndef PCH_H
#define PCH_H

// add headers that you want to pre-compile here
#include "framework.h"

// WinDBG extension headers with appropriate definitions
#define KDEXT_64BIT
#include <Windows.h>
#include <DbgEng.h>
#include <WDBGEXTS.H>

// Additional headers for named pipes and JSON
#include <string>
#include <vector>
#include <map>
#include <thread>
#include <mutex>
#include <functional>
#include <condition_variable>
#include <atomic>
#include <queue>
#include "../include/json.hpp"

// Forward declaration for ExtensionApis - defined in types.cpp
extern "C" WINDBG_EXTENSION_APIS64 ExtensionApis;

#endif //PCH_H
