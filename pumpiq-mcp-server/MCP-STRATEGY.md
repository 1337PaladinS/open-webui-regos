# PumpIQ MCP Server — Strategy & Implementation Plan

## 1. Executive Summary

This document defines the architecture, tool inventory, and phased rollout for a Model Context Protocol (MCP) server that exposes PumpIQ's environmental data integrations to any MCP-compatible AI client (Claude Desktop, Claude Code, Cursor, VS Code Copilot, etc.).

The server wraps four external API families — NOAA CO-OPS (tidal), NOAA CDO (precipitation), USGS NWIS (groundwater), and SFWMD DBHYDRO (regional hydrology) — into a unified, typed, AI-friendly interface with built-in rate limiting, date format normalization, error handling, and geospatial query support.

---

## 2. Architecture

```
┌─────────────────────┐
│   MCP Client        │  Claude Desktop, Cursor, VS Code, etc.
│   (AI Assistant)    │
└────────┬────────────┘
         │ JSON-RPC (stdio or SSE)
         ▼
┌─────────────────────────────────────────────┐
│        PumpIQ MCP Server (Node.js/TS)       │
│                                             │
│  ┌──────────┐ ┌──────────┐ ┌─────────────┐ │
│  │  Tools   │ │Resources │ │  Prompts    │ │
│  │ (19 ops) │ │ (5 feeds)│ │ (4 wkflows) │ │
│  └────┬─────┘ └────┬─────┘ └──────┬──────┘ │
│       │             │              │        │
│  ┌────▼─────────────▼──────────────▼──────┐ │
│  │         Shared Library                 │ │
│  │  • Date format normalization           │ │
│  │  • Rate limiter (token bucket)         │ │
│  │  • Error parser (200-with-error)       │ │
│  │  • Coordinate order normalizer         │ │
│  │  • Retry with exponential backoff      │ │
│  └────┬──────┬──────┬──────┬──────────────┘ │
└───────┼──────┼──────┼──────┼────────────────┘
        │      │      │      │
        ▼      ▼      ▼      ▼
   NOAA    NOAA    USGS    SFWMD
   CO-OPS  CDO     NWIS    DBHYDRO
   (tides) (rain)  (GW)    (regional)
```

### Transport

| Mode   | Use Case                        | Protocol    |
|--------|---------------------------------|-------------|
| stdio  | Local dev (Claude Desktop)      | JSON-RPC    |
| SSE    | Remote/hosted (production)      | HTTP + SSE  |

### Authentication Flow

- NOAA CO-OPS, USGS: No auth required (open APIs)
- NOAA CDO: Token passed via HTTP header (`token: <value>`)
- SFWMD DBhydro Insights: Bearer token (pending credentials)

Tokens are loaded from environment variables at startup, never hardcoded.

---

## 3. Tool Inventory (19 Tools)

### 3A. NOAA CO-OPS — Tidal Intelligence (5 tools)

| Tool Name                     | Method | Description                                              | Key Inputs                                |
|-------------------------------|--------|----------------------------------------------------------|-------------------------------------------|
| `noaa_get_water_levels`       | GET    | 6-min water level readings (real-time or date range)     | station, range OR start/end, datum        |
| `noaa_get_tidal_predictions`  | GET    | Harmonic-predicted tidal levels                          | station, start_date, end_date, datum      |
| `noaa_get_air_pressure`       | GET    | 6-min barometric pressure for storm correlation          | station, range                            |
| `noaa_get_station_metadata`   | GET    | Station details, coordinates, available products         | station                                   |
| `noaa_compute_high_low_tides` | —      | Derives high/low events from 6-min data (local compute)  | station, start_date, end_date             |

**Notes:**
- High/low tide is computed locally because Station 8723214 does not support the `high_low` product.
- All dates normalized to YYYYMMDD (no hyphens) for CO-OPS API.
- Quality flags parsed and surfaced in tool output.

### 3B. NOAA CDO — Precipitation Intelligence (4 tools)

| Tool Name                     | Method | Description                                              | Key Inputs                                |
|-------------------------------|--------|----------------------------------------------------------|-------------------------------------------|
| `noaa_get_daily_rainfall`     | GET    | GHCND daily precipitation (PRIMARY source)               | station, start_date, end_date             |
| `noaa_get_15min_precip`       | GET    | PRECIP_15 data (legacy, likely empty for recent dates)   | station, start_date, end_date             |
| `noaa_find_rain_gauges`       | GET    | Discover rain gauges within a bounding box               | bbox (min_lat, min_lng, max_lat, max_lng) |
| `noaa_list_datasets`          | GET    | Browse all available CDO datasets                        | limit                                     |

**Notes:**
- Rate limited: 5 req/sec, 10,000 req/day (enforced client-side).
- Dates normalized to YYYY-MM-DD (with hyphens) for CDO API.
- Tool output includes data gap warnings for PRECIP_15.

### 3C. USGS NWIS — Groundwater Intelligence (5 tools)

| Tool Name                       | Method | Description                                              | Key Inputs                                |
|---------------------------------|--------|----------------------------------------------------------|-------------------------------------------|
| `usgs_get_active_wells`         | GET    | List active GW monitoring wells in a county              | county_fips, parameter                    |
| `usgs_get_realtime_gw_levels`   | GET    | Real-time 15-min groundwater depth readings              | county_fips, period (e.g. P7D)            |
| `usgs_get_conductivity`         | GET    | Specific conductance — saltwater intrusion detection     | county_fips, period                       |
| `usgs_get_wells_by_bbox`        | GET    | Spatial search for wells in a bounding box               | bbox (min_lng, min_lat, max_lng, max_lat) |
| `usgs_list_ogc_collections`     | GET    | Browse modern USGS OGC API collections (future-proof)    | —                                         |

**Notes:**
- CRITICAL: `countyCd` must be used ALONE (never with `stateCd`).
- Parameter 62610 (128 wells) not 72019 (0 wells) for Miami-Dade.
- Bounding box format: lon,lat order (opposite of most mapping tools).

### 3D. SFWMD — Regional Hydrology (4 tools)

| Tool Name                       | Method | Description                                              | Key Inputs                                |
|---------------------------------|--------|----------------------------------------------------------|-------------------------------------------|
| `sfwmd_get_wells_by_county`     | GET    | Well locations via ArcGIS FeatureServer                  | county, limit                             |
| `sfwmd_get_wells_by_bbox`       | GET    | Spatial well query via ArcGIS envelope                   | bbox (min_lng, min_lat, max_lng, max_lat) |
| `sfwmd_get_wells_open_data`     | GET    | Wells via Open Data Hub (fallback for timeouts)          | county, limit                             |
| `sfwmd_get_hydrology_timeseries`| GET    | Time-series data (PLACEHOLDER — awaiting credentials)    | station, parameter, start_date, end_date  |

**Notes:**
- ArcGIS FeatureServer may time out from cloud. Auto-fallback to Open Data Hub.
- DBhydro Insights API requires pending SFWMD credentials.

### 3E. Cross-Cutting Utility Tool (1 tool)

| Tool Name                       | Description                                              |
|---------------------------------|----------------------------------------------------------|
| `pumpiq_ii_data_check`          | Validates data availability across all 4 sources for a given location and date range. Returns a readiness matrix showing which I&I equation inputs are available. |

---

## 4. Resources (5)

| URI                                   | Description                                           |
|---------------------------------------|-------------------------------------------------------|
| `pumpiq://env/station-registry`       | All configured monitoring stations (NOAA, USGS, SFWMD)|
| `pumpiq://env/data-gaps`              | Known data gaps and workarounds                       |
| `pumpiq://env/api-status`             | Current health/reachability of all 4 external APIs    |
| `pumpiq://env/parameter-reference`    | Parameter codes, units, and descriptions              |
| `pumpiq://env/ii-equations`           | I&I engine equation reference (what data feeds what)  |

---

## 5. Prompt Templates (4)

| Prompt Name             | Description                                                        |
|-------------------------|--------------------------------------------------------------------|
| `tidal_ii_investigation`| Pulls tidal data, compares predicted vs actual, flags anomalies    |
| `rainfall_ii_analysis`  | Correlates rainfall with flow data for storm response modeling     |
| `groundwater_assessment`| Evaluates groundwater levels and saltwater intrusion risk          |
| `full_ii_readiness`     | Runs data check across all sources, reports readiness for I&I calc |

---

## 6. Phased Rollout

### Phase 1 — Foundation (Week 1)
- Server scaffolding (stdio transport, TypeScript)
- Shared library (date normalization, rate limiter, error parsing)
- NOAA CO-OPS tools (5) — no auth, simplest integration
- Unit tests for all tools

### Phase 2 — Expand Sources (Week 2)
- NOAA CDO tools (4) — token auth, rate limiting
- USGS NWIS tools (5) — parameter validation, coord normalization
- Integration tests against live APIs

### Phase 3 — Regional & Cross-Cutting (Week 3)
- SFWMD tools (4) — ArcGIS + Open Data Hub fallback
- Cross-cutting `pumpiq_ii_data_check` tool
- All 5 resources
- All 4 prompt templates

### Phase 4 — Production Hardening (Week 4)
- SSE transport for remote deployment
- Supabase Auth integration (JWT + tenant context)
- Connection to PumpIQ's existing edge functions
- Caching layer for frequently-accessed metadata
- Monitoring, logging, and alerting
- Deployment to PumpIQ infrastructure

---

## 7. Known Risks & Mitigations

| Risk                                    | Mitigation                                           |
|-----------------------------------------|------------------------------------------------------|
| PRECIP_15 has no recent Miami-Dade data | Default to GHCND daily; flag gap in tool output      |
| NOAA returns 200 with error in body     | Parse response body for error messages, not just HTTP |
| SFWMD ArcGIS timeouts from cloud        | Auto-fallback to Open Data Hub endpoint              |
| USGS countyCd + stateCd causes 400      | Enforce countyCd-only in tool validation             |
| SFWMD credentials pending               | Placeholder tool with clear status messaging         |
| CDO rate limit (5/sec)                  | Token-bucket rate limiter in shared library           |
| Date format inconsistencies across APIs | Centralized date formatter per API family            |

---

## 8. Success Criteria

1. All 19 tools callable from Claude Desktop with correct results
2. Error messages are human-readable and include remediation guidance
3. Rate limits never exceeded (client-side enforcement)
4. Data gap warnings surfaced proactively (not silent empty results)
5. < 3 second response time for typical queries
6. Full TypeScript type safety across all tool inputs/outputs
