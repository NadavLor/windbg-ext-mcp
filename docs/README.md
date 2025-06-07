# WinDbg MCP Extension Documentation

Welcome to the complete documentation for the WinDbg MCP Extension - a powerful tool for automated kernel debugging and malware analysis.

## 📚 **Documentation Index**

### **🚀 Getting Started**
- [**Getting Started Guide**](getting-started.md) - Complete setup and first steps
- [**Architecture Overview**](architecture.md) - Understanding the hybrid design
- [**Installation Guide**](installation.md) - Step-by-step installation

### **🛠️ Tool References**
- [**📖 MCP Tools Reference**](mcp-tools-reference.md) - **Complete tool documentation** ⭐
- [**Security Researcher's Guide**](security-guide.md) - Advanced malware analysis
- [**Performance Optimization**](performance-guide.md) - VM debugging optimization

### **🔧 Advanced Topics**
- [**API Reference**](api-reference.md) - C++ extension API
- [**Troubleshooting Guide**](troubleshooting.md) - Common issues and solutions
- [**Contributing Guide**](contributing.md) - Development and contribution

### **💡 Examples & Workflows**
- [**Example Workflows**](examples/) - Real-world debugging scenarios
- [**Security Use Cases**](security-use-cases.md) - EDR evasion and analysis
- [**Performance Benchmarks**](performance-benchmarks.md) - Optimization results

---

## 🎯 **Quick Navigation**

### **For First-Time Users**
1. Start with [Getting Started Guide](getting-started.md)
2. Follow [Installation Guide](installation.md)
3. Review [MCP Tools Reference](mcp-tools-reference.md)

### **For Security Researchers**
1. Read [Security Researcher's Guide](security-guide.md)
2. Explore [MCP Tools Reference - Security Section](mcp-tools-reference.md#security-research)
3. Try [Example Workflows](examples/)

### **For Performance Optimization**
1. Check [Performance Guide](performance-guide.md)
2. Review [MCP Tools Reference - Performance Section](mcp-tools-reference.md#performance-tools)
3. See [Performance Benchmarks](performance-benchmarks.md)

### **For Troubleshooting**
1. Use [Troubleshooting Guide](troubleshooting.md)
2. Check [MCP Tools Reference - Support Section](mcp-tools-reference.md#support--troubleshooting-tools)
3. Run diagnostic tools from the extension

---

## 🆕 **What's New**

### **Latest Features**
- ✅ **Unified Callback Enumeration:** `mcp_list_callbacks` tool for comprehensive EDR detection
- ✅ **LLM Automation:** Safe execution control commands now enabled
- ✅ **Hybrid Architecture:** Python + C++ for optimal performance and usability
- ✅ **Network Debugging:** Enhanced VM debugging with packet loss tolerance
- ✅ **Session Recovery:** Robust session management and automatic recovery
- ✅ **Performance Optimization:** Async execution and intelligent caching

### **Recent Updates**
- 🔧 **Fixed:** Duplicate handler registrations in C++ extension
- 📚 **Added:** Comprehensive tool documentation with 25+ tools
- 🚀 **Enhanced:** Error handling with guided troubleshooting
- ⚡ **Improved:** Performance optimization for network debugging

---

## 📊 **Project Statistics**

- **🛠️ Tools Available:** 25+ MCP tools
- **🏗️ Architecture:** Hybrid Python/C++ design
- **🔧 Commands Supported:** 100+ WinDbg commands with safety validation
- **🌐 Network Support:** Optimized for VM-based kernel debugging
- **🛡️ Safety Features:** Comprehensive validation and error recovery
- **📈 Performance:** Up to 10x faster with optimization enabled

---

## 🤝 **Community & Support**

### **Getting Help**
- Use the built-in `get_help()` tool for immediate assistance
- Check [Troubleshooting Guide](troubleshooting.md) for common issues
- Review [FAQ](faq.md) for frequently asked questions

### **Contributing**
- Read [Contributing Guide](contributing.md) for development setup
- Check [API Reference](api-reference.md) for extension development
- Submit issues and feature requests on GitHub

### **Resources**
- **GitHub Repository:** [windbg-ext-mcp](https://github.com/yourusername/windbg-ext-mcp)
- **Discord Community:** Join our debugging community
- **Blog Posts:** [Advanced Windows Debugging](https://blog.example.com)

---

## 📝 **License & Credits**

This project is licensed under the MIT License. See [LICENSE](../LICENSE) for details.

**Built with:**
- Microsoft WinDbg SDK
- Python 3.8+ with FastMCP
- Modern C++17
- JSON for Modern C++

**Special Thanks:**
- Microsoft Debugging Tools team
- WinDbg community contributors
- Security researchers and malware analysts 