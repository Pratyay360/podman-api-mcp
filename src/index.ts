import { Hono } from "hono";
import { createMcpHandler } from "mcp-handler";
import { Scalar } from "@scalar/hono-api-reference";
import { z } from "zod";
import yaml from "js-yaml";
// import { de } from "zod/v4/locales";

const app = new Hono();

// Accept parsed spec object directly
function extractRoutesFromSpec(spec: any) {
  const routes: Array<{
    path: string;
    method: string;
    operationId?: string;
    summary?: string;
    tags?: string[];
  }> = [];

  if (spec.paths) {
    for (const [path, methods] of Object.entries(spec.paths)) {
      for (const [method, operation] of Object.entries(methods as any)) {
        if (
          ["get", "post", "put", "delete", "patch", "head", "options"].includes(
            method,
          )
        ) {
          routes.push({
            path,
            method: method.toUpperCase(),
            operationId: (operation as any).operationId,
            summary: (operation as any).summary,
            tags: (operation as any).tags,
          });
        }
      }
    }
  }

  return {
    info: spec.info,
    routes: routes.sort((a, b) => a.path.localeCompare(b.path)),
  };
}

// Helper to fetch and parse OpenAPI spec (handles both JSON and YAML)
async function fetchAndParseSpec(url: string) {
  const response = await fetch(url);
  const text = await response.text();
  // yaml.load works for JSON as well (JSON is valid YAML)
  return yaml.load(text);
}

const handler = createMcpHandler(
  (server) => {
    server.tool(
      "list-podman-routes",
      "List all Podman API routes from the latest swagger spec",
      async () => {
        const spec = await fetchAndParseSpec(
          "https://storage.googleapis.com/libpod-master-releases/swagger-latest.yaml",
        );
        const data = extractRoutesFromSpec(spec);
        return {
          content: [
            {
              type: "text",
              text: `Podman API v${data.info?.version}\n\n${JSON.stringify(data.routes, null, 2)}`,
            },
          ],
        };
      },
    );

    server.tool(
      "list-docker-routes",
      "List all Docker Engine API routes (v1.43)",
      async () => {
        const spec = await fetchAndParseSpec(
          "https://docs.docker.com/reference/api/engine/version/v1.54.yaml",
        );
        const data = extractRoutesFromSpec(spec);
        return {
          content: [
            {
              type: "text",
              text: `Docker API v${data.info?.version}\n\n${JSON.stringify(data.routes, null, 2)}`,
            },
          ],
        };
      },
    );

    server.tool(
      "search",
      "Search for a specific route by path or operationId",
      {
        query: z.string().describe("Search term for path or operationId"),
        api: z.enum(["podman", "docker"]).describe("Which API to search"),
      },
      async ({ query, api }) => {
        const url =
          api === "podman"
            ? "https://storage.googleapis.com/libpod-master-releases/swagger-latest.yaml"
            : "https://docs.docker.com/reference/api/engine/version/v1.54.yaml";

        const spec = await fetchAndParseSpec(url);
        const { routes } = extractRoutesFromSpec(spec);

        const results = routes.filter(
          (r) =>
            r.path.toLowerCase().includes(query.toLowerCase()) ||
            r.operationId?.toLowerCase().includes(query.toLowerCase()),
        );

        return {
          content: [
            {
              type: "text",
              text: `Found ${results.length} matching routes in ${api} API:\n${JSON.stringify(results, null, 2)}`,
            },
          ],
        };
      },
    );
  },
  {},
  {
    basePath: "/",
    maxDuration: 60,
    verboseLogs: true,
  },
);

app.all("/mcp/*", async (c) => {
  return await handler(c.req.raw);
});

app.get("/", (c) => {
  return c.json({
    message: "Hono MCP Server - info socket",
    endpoints: {
      mcp: "/mcp",
      description:
        "MCP server with info about the server and available endpoints in podman and docker .",
    },
    tools: ["list-podman-routes", "list-docker-routes", "search"],
  });
});

app.get(
  "/podman",
  Scalar({
    url: "https://storage.googleapis.com/libpod-master-releases/swagger-latest.yaml",
    proxyUrl: "https://proxy.scalar.com",
  }),
);

app.get(
  "/docker",
  Scalar({
    url: "https://docs.docker.com/reference/api/engine/version/v1.54.yaml",
    proxyUrl: "https://proxy.scalar.com",
  }),
);

export default app;
