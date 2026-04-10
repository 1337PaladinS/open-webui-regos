/**
 * PumpIQ MCP Server — Server Definition
 *
 * Registers all tools, resources, and prompts with the MCP server instance.
 */

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { registerNoaaCoopsTools } from "./tools/noaa-coops.js";
import { registerNoaaCdoTools } from "./tools/noaa-cdo.js";
import { registerUsgsNwisTools } from "./tools/usgs-nwis.js";
import { registerSfwmdTools } from "./tools/sfwmd.js";
import { registerIIReadinessTools } from "./tools/ii-readiness.js";
import { registerResources } from "./resources/index.js";
import { registerPrompts } from "./prompts/index.js";

export function createServer(): McpServer {
  const server = new McpServer({
    name: "PumpIQ Environmental Data",
    version: "1.0.0",
  });

  // ─── Tools (19 total) ────────────────────────────────────────────
  registerNoaaCoopsTools(server);    // 5 tools
  registerNoaaCdoTools(server);      // 4 tools
  registerUsgsNwisTools(server);     // 5 tools
  registerSfwmdTools(server);        // 4 tools
  registerIIReadinessTools(server);  // 1 tool

  // ─── Resources (4) ───────────────────────────────────────────────
  registerResources(server);

  // ─── Prompts (4) ─────────────────────────────────────────────────
  registerPrompts(server);

  return server;
}
