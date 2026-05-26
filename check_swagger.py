#!/usr/bin/env python3
import sys
import json
import re
import urllib.request
import urllib.parse
from urllib.error import URLError, HTTPError

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
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return "swagger" in data or "openapi" in data or "swaggerVersion" in data or "paths" in data
    except json.JSONDecodeError:
        pass
    if "paths:" in text and ("swagger:" in text or "openapi:" in text):
        return True
    return False

def discover_github_repo(html_content, base_url):
    """Scans HTML content for links pointing to a GitHub repository."""
    if not html_content:
        return None
    # Look for patterns like github.com/owner/repo
    matches = re.findall(r'href=["\']https?://github\.com/([a-zA-Z0-9_\-]+)/([a-zA-Z0-9_\-]+)(?:/)?["\']', html_content)
    if matches:
        # Exclude common github pages like features, pricing, etc.
        exclusions = {"features", "pricing", "marketplace", "trending", "explore", "topics", "about", "contact"}
        for owner, repo in matches:
            if owner.lower() not in exclusions and repo.lower() not in exclusions:
                repo_url = f"https://github.com/{owner}/{repo}"
                log(f"Discovered GitHub repository link: {repo_url}")
                return owner, repo
    return None

def fetch_github_tree(owner, repo, branch="main"):
    """Fetches the file tree of a GitHub repository recursively."""
    tree_url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/{branch}?recursive=1"
    log(f"Fetching Git tree for {owner}/{repo} (branch: {branch})")
    content, _ = fetch_url(tree_url)
    
    if not content:
        if branch == "main":
            # Try master as fallback
            return fetch_github_tree(owner, repo, branch="master")
        return None
        
    try:
        data = json.loads(content)
        return data.get("tree", []), branch
    except Exception as e:
        log(f"Failed to parse Git tree: {e}")
        return None, branch

def scan_codebase_files(tree_files):
    """Scans the repository file tree for router/view configurations."""
    candidates = []
    for f in tree_files:
        path = f.get("path", "")
        # Filter files by name/path pattern
        lower_path = path.lower()
        if f.get("type") == "blob":
            # Express patterns
            if "routes" in lower_path or lower_path.endswith("app.js") or lower_path.endswith("server.js") or lower_path.endswith("routes.js") or lower_path.endswith("routes.ts"):
                candidates.append((path, "express"))
            # FastAPI/Flask patterns
            elif lower_path.endswith("main.py") or lower_path.endswith("app.py") or "views.py" in lower_path or "routes.py" in lower_path:
                candidates.append((path, "python-api"))
            # Django pattern
            elif lower_path.endswith("urls.py"):
                candidates.append((path, "django"))
            # Java Spring Boot patterns
            elif lower_path.endswith("controller.java") or lower_path.endswith("resource.java") or lower_path.endswith("controller.kt") or lower_path.endswith("resource.kt"):
                candidates.append((path, "java-spring"))
                
    return candidates

def parse_express_routes(code):
    """Extracts REST routes from Express.js Javascript/Typescript code."""
    endpoints = []
    # Pattern to match e.g. router.get('/users', ...), app.post("/api/v1/auth", ...)
    matches = re.findall(r'\.(get|post|put|delete|patch)\(\s*[\'"]([^\'\"]+)[\'"]', code)
    for method, path in matches:
        endpoints.append({
            "method": method.upper(),
            "path": path,
            "summary": f"Express route handler for {path}"
        })
    return endpoints

def parse_python_routes(code):
    """Extracts REST routes from Flask/FastAPI Python code."""
    endpoints = []
    # FastAPI decorator pattern: @router.get("/users")
    matches = re.findall(r'@(?:app|router)\.(get|post|put|delete|patch)\(\s*[\'"]([^\'\"]+)[\'"]', code)
    for method, path in matches:
        endpoints.append({
            "method": method.upper(),
            "path": path,
            "summary": f"FastAPI route handler for {path}"
        })
        
    # Flask route pattern: @app.route('/users', methods=['GET', 'POST'])
    flask_matches = re.findall(r'@(?:app|blueprint)\.route\(\s*[\'"]([^\'\"]+)[\'"](?:,\s*methods\s*=\s*\[([^\]]+)\])?', code)
    for path, methods_str in flask_matches:
        methods = ["GET"]
        if methods_str:
            # Parse e.g. 'GET', 'POST' or "PUT"
            methods = [m.strip().strip('"\'').upper() for m in methods_str.split(",")]
        for m in methods:
            endpoints.append({
                "method": m,
                "path": path,
                "summary": f"Flask route handler for {path}"
            })
            
    return endpoints

def parse_django_routes(code):
    """Extracts REST routes from Django urls.py code."""
    endpoints = []
    # Pattern: path('users/', views.list_users)
    matches = re.findall(r'path\(\s*[\'"]([^\'\"]*)[\'"]', code)
    for path in matches:
        # Django paths are default GET unless specific REST frameworks are used, list as standard endpoint
        endpoints.append({
            "method": "GET/POST",
            "path": "/" + path.strip('/'),
            "summary": f"Django path routing to {path}"
        })
    return endpoints

def parse_spring_routes(code):
    """Extracts REST routes from Java/Kotlin Spring Boot controller code."""
    endpoints = []
    
    # 1. Look for class-level RequestMapping base path
    base_path = ""
    base_match = re.search(r'@RequestMapping\(\s*(?:value\s*=\s*)?[\'"]([^\'\"]+)[\'"]', code)
    if base_match:
        base_path = base_match.group(1).rstrip('/')
        
    # 2. Extract method-level mappings
    mapping_patterns = [
        ("GET", r'@GetMapping\(\s*(?:value\s*=\s*)?[\'"]([^\'\"]+)[\'"]'),
        ("POST", r'@PostMapping\(\s*(?:value\s*=\s*)?[\'"]([^\'\"]+)[\'"]'),
        ("PUT", r'@PutMapping\(\s*(?:value\s*=\s*)?[\'"]([^\'\"]+)[\'"]'),
        ("DELETE", r'@DeleteMapping\(\s*(?:value\s*=\s*)?[\'"]([^\'\"]+)[\'"]'),
        ("PATCH", r'@PatchMapping\(\s*(?:value\s*=\s*)?[\'"]([^\'\"]+)[\'"]'),
        ("GET/POST", r'@RequestMapping\(\s*(?:value\s*=\s*)?[\'"]([^\'\"]+)[\'"]'),
    ]
    
    for method, pattern in mapping_patterns:
        matches = re.findall(pattern, code)
        for path in matches:
            # Combine base_path and path
            full_path = base_path + "/" + path.lstrip('/')
            # Clean double slashes
            full_path = "/" + full_path.strip('/')
            
            endpoints.append({
                "method": method,
                "path": full_path,
                "summary": f"Spring Boot {method} handler for {full_path}"
            })
            
    return endpoints

def generate_mcp_server(endpoints, base_url, repo_name, output_path):
    """Synthesizes discovered endpoints into a runnable Python MCP server script."""
    tools_definitions = []
    tools_handling = []
    
    # Sanitize base URL
    base_url = base_url.rstrip('/')
    
    for idx, ep in enumerate(endpoints):
        method = ep["method"]
        path = ep["path"]
        # Create a safe name for the tool
        tool_name = re.sub(r'[^a-zA-Z0-9_]', '_', f"{method.lower()}_{path.strip('/')}")
        tool_name = tool_name.strip('_')
        if not tool_name:
            tool_name = f"route_{idx}"
            
        desc = ep["summary"].replace('"', '\\"')
        
        # Tool Schema Definition
        tools_definitions.append(f"""                            {{
                                "name": "{tool_name}",
                                "description": "Queries the API endpoint {method} {path} - {desc}",
                                "inputSchema": {{
                                    "type": "object",
                                    "properties": {{
                                        "query_params": {{
                                            "type": "object",
                                            "description": "Optional dictionary of URL query parameters"
                                        }},
                                        "body": {{
                                            "type": "object",
                                            "description": "Optional JSON payload dictionary for POST/PUT requests"
                                        }}
                                    }}
                                }}
                            }}""")
        
        # Handle execution block (Use raw string replacement to prevent f-string NameErrors)
        exec_block = """                elif tool_name == "__TOOL_NAME__":
                    query_params = arguments.get("query_params", {})
                    body = arguments.get("body")
                    
                    full_path = "__PATH__"
                    # Interpolate path params if any (e.g. {id})
                    for param_k, param_v in arguments.items():
                        if param_k not in ("query_params", "body"):
                            full_path = full_path.replace(f"{{param_k}}", str(param_v))
                            full_path = full_path.replace(f"{{{param_k}}}", str(param_v))
                            
                    url = f"{BASE_URL}{full_path}"
                    if query_params:
                        url += "?" + urllib.parse.urlencode(query_params)
                        
                    log(f"Querying: __METHOD__ {url}")
                    try:
                        req_data = json.dumps(body).encode('utf-8') if body else None
                        req = urllib.request.Request(url, data=req_data, method="__METHOD__")
                        req.add_header("Content-Type", "application/json")
                        req.add_header("User-Agent", "Mozilla/5.0")
                        
                        with urllib.request.urlopen(req, timeout=10) as resp:
                            res_text = resp.read().decode('utf-8', errors='ignore')
                            result = {
                                "content": [{
                                    "type": "text",
                                    "text": f"### Response (__METHOD__ __PATH__)\\n\\n```json\\n{res_text}\\n```"
                                }],
                                "isError": False
                            }
                    except Exception as e:
                        result = {
                            "content": [{
                                "type": "text",
                                "text": f"Error querying endpoint: {e}"
                            }],
                            "isError": True
                        }"""
        exec_block = exec_block.replace("__TOOL_NAME__", tool_name)
        exec_block = exec_block.replace("__PATH__", path)
        exec_block = exec_block.replace("__METHOD__", method)
        tools_handling.append(exec_block)

    tools_def_str = ",\n".join(tools_definitions)
    tools_hand_str = "\n".join(tools_handling)

    mcp_code = """#!/usr/bin/env python3
# ====================================================================
#  AUTOMATICALLY GENERATED MCP SERVER FOR __REPO_NAME__
#  Base Target API: __BASE_URL__
# ====================================================================
import sys
import json
import urllib.request
import urllib.parse

BASE_URL = "__BASE_URL__"

def log(msg):
    sys.stderr.write(f"[LOG] {msg}\\n")
    sys.stderr.flush()

def handle_mcp_session():
    log("Starting Generated MCP Server for __REPO_NAME__...")
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
                            "name": "mcp-server-__REPO_LOWER__",
                            "version": "1.0.0"
                        }
                    }
                }
                sys.stdout.write(json.dumps(response) + "\\n")
                sys.stdout.flush()
                
            elif method == "tools/list":
                response = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "tools": [
__TOOLS_DEF_STR__
                        ]
                    }
                }
                sys.stdout.write(json.dumps(response) + "\\n")
                sys.stdout.flush()
                
            elif method == "tools/call":
                params = request.get("params", {})
                tool_name = params.get("name")
                arguments = params.get("arguments", {})
                
                result = None
                if False:
                    pass
__TOOLS_HAND_STR__
                else:
                    result = {
                        "content": [{
                            "type": "text",
                            "text": f"Unknown tool name: {tool_name}"
                        }],
                        "isError": True
                    }
                    
                response = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": result
                }
                sys.stdout.write(json.dumps(response) + "\\n")
                sys.stdout.flush()
                
        except Exception as e:
            log(f"MCP Session Error: {e}")
            break

if __name__ == "__main__":
    handle_mcp_session()
"""

    mcp_code = mcp_code.replace("__REPO_NAME__", repo_name)
    mcp_code = mcp_code.replace("__BASE_URL__", base_url)
    mcp_code = mcp_code.replace("__REPO_LOWER__", repo_name.lower())
    mcp_code = mcp_code.replace("__TOOLS_DEF_STR__", tools_def_str)
    mcp_code = mcp_code.replace("__TOOLS_HAND_STR__", tools_hand_str)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(mcp_code)
    log(f"Auto-generated MCP server code written to: {output_path}")
    return output_path

def probe_swagger(target_url):
    """Probes target URL and common subpaths for Swagger documentation."""
    log(f"Probing target URL: {target_url}")
    content, final_url = fetch_url(target_url)
    
    if content and is_swagger_spec(content):
        return content, final_url
        
    parsed = urllib.parse.urlparse(final_url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    
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
    
    urls_to_try = []
    for p in probe_paths:
        urls_to_try.append(urllib.parse.urljoin(final_url, p.lstrip('/')))
        urls_to_try.append(urllib.parse.urljoin(base_url, p.lstrip('/')))
        
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
    spec_info = {
        "title": "Swagger/OpenAPI Service (YAML)",
        "version": "Unknown",
        "description": "",
        "endpoints": []
    }
    title_match = re.search(r"title:\s*['\"]?([^'\"\n]+)", yaml_text)
    if title_match:
        spec_info["title"] = title_match.group(1).strip()
        
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
                in_paths = False
                continue
            path_match = re.match(r"^['\"]?(/[^'\":]+)['\"]?:", stripped)
            if path_match:
                current_path = path_match.group(1)
                method_indent = indent
                continue
            if current_path and indent > method_indent:
                method_match = re.match(r"^(get|post|put|delete|patch|options|head):", stripped)
                if method_match:
                    current_method = method_match.group(1).upper()
                    spec_info["endpoints"].append({
                        "path": current_path,
                        "method": current_method,
                        "summary": "",
                        "parameters": "Unknown (YAML format limit)"
                    })
    return spec_info

def format_endpoints_to_markdown(spec_info, spec_url):
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

def run_codebase_pipeline(owner, repo, base_url):
    """Executes the complete codebase API scanner & MCP generation pipeline."""
    log(f"Starting Codebase API Parser for: {owner}/{repo}")
    tree_files, branch = fetch_github_tree(owner, repo)
    if not tree_files:
        return f"Error: Could not retrieve file tree for GitHub repository {owner}/{repo}."
        
    candidates = scan_codebase_files(tree_files)
    if not candidates:
        return f"Scan Complete: No framework routing files (Express, FastAPI, Flask, Django, Spring Boot) detected in {owner}/{repo}."
        
    log(f"Found {len(candidates)} routing files. Starting static code analysis...")
    endpoints = []
    
    for path, framework in candidates:
        raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}"
        log(f"Downloading & Parsing ({framework}): {path}")
        code, _ = fetch_url(raw_url)
        if not code:
            continue
            
        file_endpoints = []
        if framework == "express":
            file_endpoints = parse_express_routes(code)
        elif framework == "python-api":
            file_endpoints = parse_python_routes(code)
        elif framework == "django":
            file_endpoints = parse_django_routes(code)
        elif framework == "java-spring":
            file_endpoints = parse_spring_routes(code)
            
        for ep in file_endpoints:
            # Augment summary with file info
            ep["summary"] += f" (parsed from `{path}`)"
            endpoints.append(ep)
            
    # Deduplicate parsed endpoints by Method & Path
    unique_endpoints = []
    seen_endpoints = set()
    for ep in endpoints:
        key = (ep["method"], ep["path"])
        if key not in seen_endpoints:
            seen_endpoints.add(key)
            unique_endpoints.append(ep)
            
    if not unique_endpoints:
        return f"Scan Complete: Routing files were scanned, but no REST paths could be extracted from {owner}/{repo}."
        
    # Auto-generate the custom MCP server!
    output_mcp_path = f"./generated_mcp_{repo}.py"
    generate_mcp_server(unique_endpoints, base_url, repo, output_mcp_path)
    
    # Format a beautiful Markdown report
    md = []
    md.append(f"# 🔍 Codebase API Scan Report: {owner}/{repo}")
    md.append(f"**Target Host Base URL:** `{base_url}`\n")
    md.append(f"Successfully scanned **{len(candidates)}** code routing files and extracted **{len(unique_endpoints)}** REST endpoint mappings.\n")
    md.append("## 🛠️ Auto-Generated MCP Server")
    md.append(f"An executable, standard-compliant Python MCP server has been automatically generated for this codebase!")
    md.append(f"*   **Server Path:** `{output_mcp_path}`")
    md.append(f"*   **Exposed Tools:** Every discovered API endpoint has been converted into an individual, executable MCP tool. Calling these tools executes live HTTP requests against the base URL!")
    md.append("\n## 📋 Discovered API Endpoints\n")
    md.append("| Method | Path | Discovered Routing File |")
    md.append("| :--- | :--- | :--- |")
    for ep in unique_endpoints:
        md.append(f"| `{ep['method']}` | `{ep['path']}` | {ep['summary']} |")
        
    return "\n".join(md)

def run_pipeline(target_url):
    """Router pipeline that determines whether to probe Swagger or scan codebase."""
    # 1. Check if the URL is directly a GitHub repo
    gh_match = re.search(r'github\.com/([a-zA-Z0-9_\-]+)/([a-zA-Z0-9_\-]+)', target_url)
    if gh_match:
        owner, repo = gh_match.group(1), gh_match.group(2)
        base_api_url = f"https://api.{repo}.com" # Mock fallback
        # Let's try to assume base URL is the standard domain related to repo, or ask mock
        return run_codebase_pipeline(owner, repo, "https://api.example.com")
        
    # 2. Fetch target URL
    content, final_url = fetch_url(target_url)
    if not content:
        return f"Error: Could not retrieve content from: {target_url}"
        
    # 3. If it contains a Swagger/OpenAPI spec, parse it!
    if is_swagger_spec(content):
        info = parse_swagger_spec(content)
        return format_endpoints_to_markdown(info, final_url)
        
    # 4. Probe common subpaths for Swagger documentation
    spec_text, spec_url = probe_swagger(target_url)
    if spec_text:
        info = parse_swagger_spec(spec_text)
        return format_endpoints_to_markdown(info, spec_url)
        
    # 5. If Swagger not found, scan for any linked GitHub repositories (open codebase)!
    log("Swagger documentation not found. Scanning HTML for open-source codebase links...")
    repo_info = discover_github_repo(content, final_url)
    if repo_info:
        owner, repo = repo_info
        parsed = urllib.parse.urlparse(final_url)
        base_api_url = f"{parsed.scheme}://{parsed.netloc}"
        return run_codebase_pipeline(owner, repo, base_api_url)
        
    return f"Scan Complete: Swagger documentation was not found, and no public GitHub repositories could be discovered from: {target_url}"

def run_cli(target_url):
    report = run_pipeline(target_url)
    print(report)

def handle_mcp_session():
    log("Starting Create MCP (Swagger/Codebase) server session...")
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
                            "name": "create-mcp",
                            "version": "1.1.0"
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
                                "description": "Inspects a URL to automatically discover APIs. Probes for Swagger/OpenAPI docs. If not found, it automatically scans the page's HTML to locate any public GitHub repositories (open codebase), analyzes the backend code files (Express, Flask, FastAPI, Django), lists all REST paths, and auto-generates a custom, runnable Python MCP server for it!",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "url": {
                                            "type": "string",
                                            "description": "The target website URL or direct GitHub repository URL to scan"
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
                    report = run_pipeline(url)
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
