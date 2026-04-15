import json
import os
from pathlib import Path
from typing import Optional

import redis
import yaml
from fastmcp import FastMCP

spec_text = Path("swagger-latest.yaml").read_text()
spec = yaml.safe_load(spec_text)
mcp = FastMCP(name="Podman API Docs")

r = redis.Redis(
    host=os.environ.get("REDIS_HOST", ""),
    port=int(os.environ.get("REDIS_PORT", 6379)),
    decode_responses=True,
    username=os.environ.get("REDIS_USERNAME", ""),
    password=os.environ.get("REDIS_PASSWORD", ""),
)


def list_endpoints() -> list[dict]:
    """List all available Podman API endpoints with their HTTP method and summary."""
    cache_key = "list_endpoints"
    cached = r.get(cache_key)
    if cached:
        return json.loads(cached)  # type: ignore[str]
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
    r.set(cache_key, json.dumps(results), ex=3600)
    return results


@mcp.tool()
def get_endpoint(path: str, method: str) -> dict:
    """Get full details for a specific endpoint including parameters, request body, and responses."""
    cache_key = f"endpoint:{path}:{method.lower()}"
    cached = r.get(cache_key)
    if cached:
        return json.loads(cached)  # type: ignore[str]
    method = method.lower()
    paths = spec.get("paths", {})
    if path not in paths:
        result = {"error": f"Path '{path}' not found"}
    elif method not in paths[path]:
        result = {"error": f"Method '{method.upper()}' not found for '{path}'"}
    else:
        result = paths[path][method]
    r.set(cache_key, json.dumps(result), ex=3600)
    return result


@mcp.tool()
def get_definition(name: str) -> dict:
    """Get a schema definition by name (e.g. 'Container', 'ContainerBasicConfig')."""
    cache_key = f"definition:{name}"
    cached = r.get(cache_key)
    if cached:
        return json.loads(cached)  # type: ignore[str]
    definitions = spec.get("definitions", spec.get("components", {}).get("schemas", {}))
    if name not in definitions:
        # fuzzy: case-insensitive match
        match = next((k for k in definitions if k.lower() == name.lower()), None)
        if not match:
            result = {
                "error": f"Definition '{name}' not found",
                "available": sorted(definitions.keys())[:50],
            }
        else:
            result = definitions[match]
            cache_key = f"definition:{match}"  # cache under the matched name
    else:
        result = definitions[name]
    r.set(cache_key, json.dumps(result), ex=3600)
    return result


@mcp.tool()
def search_endpoints(keyword: str) -> list[dict]:
    """Search endpoints by keyword in path, summary, description, or tags."""
    keyword_lower = keyword.lower()
    cache_key = f"search:{keyword_lower}"
    cached = r.get(cache_key)
    if cached:
        return json.loads(cached)  # type: ignore[str]
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
    r.set(cache_key, json.dumps(results), ex=3600)
    return results


@mcp.tool()
def get_api_info() -> dict:
    """Get general info about the Podman API: title, version, description."""
    cache_key = "api_info"
    cached = r.get(cache_key)
    if cached:
        return json.loads(cached)  # type: ignore[str]
    info = spec.get("info", {})
    result = {
        "title": info.get("title"),
        "version": info.get("version"),
        "description": info.get("description", "")[:500],
        "base_path": spec.get("basePath", "/"),
        "host": spec.get("host", ""),
    }
    r.set(cache_key, json.dumps(result), ex=3600)
    return result


if __name__ == "__main__":
    mcp.run()
