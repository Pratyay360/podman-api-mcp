import json
from pathlib import Path

import yaml
from fastmcp import FastMCP

spec_text = Path("swagger-latest.yaml").read_text()
spec = yaml.safe_load(spec_text)
mcp = FastMCP(name="Podman API Docs")


@mcp.tool()
def list_endpoints() -> list[dict]:
    """List all available Podman API endpoints with their HTTP method and summary."""
    results = []
    for path, methods in spec.get("paths", {}).items():
        for method, details in methods.items():
            if method in ("get", "post", "put", "delete", "patch"):
                results.append(
                    {
                        "method": method.upper(),
                        "path": path,
                        "operationId": details.get("operationId", ""),
                        "summary": details.get(
                            "summary",
                            details.get("description", "")[:120]
                            if details.get("description")
                            else "",
                        ),
                        "tags": details.get("tags", []),
                    }
                )
    return results


@mcp.tool()
def get_endpoint(path: str, method: str) -> dict:
    """Get full details for a specific endpoint including parameters, request body, and responses."""
    method = method.lower()
    paths = spec.get("paths", {})
    if path not in paths:
        return {"error": f"Path '{path}' not found"}
    elif method not in paths[path]:
        return {"error": f"Method '{method.upper()}' not found for '{path}'"}
    else:
        return paths[path][method]


@mcp.tool()
def get_definition(name: str) -> dict:
    """Get a schema definition by name (e.g. 'Container', 'ContainerBasicConfig')."""
    definitions = spec.get("definitions", spec.get("components", {}).get("schemas", {}))
    if name not in definitions:
        # fuzzy: case-insensitive match
        match = next((k for k in definitions if k.lower() == name.lower()), None)
        if not match:
            return {
                "error": f"Definition '{name}' not found",
                "available": sorted(definitions.keys())[:50],
            }
        else:
            return definitions[match]
    else:
        return definitions[name]


@mcp.tool()
def search_endpoints(keyword: str) -> list[dict]:
    """Search endpoints by keyword in path, summary, description, or tags."""
    keyword_lower = keyword.lower()
    results = []
    for path, methods in spec.get("paths", {}).items():
        for method, details in methods.items():
            if method not in ("get", "post", "put", "delete", "patch"):
                continue
            haystack = " ".join(
                [
                    path,
                    details.get("summary", ""),
                    details.get("description", ""),
                    " ".join(details.get("tags", [])),
                    details.get("operationId", ""),
                ]
            ).lower()
            if keyword_lower in haystack:
                results.append(
                    {
                        "method": method.upper(),
                        "path": path,
                        "operationId": details.get("operationId", ""),
                        "summary": details.get("summary", ""),
                        "tags": details.get("tags", []),
                    }
                )
    return results


@mcp.tool()
def get_api_info() -> dict:
    """Get general info about the Podman API: title, version, description."""
    info = spec.get("info", {})
    return {
        "title": info.get("title"),
        "version": info.get("version"),
        "description": info.get("description", "")[:500],
        "base_path": spec.get("basePath", "/"),
        "host": spec.get("host", ""),
    }


import os

if __name__ == "__main__":
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    # If using SSE, we usually need to specify the host and port
    if transport == "sse":
        mcp.run(transport="sse", host="0.0.0.0", port=8000)
    else:
        mcp.run(transport="stdio")
