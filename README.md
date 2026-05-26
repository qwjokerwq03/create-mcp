# 🔍 Create MCP (Swagger/OpenAPI Detector)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Model Context Protocol](https://img.shields.io/badge/Protocol-MCP-blue.svg)](https://modelcontextprotocol.io/)
[![Python 3](https://img.shields.io/badge/Python-3.8%2B-green.svg)](https://www.python.org/)

A premium Model Context Protocol (MCP) server written in pure Python with **zero external dependencies** that probes target URLs to detect Swagger/OpenAPI documentation. If the codebase is open-source (GitHub), it automatically performs static code analysis to map REST routes and **auto-generates a fully functional, custom Python MCP server** for that website on the fly!

---

## ✨ Features
*   **Smart Probing**: Give it a homepage URL, and it automatically discovers specifications at common subpaths (e.g. `/swagger.json`, `/openapi.json`, `/v2/api-docs`, etc.).
*   **Open Codebase API Scanner**: If Swagger is not found, the tool automatically scans the webpage's HTML to locate its public GitHub repository. It then uses public tree APIs to inspect its codebase structure.
*   **Multi-Framework Support**: Statically scans and extracts REST routes from Express.js (JS/TS), FastAPI/Flask (Python), and Django (Python) controllers, routers, and URL configurations.
*   **Auto-generated Custom MCP Server**: Automatically synthesizes discovered endpoints into a self-contained, fully compliant `generated_mcp_<repo>.py` Python server! Each discovered endpoint is converted into an executable MCP tool that performs live HTTP requests against the base URL.
*   **Multi-format Parsing**: Robustly parses both JSON and basic YAML OpenAPI formats.
*   **Comprehensive Summaries**: Renders all routes, HTTP methods (`GET`, `POST`, etc.), parameters, types, and descriptions in a clear markdown structure.

---

## 🛠️ Configuration & Installation

Register the server in your environment's configuration file (e.g., `mcp_config.json`, `claude_desktop_config.json`, or the Antigravity CLI config):

```json
{
  "mcpServers": {
    "swagger-api-finder": {
      "command": "python3",
      "args": [
        "/path/to/create-mcp/check_swagger.py"
      ]
    }
  }
}
```

---

## 💻 Manual CLI Usage

This script supports **dual-mode execution**, allowing you to use it as a standard command-line tool in addition to an MCP server.

*   **Inspect an API from a documentation URL:**
    ```bash
    python3 check_swagger.py --url https://petstore.swagger.io/v2/swagger.json
    ```

---

## 🔍 Search Keywords (SEO Tags)
*   `model-context-protocol`, `mcp-server`, `swagger`, `openapi`, `api-detector`, `api-explorer`, `python-mcp`, `mcp-tools`, `antigravity-skill`, `gemini-mcp`, `claude-desktop-mcp`, `zero-dependencies-mcp`.

---

## 📄 License
This project is licensed under the [MIT License](LICENSE).
