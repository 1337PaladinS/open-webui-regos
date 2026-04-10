#!/usr/bin/env node

/**
 * PumpIQ MCP Server — Entry Point
 *
 * Launches the MCP server with stdio transport (default) for use with
 * Claude Desktop, Claude Code, Cursor, VS Code, and other MCP clients.
 *
 * Usage:
 *   npx tsx src/index.ts          # Development
 *   node dist/index.js            # Production (after tsc build)
 *
 * Environment Variables:
 *   NOAA_CDO_TOKEN     — Required for NOAA CDO precipitation tools
 *   SFWMD_API_KEY      — Optional, for SFWMD DBhydro Insights API (pending)
 *
 * Claude Desktop config (~/.claude/claude_desktop_config.json):
 *   {
 *     "mcpServers": {
 *       "pumpiq": {
 *         "command": "npx",
 *         "args": ["tsx", "/path/to/pumpiq-mcp-server/src/index.ts"],
 *         "env": {
 *           "NOAA_CDO_TOKEN": "your-token-here"
 *         }
 *       }
 *     }
 *   }
 */

import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { createServer } from "./server.js";

async function main(): Promise<void> {
  const server = createServer();
  const transport = new StdioServerTransport();

  await server.connect(transport);

  // Graceful shutdown
  process.on("SIGINT", async () => {
    await server.close();
    process.exit(0);
  });

  process.on("SIGTERM", async () => {
    await server.close();
    process.exit(0);
  });
}

main().catch((err) => {
  console.error("Fatal error starting PumpIQ MCP server:", err);
  process.exit(1);
});
