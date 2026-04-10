/**
 * PumpIQ MCP Server — Resources
 *
 * Resources are read-only data feeds that MCP clients can pull as context.
 * They complement tools (which are action-oriented) by providing
 * reference data the AI can use to interpret results.
 */

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { DEFAULTS } from "../lib/config.js";

export function registerResources(server: McpServer): void {
  // 1. Station Registry
  server.resource(
    "station-registry",
    "pumpiq://env/station-registry",
    {
      description:
        "All configured monitoring stations across NOAA, USGS, and SFWMD with their IDs, coordinates, and data products.",
      mimeType: "application/json",
    },
    async () => ({
      contents: [
        {
          uri: "pumpiq://env/station-registry",
          mimeType: "application/json",
          text: JSON.stringify(
            {
              noaa_coops: [
                {
                  id: DEFAULTS.noaa_station,
                  name: "Virginia Key, Biscayne Bay, FL",
                  lat: 25.7314,
                  lon: -80.1618,
                  products: [
                    "water_level",
                    "predictions",
                    "air_pressure",
                  ],
                  notes:
                    "Does NOT support high_low product. Compute from 6-min data.",
                },
              ],
              noaa_cdo: [
                {
                  id: DEFAULTS.noaa_cdo_station,
                  name: "Miami International Airport (COOP)",
                  dataset: "PRECIP_15",
                  status: "INACTIVE — no data since 2014",
                },
                {
                  id: DEFAULTS.noaa_ghcnd_station,
                  name: "Miami International Airport (GHCND)",
                  dataset: "GHCND",
                  status: "ACTIVE — daily precipitation confirmed for 2026",
                },
              ],
              usgs: {
                county_fips: DEFAULTS.miami_dade_fips,
                parameters: [
                  {
                    code: DEFAULTS.usgs_gw_param,
                    name: "GW level above NGVD 1929",
                    unit: "feet",
                    active_wells: 128,
                  },
                  {
                    code: DEFAULTS.usgs_conductivity_param,
                    name: "Specific conductance",
                    unit: "µS/cm",
                    active_sites: 50,
                    use: "Saltwater intrusion detection",
                  },
                ],
              },
              sfwmd: {
                arcgis_server: "May time out from cloud — use Open Data Hub",
                open_data_hub: "Accessible from anywhere",
                dbhydro_api: "PENDING — awaiting credentials from DataRequests@sfwmd.gov",
              },
            },
            null,
            2
          ),
        },
      ],
    })
  );

  // 2. Known Data Gaps
  server.resource(
    "data-gaps",
    "pumpiq://env/data-gaps",
    {
      description:
        "Known data gaps, API quirks, and workarounds for all external data sources.",
      mimeType: "application/json",
    },
    async () => ({
      contents: [
        {
          uri: "pumpiq://env/data-gaps",
          mimeType: "application/json",
          text: JSON.stringify(
            [
              {
                source: "NOAA CDO — PRECIP_15",
                issue:
                  "All Miami-Dade stations stopped reporting 15-min precipitation between 2003-2014",
                impact: "No sub-daily rainfall data available",
                workaround: "Use GHCND daily data (confirmed working for 2026)",
                future:
                  "Investigate api.weather.gov hourly observations or NWS QPE radar data",
              },
              {
                source: "NOAA CO-OPS — high_low product",
                issue:
                  "Station 8723214 does NOT support the high_low product",
                impact:
                  "API returns 200 OK but error in body (misleading!)",
                workaround:
                  "Use noaa_compute_high_low_tides to derive from 6-min water_level data",
              },
              {
                source: "SFWMD ArcGIS FeatureServer",
                issue: "Times out from cloud hosting environments",
                impact: "Cannot query well locations from hosted apps",
                workaround: "Use SFWMD Open Data Hub (always accessible)",
              },
              {
                source: "USGS NWIS",
                issue:
                  "Combining countyCd with stateCd causes HTTP 400",
                impact: "Silent query failure",
                workaround:
                  "Use countyCd ALONE — never combine with stateCd",
                fixed_in: "V2 of Postman collection",
              },
              {
                source: "USGS NWIS — parameter 72019",
                issue: "Zero wells in Miami-Dade use parameter 72019",
                impact: "Queries return empty results",
                workaround:
                  "Use parameter 62610 (128 active wells in Miami-Dade)",
                fixed_in: "V2 of Postman collection",
              },
              {
                source: "SFWMD DBhydro Insights API",
                issue: "Credentials not yet obtained",
                impact: "Time-series hydrology data unavailable",
                workaround:
                  "Use USGS NWIS for groundwater levels. Email DataRequests@sfwmd.gov for access.",
              },
            ],
            null,
            2
          ),
        },
      ],
    })
  );

  // 3. Parameter Reference
  server.resource(
    "parameter-reference",
    "pumpiq://env/parameter-reference",
    {
      description:
        "Parameter codes, units, date format requirements, and coordinate conventions for each API.",
      mimeType: "application/json",
    },
    async () => ({
      contents: [
        {
          uri: "pumpiq://env/parameter-reference",
          mimeType: "application/json",
          text: JSON.stringify(
            {
              date_formats: {
                "NOAA CO-OPS": "YYYYMMDD (no hyphens)",
                "NOAA CDO": "YYYY-MM-DD (with hyphens)",
                "USGS NWIS": "ISO 8601 period (P1D, P7D, P30D)",
              },
              coordinate_order: {
                "USGS bBox": "minLON,minLAT,maxLON,maxLAT (longitude FIRST!)",
                "SFWMD ArcGIS": "minLON,minLAT,maxLON,maxLAT (esriGeometryEnvelope)",
                "NOAA CDO extent": "minLAT,minLON,maxLAT,maxLON (latitude first)",
              },
              authentication: {
                "NOAA CO-OPS": "None required",
                "NOAA CDO":
                  "Token in HTTP header (key: 'token', NOT in URL — silently fails)",
                "USGS NWIS": "None required",
                "SFWMD ArcGIS": "None (open endpoints)",
                "SFWMD DBhydro":
                  "Bearer token (Authorization header) — PENDING",
              },
              rate_limits: {
                "NOAA CDO": "5 requests/sec, 10,000 requests/day",
                Others: "No documented limits (backoff recommended)",
              },
            },
            null,
            2
          ),
        },
      ],
    })
  );

  // 4. I&I Equation Reference
  server.resource(
    "ii-equations",
    "pumpiq://env/ii-equations",
    {
      description:
        "I&I engine equation reference showing which external data feeds into which calculation.",
      mimeType: "application/json",
    },
    async () => ({
      contents: [
        {
          uri: "pumpiq://env/ii-equations",
          mimeType: "application/json",
          text: JSON.stringify(
            {
              equations: [
                {
                  id: "Eq2",
                  name: "Groundwater Infiltration (GWI)",
                  description:
                    "Calculates infiltration driven by groundwater table height using Darcy's law",
                  data_sources: ["USGS NWIS (param 62610)"],
                  tools: ["usgs_get_realtime_gw_levels", "usgs_get_active_wells"],
                },
                {
                  id: "Eq3",
                  name: "Tidal Infiltration (TI)",
                  description:
                    "Models infiltration from tidal influence on coastal groundwater",
                  data_sources: [
                    "NOAA CO-OPS (water_level, predictions)",
                    "USGS NWIS (param 62610)",
                  ],
                  tools: [
                    "noaa_get_water_levels",
                    "noaa_get_tidal_predictions",
                    "noaa_compute_high_low_tides",
                    "usgs_get_realtime_gw_levels",
                  ],
                },
                {
                  id: "Eq4",
                  name: "Rainfall-Driven I&I (RDII)",
                  description:
                    "Storm response model correlating rainfall with excess flow",
                  data_sources: ["NOAA CDO (GHCND daily, PRCP)"],
                  tools: ["noaa_get_daily_rainfall"],
                  known_gaps:
                    "15-min precipitation (PRECIP_15) unavailable since 2014 in Miami-Dade",
                },
                {
                  id: "Eq5",
                  name: "Saltwater Intrusion (SWI)",
                  description:
                    "Detects saltwater intrusion into Biscayne Aquifer via conductivity monitoring",
                  data_sources: [
                    "USGS NWIS (param 00095 — specific conductance)",
                    "SFWMD (regional well data)",
                  ],
                  tools: [
                    "usgs_get_conductivity",
                    "sfwmd_get_wells_by_county",
                    "sfwmd_get_wells_open_data",
                  ],
                },
              ],
            },
            null,
            2
          ),
        },
      ],
    })
  );
}
