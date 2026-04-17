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


@mcp.tool()
def get_schema_fields(name: str) -> dict:
    """Get detailed field breakdown for a schema including required vs optional, types, and descriptions.

    Args:
        name: Schema name (e.g., 'ContainerConfig', 'Volume', 'AuthConfig')
    """
    definitions = spec.get("definitions", spec.get("components", {}).get("schemas", {}))

    # Fuzzy match
    match = next((k for k in definitions if k.lower() == name.lower()), None)
    if not match:
        return {
            "error": f"Schema '{name}' not found",
            "hint": "Use get_definition() for exact name or search_schemas() to find by field",
        }

    schema = definitions[match]
    properties = schema.get("properties", {})
    required = schema.get("required", [])

    fields = {"required": [], "optional": []}

    for field_name, field_details in properties.items():
        field_info = {
            "name": field_name,
            "type": field_details.get("type", "object"),
            "description": field_details.get("description", "")[:200],
        }

        # Handle $ref
        if "$ref" in field_details:
            ref_name = field_details["$ref"].split("/")[-1]
            field_info["type"] = f"ref:{ref_name}"

        # Handle array items
        if field_details.get("type") == "array" and "items" in field_details:
            items = field_details["items"]
            if "$ref" in items:
                ref_name = items["$ref"].split("/")[-1]
                field_info["type"] = f"array[{ref_name}]"
            else:
                field_info["type"] = f"array[{items.get('type', 'unknown')}]"

        # Handle format
        if "format" in field_details:
            field_info["format"] = field_details["format"]

        if field_name in required:
            fields["required"].append(field_info)
        else:
            fields["optional"].append(field_info)

    return {
        "schema": match,
        "type": schema.get("type", "object"),
        "title": schema.get("title", ""),
        "description": schema.get("description", "")[:500],
        "total_fields": len(properties),
        "required_count": len(fields["required"]),
        "optional_count": len(fields["optional"]),
        "fields": fields,
    }


@mcp.tool()
def find_schema_usage(name: str) -> dict:
    """Find where a schema is used in the API (as request body or response).

    Args:
        name: Schema name to search for (e.g., 'Container', 'Volume')
    """
    definitions = spec.get("definitions", spec.get("components", {}).get("schemas", {}))

    # Fuzzy match
    match = next((k for k in definitions if k.lower() == name.lower()), None)
    if not match:
        return {"error": f"Schema '{name}' not found"}

    ref_pattern = f"#/definitions/{match}"
    alt_ref_pattern = f"#/components/schemas/{match}"

    used_in_requests = []
    used_in_responses = []
    used_in_params = []

    for path, methods in spec.get("paths", {}).items():
        for method, details in methods.items():
            if method not in ("get", "post", "put", "delete", "patch"):
                continue

            # Check parameters
            for param in details.get("parameters", []):
                schema_ref = param.get("schema", {}).get("$ref", "")
                if match in schema_ref:
                    used_in_params.append(
                        {
                            "path": path,
                            "method": method.upper(),
                            "param_name": param.get("name"),
                        }
                    )

            # Check request body
            body = details.get("parameters", [])
            for param in body:
                if param.get("in") == "body":
                    schema_ref = param.get("schema", {}).get("$ref", "")
                    if match in schema_ref:
                        used_in_requests.append(
                            {
                                "path": path,
                                "method": method.upper(),
                                "operationId": details.get("operationId", ""),
                            }
                        )

            # Check responses
            for code, resp in details.get("responses", {}).items():
                schema_ref = resp.get("schema", {}).get("$ref", "")
                if match in schema_ref:
                    used_in_responses.append(
                        {
                            "path": path,
                            "method": method.upper(),
                            "status_code": code,
                            "operationId": details.get("operationId", ""),
                        }
                    )

    return {
        "schema": match,
        "used_as_request": used_in_requests,
        "used_as_response": used_in_responses,
        "used_in_parameters": used_in_params,
        "total_usages": len(used_in_requests)
        + len(used_in_responses)
        + len(used_in_params),
    }


@mcp.tool()
def get_schema_dependencies(name: str) -> dict:
    """Get all schemas that this schema references (nested dependencies).

    Args:
        name: Schema name to analyze
    """
    definitions = spec.get("definitions", spec.get("components", {}).get("schemas", {}))

    # Fuzzy match
    match = next((k for k in definitions if k.lower() == name.lower()), None)
    if not match:
        return {"error": f"Schema '{name}' not found"}

    schema = definitions[match]
    dependencies = set()

    def extract_refs(obj, depth=0):
        if depth > 10:  # Prevent infinite recursion
            return
        if isinstance(obj, dict):
            if "$ref" in obj:
                ref_name = obj["$ref"].split("/")[-1]
                dependencies.add(ref_name)
            for value in obj.values():
                extract_refs(value, depth + 1)
        elif isinstance(obj, list):
            for item in obj:
                extract_refs(item, depth + 1)

    extract_refs(schema)

    return {
        "schema": match,
        "dependencies": sorted(dependencies),
        "dependency_count": len(dependencies),
    }


@mcp.tool()
def search_schemas(keyword: str) -> list[dict]:
    """Search schemas by name, field name, or description.

    Args:
        keyword: Search term to match against schema names, fields, or descriptions
    """
    definitions = spec.get("definitions", spec.get("components", {}).get("schemas", {}))
    keyword_lower = keyword.lower()
    results = []

    for name, schema in definitions.items():
        score = 0
        matched_fields = []

        # Match on schema name
        if keyword_lower in name.lower():
            score += 10

        # Match on description
        desc = schema.get("description", "")
        if keyword_lower in desc.lower():
            score += 3

        # Match on field names
        for field_name, field_details in schema.get("properties", {}).items():
            if keyword_lower in field_name.lower():
                score += 5
                matched_fields.append(field_name)
            elif keyword_lower in field_details.get("description", "").lower():
                score += 2
                matched_fields.append(field_name)

        if score > 0:
            results.append(
                {
                    "name": name,
                    "score": score,
                    "matched_fields": matched_fields[:10],
                    "field_count": len(schema.get("properties", {})),
                    "description": desc[:150] if desc else "",
                }
            )

    return sorted(results, key=lambda x: -x["score"])[:30]


@mcp.tool()
def generate_example(name: str) -> dict:
    """Generate an example JSON object from a schema definition.

    Args:
        name: Schema name to generate example for
    """
    definitions = spec.get("definitions", spec.get("components", {}).get("schemas", {}))

    # Fuzzy match
    match = next((k for k in definitions if k.lower() == name.lower()), None)
    if not match:
        return {"error": f"Schema '{name}' not found"}

    schema = definitions[match]

    def generate_value(prop_def, visited=None):
        if visited is None:
            visited = set()

        # Handle $ref
        if "$ref" in prop_def:
            ref_name = prop_def["$ref"].split("/")[-1]
            if ref_name in visited:
                return {"$ref": ref_name}  # Avoid cycles
            if ref_name in definitions:
                visited.add(ref_name)
                result = generate_value(definitions[ref_name], visited)
                visited.discard(ref_name)
                return result
            return {ref_name: "..."}

        prop_type = prop_def.get("type", "object")

        if prop_type == "string":
            if "format" in prop_def:
                fmt = prop_def["format"]
                if fmt == "date-time":
                    return "2024-01-15T10:30:00Z"
                elif fmt == "date":
                    return "2024-01-15"
                elif fmt == "uri":
                    return "https://example.com"
                elif fmt == "email":
                    return "user@example.com"
                elif fmt == "int64" or fmt == "int32":
                    return 12345
            if "enum" in prop_def:
                return prop_def["enum"][0]
            example = prop_def.get("example") or prop_def.get("default")
            if example:
                return example
            return "string"

        elif prop_type == "integer":
            return prop_def.get("default", 42)

        elif prop_type == "number":
            return prop_def.get("default", 3.14)

        elif prop_type == "boolean":
            return prop_def.get("default", True)

        elif prop_type == "array":
            items = prop_def.get("items", {})
            return [generate_value(items, visited.copy())]

        elif prop_type == "object":
            result = {}
            props = prop_def.get("properties", {})
            for pname, pdetails in list(props.items())[:10]:  # Limit depth
                result[pname] = generate_value(pdetails, visited.copy())
            return result

        return None

    example = generate_value(schema)
    return {
        "schema": match,
        "example": example,
        "note": "Generated from schema structure. Adjust values as needed.",
    }


@mcp.tool()
def list_schemas() -> dict:
    """List all available schema definitions with basic info."""
    definitions = spec.get("definitions", spec.get("components", {}).get("schemas", {}))

    schemas = []
    for name, schema in definitions.items():
        props = schema.get("properties", {})
        schemas.append(
            {
                "name": name,
                "type": schema.get("type", "object"),
                "field_count": len(props),
                "description": (schema.get("description") or schema.get("title", ""))[
                    :100
                ],
            }
        )

    return {
        "total": len(schemas),
        "schemas": sorted(schemas, key=lambda x: x["name"]),
    }


import os

if __name__ == "__main__":
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    # If using SSE, we usually need to specify the host and port
    if transport == "sse":
        mcp.run(transport="sse", host="0.0.0.0", port=8000)
    else:
        mcp.run(transport="stdio")
