# 🔍 Swagger/OpenAPI Detector MCP Server

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Model Context Protocol](https://img.shields.io/badge/Protocol-MCP-blue.svg)](https://modelcontextprotocol.io/)
[![Python 3](https://img.shields.io/badge/Python-3.8%2B-green.svg)](https://www.python.org/)

A premium Model Context Protocol (MCP) server written in pure Python with **zero external dependencies** that probes target URLs, detects Swagger/OpenAPI specification endpoints, and parses them into human-readable markdown formats.

---

## ✨ Features
*   **Smart Probing**: Give it a homepage URL, and it automatically discovers specifications at common subpaths (e.g. `/swagger.json`, `/openapi.json`, `/v2/api-docs`, etc.).
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
        "/path/to/swagger-detector-mcp/check_swagger.py"
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
