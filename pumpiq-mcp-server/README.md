# PumpIQ MCP Server

MCP (Model Context Protocol) server that exposes PumpIQ's environmental data integrations to AI assistants. Query tidal levels, precipitation, groundwater, and regional hydrology data from NOAA, USGS, and SFWMD through natural language.

## Quick Start

```bash
# Install dependencies
cd pumpiq-mcp-server
npm install

# Run in development mode
NOAA_CDO_TOKEN=your-token-here npx tsx src/index.ts

# Build for production
npm run build
NOAA_CDO_TOKEN=your-token-here node dist/index.js
```

## Connect to Claude Desktop

Add to `~/.claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "pumpiq": {
      "command": "npx",
      "args": ["tsx", "/absolute/path/to/pumpiq-mcp-server/src/index.ts"],
      "env": {
        "NOAA_CDO_TOKEN": "your-noaa-cdo-token"
      }
    }
  }
}
```

Restart Claude Desktop. You should see "PumpIQ Environmental Data" in your MCP connections.

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `NOAA_CDO_TOKEN` | Yes | NOAA Climate Data Online API token. Get one free at https://www.ncdc.noaa.gov/cdo-web/token |
| `SFWMD_API_KEY` | No | SFWMD DBhydro Insights API key (pending — email DataRequests@sfwmd.gov) |

## Available Tools (19)

### NOAA CO-OPS — Tidal Intelligence (no auth required)

| Tool | Description |
|------|-------------|
| `noaa_get_water_levels` | 6-min water level readings (real-time or historical) |
| `noaa_get_tidal_predictions` | Harmonic-predicted tidal levels |
| `noaa_get_air_pressure` | 6-min barometric pressure for storm correlation |
| `noaa_get_station_metadata` | Station details, coordinates, available products |
| `noaa_compute_high_low_tides` | Derives high/low events from raw 6-min data |

### NOAA CDO — Precipitation Intelligence (token required)

| Tool | Description |
|------|-------------|
| `noaa_get_daily_rainfall` | GHCND daily precipitation (PRIMARY source) |
| `noaa_get_15min_precip` | PRECIP_15 legacy data (empty for recent Miami-Dade dates) |
| `noaa_find_rain_gauges` | Discover rain gauges in a bounding box |
| `noaa_list_datasets` | Browse all NOAA CDO datasets |

### USGS NWIS — Groundwater Intelligence (no auth required)

| Tool | Description |
|------|-------------|
| `usgs_get_active_wells` | List active GW wells in a county |
| `usgs_get_realtime_gw_levels` | Real-time 15-min groundwater depth |
| `usgs_get_conductivity` | Specific conductance for saltwater intrusion |
| `usgs_get_wells_by_bbox` | Spatial well search in a bounding box |
| `usgs_list_ogc_collections` | Modern USGS OGC API (future replacement) |

### SFWMD — Regional Hydrology

| Tool | Description |
|------|-------------|
| `sfwmd_get_wells_by_county` | Wells from ArcGIS FeatureServer |
| `sfwmd_get_wells_by_bbox` | Spatial well query via ArcGIS |
| `sfwmd_get_wells_open_data` | Wells via Open Data Hub (reliable fallback) |
| `sfwmd_get_hydrology_timeseries` | Time-series data (PLACEHOLDER — awaiting credentials) |

### Cross-Cutting

| Tool | Description |
|------|-------------|
| `pumpiq_ii_data_check` | Validate data availability for all I&I equations |

## Resources

| URI | Description |
|-----|-------------|
| `pumpiq://env/station-registry` | Configured monitoring stations |
| `pumpiq://env/data-gaps` | Known data gaps and workarounds |
| `pumpiq://env/parameter-reference` | Parameter codes, units, date formats |
| `pumpiq://env/ii-equations` | I&I equation-to-data-source mapping |

## Prompt Templates

| Prompt | Description |
|--------|-------------|
| `tidal_ii_investigation` | Investigate tidal influence on I&I |
| `rainfall_ii_analysis` | Analyze rainfall patterns for RDII |
| `groundwater_assessment` | Evaluate GW levels and saltwater intrusion |
| `full_ii_readiness` | Check data availability for all I&I equations |

## Example Conversations

**"What's the current tidal level at Virginia Key?"**
→ Calls `noaa_get_water_levels` with default station 8723214

**"How much rain fell in Miami last week?"**
→ Calls `noaa_get_daily_rainfall` with GHCND station for the date range

**"Are there any groundwater wells near Opa-Locka?"**
→ Calls `usgs_get_wells_by_bbox` with Opa-Locka bounding box coordinates

**"Can we run I&I analysis for March 2026?"**
→ Calls `pumpiq_ii_data_check` to assess data readiness across all sources

## Project Structure

```
pumpiq-mcp-server/
├── src/
│   ├── index.ts              # Entry point (stdio transport)
│   ├── server.ts             # MCP server definition
│   ├── tools/
│   │   ├── noaa-coops.ts     # 5 tidal tools
│   │   ├── noaa-cdo.ts       # 4 precipitation tools
│   │   ├── usgs-nwis.ts      # 5 groundwater tools
│   │   ├── sfwmd.ts          # 4 regional hydrology tools
│   │   └── ii-readiness.ts   # 1 cross-cutting tool
│   ├── resources/
│   │   └── index.ts          # 4 data resources
│   ├── prompts/
│   │   └── index.ts          # 4 workflow prompts
│   └── lib/
│       ├── config.ts         # URLs, defaults, env vars
│       ├── dates.ts          # Date format normalization
│       ├── http.ts           # HTTP client with retry
│       ├── rate-limiter.ts   # Token bucket rate limiter
│       └── types.ts          # TypeScript type definitions
├── package.json
├── tsconfig.json
├── MCP-STRATEGY.md           # Architecture and implementation plan
└── README.md                 # This file
```

## Deploy with Open WebUI (Docker Compose)

The PumpIQ MCP server can run as a containerized service alongside Open WebUI, exposing all 19 tools to any model through the chat interface.

### Prerequisites

- Docker and Docker Compose installed
- The `open-webui-regos` repository cloned
- (Optional) A free NOAA CDO API token from https://www.ncdc.noaa.gov/cdo-web/token

### Architecture

```
┌─────────────────────────────────────────────────────┐
│  Docker Compose Network                             │
│                                                     │
│  ┌──────────────┐    HTTP :8001    ┌──────────────┐ │
│  │  open-webui  │ ──────────────── │  pumpiq-mcp  │ │
│  │  (port 3000) │   MCP tools      │  MCPO bridge │ │
│  └──────────────┘                  │  ┌──────────┐│ │
│                                    │  │ PumpIQ   ││ │
│                                    │  │ MCP svr  ││ │
│                                    │  │ (stdio)  ││ │
│                                    │  └──────────┘│ │
│                                    └──────┬───────┘ │
└───────────────────────────────────────────┼─────────┘
                                            │ HTTPS
                              ┌─────────────┼─────────────┐
                              │             │             │
                         NOAA CO-OPS   USGS NWIS    SFWMD
                         NOAA CDO
```

MCPO (MCP-to-OpenAPI proxy) runs inside the container, wrapping the stdio-based MCP server into an HTTP endpoint that Open WebUI can consume natively.

### Step 1 — Add your API tokens to `.env`

In the repository root, add to your `.env` file:

```bash
# PumpIQ MCP Server (optional — 15 of 19 tools work without tokens)
NOAA_CDO_TOKEN=your-noaa-cdo-token-here
SFWMD_API_KEY=
```

### Step 2 — Build and start the service

```bash
cd open-webui-regos

# Build and start just PumpIQ (if Open WebUI is already running)
docker compose up -d --build pumpiq-mcp

# Or start everything together
docker compose up -d --build
```

Verify it's running:

```bash
# Check the container is healthy
docker ps | grep pumpiq

# Check the Swagger docs are accessible
curl -s http://localhost:8001/docs | head -5
```

You should see the Swagger UI HTML. Visit `http://localhost:8001/docs` in your browser to see all 19 tools listed.

### Step 3 — Register in Open WebUI

1. Open **http://localhost:3000** (Open WebUI)
2. Go to **Admin Settings → External Tools**
3. Click **+ Add Server**
4. Configure:
   - **Type:** MCP (Streamable HTTP)
   - **URL:** `http://pumpiq-mcp:8001`
   - **Auth:** None
5. Click **Save**

> **Important:** Use the Docker service name `pumpiq-mcp` (not `localhost` or `host.docker.internal`) since both containers are on the same Docker Compose network.

### Step 4 — Use the tools in a chat

1. Open a new chat in Open WebUI
2. Click the **tools icon** (+ or wrench icon near the chat input)
3. Toggle on the PumpIQ tools you want
4. Ask a question — the model will call the appropriate tool automatically

Example queries:

| Query | Tool triggered |
|-------|----------------|
| "What's the current tide level at Virginia Key?" | `noaa_get_water_levels` |
| "How much rain fell in Miami last week?" | `noaa_get_daily_rainfall` |
| "Show me groundwater wells near Opa-Locka" | `usgs_get_wells_by_bbox` |
| "Can we run I&I analysis for this month?" | `pumpiq_ii_data_check` |
| "What's the saltwater intrusion risk in Miami-Dade?" | `usgs_get_conductivity` |

### Updating the server

After making changes to the PumpIQ MCP source code:

```bash
docker compose up -d --build pumpiq-mcp
```

This rebuilds the container with your changes and restarts it. Open WebUI will automatically reconnect.

### Troubleshooting

| Issue | Fix |
|-------|-----|
| "Failed to connect to MCP server" in Open WebUI | Make sure URL is `http://pumpiq-mcp:8001` (service name, not localhost) |
| Tools not showing in chat | Click the tools/+ icon in the chat input area and toggle them on |
| NOAA CDO tools return auth errors | Add `NOAA_CDO_TOKEN` to `.env` and restart: `docker compose up -d pumpiq-mcp` |
| Container won't start | Check logs: `docker logs pumpiq-mcp` |
| Swagger UI not loading | Verify port isn't in use: `lsof -i :8001` |

---

## Standalone Usage (without Docker)

### Claude Desktop

Add to `~/.claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "pumpiq": {
      "command": "npx",
      "args": ["tsx", "/absolute/path/to/pumpiq-mcp-server/src/index.ts"],
      "env": {
        "NOAA_CDO_TOKEN": "your-noaa-cdo-token"
      }
    }
  }
}
```

### Local MCPO (without Docker)

If you want to run MCPO directly on your machine (e.g., for development):

```bash
cd pumpiq-mcp-server
npm install && npm run build

# Install MCPO
pipx install mcpo   # or: pip install mcpo

# Start the bridge
NOAA_CDO_TOKEN=your-token mcpo --port 8001 -- node $(pwd)/dist/index.js
```

Then register in Open WebUI with URL `http://host.docker.internal:8001`.

---

## How PumpIQ Connects to RegOS

PumpIQ provides **operational data** (what's actually happening with water levels, rainfall, groundwater) and RegOS provides **regulatory intelligence** (what the code requires, what thresholds apply, when reports are due).

Together they enable compliance intelligence:

1. **PumpIQ** reports: "Groundwater at Well X is 3.2 ft NGVD, conductivity is 1,400 µS/cm"
2. **RegOS** responds: "Chapter 24 Section 24-42.3 requires conductivity below 1,000 µS/cm. You're in violation. Penalty structure per Section 24-50 applies."

This is the MVP architecture agreed upon by the team — PumpIQ queries Open WebUI/RegOS with hard-coded knowledge of how to ask, RegOS handles the reasoning, and the response flows back as a complete compliance assessment.

### I&I Equations Mapped to Data Sources

| Equation | What it measures | PumpIQ data source |
|----------|-----------------|-------------------|
| Eq2 — GWI | Groundwater infiltration into sewer pipes | USGS groundwater levels |
| Eq3 — TI | Tidal infiltration in coastal areas | NOAA tidal levels |
| Eq4 — RDII | Rainfall-driven inflow through pipe cracks | NOAA daily rainfall |
| Eq5 — SWI | Saltwater intrusion into freshwater aquifer | USGS conductivity |

---

## Known Limitations

1. **15-min rainfall data unavailable** — PRECIP_15 stopped reporting in Miami-Dade by 2014. Daily GHCND is the primary source.
2. **SFWMD time series pending** — DBhydro Insights API credentials not yet obtained.
3. **SFWMD ArcGIS timeouts** — Cloud environments may experience timeouts; Open Data Hub is the fallback.
4. **Single-region defaults** — Currently configured for Miami-Dade (FIPS 12086). Extend config for other regions.

## License

Proprietary — APAS/Regos.ai
