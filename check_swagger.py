#!/usr/bin/env python3
import sys
import json
import re
import urllib.request
import urllib.parse
from urllib.error import URLError, HTTPError

# Helper for logging to stderr so we do not corrupt MCP stdout
def log(msg):
    sys.stderr.write(f"[LOG] {msg}\n")
    sys.stderr.flush()

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/html, */*"
}

def fetch_url(url):
    """Fetches a URL and returns string data and final URL (after redirects)."""
    try:
        req = urllib.request.Request(url, headers=DEFAULT_HEADERS)
        with urllib.request.urlopen(req, timeout=10) as response:
            content = response.read()
            final_url = response.geturl()
            # Try to decode content
            for encoding in ('utf-8', 'latin-1', 'utf-16'):
                try:
                    return content.decode(encoding), final_url
                except UnicodeDecodeError:
                    continue
            return content.decode('utf-8', errors='ignore'), final_url
    except Exception as e:
        log(f"Error fetching {url}: {e}")
        return None, url

def is_swagger_spec(text):
    """Heuristic to check if text is a Swagger or OpenAPI specification."""
    if not text:
        return False
    # Check if JSON
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            # Swagger 2.0 or OpenAPI 3.0+ indicators
            has_version = "swagger" in data or "openapi" in data or "swaggerVersion" in data
            has_paths = "paths" in data
            return has_version or has_paths
    except json.JSONDecodeError:
        pass
    
    # Check if YAML (heuristic)
    if "paths:" in text and ("swagger:" in text or "openapi:" in text):
        return True
        
    return False

def probe_swagger(target_url):
    """Probes the target URL and common paths for a Swagger specification."""
    log(f"Probing target URL: {target_url}")
    content, final_url = fetch_url(target_url)
    
    if content and is_swagger_spec(content):
        return content, final_url
        
    # If not a spec, maybe it's a page hosting Swagger UI or a base URL.
    # Check common subpaths.
    parsed = urllib.parse.urlparse(final_url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    
    # Try relative paths from current folder too
    path_parts = parsed.path.rstrip('/').split('/')
    folder_url = f"{parsed.scheme}://{parsed.netloc}"
    if len(path_parts) > 1:
        folder_url += "/".join(path_parts[:-1])
        
    probe_paths = [
        "/swagger.json",
        "/openapi.json",
        "/swagger-ui.html",
        "/swagger/v1/swagger.json",
        "/v2/api-docs",
        "/v3/api-docs",
        "/swagger.yaml",
        "/openapi.yaml",
        "/api-docs",
        "/api/swagger.json"
    ]
    
    # Generate complete list of URLs to probe
    urls_to_try = []
    # 1. Probing relative to folder
    for p in probe_paths:
        urls_to_try.append(urllib.parse.urljoin(final_url, p.lstrip('/')))
        urls_to_try.append(urllib.parse.urljoin(base_url, p.lstrip('/')))
        
    # Remove duplicates preserving order
    seen = set()
    urls_to_try = [x for x in urls_to_try if not (x in seen or seen.add(x))]
    
    for url in urls_to_try:
        log(f"Probing: {url}")
        c, f_url = fetch_url(url)
        if c and is_swagger_spec(c):
            log(f"Found spec at: {f_url}")
            return c, f_url
            
    return None, None

def parse_swagger_spec(spec_text):
    """Parses standard JSON Swagger/OpenAPI spec."""
    try:
        data = json.loads(spec_text)
    except json.JSONDecodeError:
        # Simple fallback parser for YAML if we couldn't parse as JSON
        log("Spec is not JSON. Attempting basic YAML parsing...")
        return parse_basic_yaml(spec_text)
        
    spec_info = {
        "title": data.get("info", {}).get("title", "Swagger/OpenAPI Service"),
        "version": data.get("info", {}).get("version", "1.0.0"),
        "description": data.get("info", {}).get("description", ""),
        "endpoints": []
    }
    
    paths = data.get("paths", {})
    for path, path_data in paths.items():
        if not isinstance(path_data, dict):
            continue
        for method, method_data in path_data.items():
            if method.lower() not in ("get", "post", "put", "delete", "patch", "options", "head"):
                continue
            
            summary = method_data.get("summary") or method_data.get("description") or ""
            summary = summary.replace("\n", " ").strip()
            if len(summary) > 100:
                summary = summary[:97] + "..."
                
            parameters = []
            for param in method_data.get("parameters", []):
                if isinstance(param, dict) and "name" in param:
                    param_type = param.get("type") or param.get("schema", {}).get("type") or "string"
                    req = "required" if param.get("required") else "optional"
                    parameters.append(f"{param['name']} ({param_type}, {req})")
                    
            spec_info["endpoints"].append({
                "path": path,
                "method": method.upper(),
                "summary": summary,
                "parameters": ", ".join(parameters) if parameters else "None"
            })
            
    return spec_info

def parse_basic_yaml(yaml_text):
    """Extremely simplified regex-based YAML parser for paths & methods."""
    spec_info = {
        "title": "Swagger/OpenAPI Service (YAML)",
        "version": "Unknown",
        "description": "",
        "endpoints": []
    }
    
    # Try to find a title
    title_match = re.search(r"title:\s*['\"]?([^'\"\n]+)", yaml_text)
    if title_match:
        spec_info["title"] = title_match.group(1).strip()
        
    # Extract paths using a simple scanner
    lines = yaml_text.splitlines()
    in_paths = False
    current_path = None
    current_method = None
    paths_indent = 0
    method_indent = 0
    
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
            
        indent = len(line) - len(line.lstrip())
        
        if stripped == "paths:":
            in_paths = True
            paths_indent = indent
            continue
            
        if in_paths:
            if indent <= paths_indent and stripped != "paths:":
                # Out of paths section
                in_paths = False
                continue
                
            # Detect path endpoint (e.g., /users:)
            path_match = re.match(r"^['\"]?(/[^'\":]+)['\"]?:", stripped)
            if path_match:
                current_path = path_match.group(1)
                method_indent = indent
                continue
                
            # Detect method (e.g., get:, post:)
            if current_path and indent > method_indent:
                method_match = re.match(r"^(get|post|put|delete|patch|options|head):", stripped)
                if method_match:
                    current_method = method_match.group(1).upper()
                    
                    # Look for summary in upcoming lines
                    summary = ""
                    spec_info["endpoints"].append({
                        "path": current_path,
                        "method": current_method,
                        "summary": summary,
                        "parameters": "Unknown (YAML format limit)"
                    })
                    
    return spec_info

def format_endpoints_to_markdown(spec_info, spec_url):
    """Formats parsed specification into a beautiful markdown report."""
    md = []
    md.append(f"# {spec_info['title']} (v{spec_info['version']})")
    md.append(f"**Specification URL:** [{spec_url}]({spec_url})\n")
    if spec_info['description']:
        md.append(f"{spec_info['description']}\n")
        
    md.append("## Supported API Endpoints\n")
    md.append("| Method | Path | Summary | Parameters |")
    md.append("| :--- | :--- | :--- | :--- |")
    
    if not spec_info['endpoints']:
        md.append("| - | No endpoints found | - | - |")
    else:
        for ep in spec_info['endpoints']:
            md.append(f"| `{ep['method']}` | `{ep['path']}` | {ep['summary']} | {ep['parameters']} |")
            
    return "\n".join(md)

def run_cli(target_url):
    """CLI execution wrapper."""
    spec_text, final_url = probe_swagger(target_url)
    if not spec_text:
        print(f"Error: Could not locate a Swagger/OpenAPI specification at: {target_url}", file=sys.stderr)
        sys.exit(1)
        
    info = parse_swagger_spec(spec_text)
    report = format_endpoints_to_markdown(info, final_url)
    print(report)

def handle_mcp_session():
    """Handles an MCP stdio JSON-RPC session."""
    log("Starting Swagger MCP server session...")
    
    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break
                
            request = json.loads(line.strip())
            method = request.get("method")
            req_id = request.get("id")
            
            if method == "initialize":
                response = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {
                            "tools": {}
                        },
                        "serverInfo": {
                            "name": "swagger-api-finder",
                            "version": "1.0.0"
                        }
                    }
                }
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()
                
            elif method == "tools/list":
                response = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "tools": [
                            {
                                "name": "check_swagger",
                                "description": "Checks a URL to see if it hosts a Swagger/OpenAPI specification. If found, lists all supported endpoints, methods, and parameters.",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "url": {
                                            "type": "string",
                                            "description": "The base URL or specific documentation URL to inspect"
                                        }
                                    },
                                    "required": ["url"]
                                }
                            }
                        ]
                    }
                }
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()
                
            elif method == "tools/call":
                params = request.get("params", {})
                tool_name = params.get("name")
                arguments = params.get("arguments", {})
                url = arguments.get("url")
                
                if tool_name == "check_swagger" and url:
                    spec_text, final_url = probe_swagger(url)
                    if spec_text:
                        info = parse_swagger_spec(spec_text)
                        report = format_endpoints_to_markdown(info, final_url)
                        result = {
                            "content": [
                                {
                                    "type": "text",
                                    "text": report
                                }
                            ],
                            "isError": False
                        }
                    else:
                        result = {
                            "content": [
                                {
                                    "type": "text",
                                    "text": f"Error: Could not locate a Swagger/OpenAPI specification at: {url}"
                                }
                            ],
                            "isError": True
                        }
                else:
                    result = {
                        "content": [
                            {
                                "type": "text",
                                "text": f"Unknown tool or missing 'url' argument: {tool_name}"
                            }
                        ],
                        "isError": True
                    }
                    
                response = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": result
                }
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()
                
        except Exception as e:
            log(f"MCP Session Error: {e}")
            break

if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--url":
        run_cli(sys.argv[2])
    else:
        handle_mcp_session()
