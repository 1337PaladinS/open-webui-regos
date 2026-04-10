/**
 * PumpIQ MCP Server — NOAA CDO Tools
 *
 * Tools for NOAA Climate Data Online / NCEI.
 * Used for Equation 4: Rainfall-Driven I&I (storm response model).
 *
 * Authentication: Token in HTTP header (NOT URL).
 * Rate limit: 5 requests/sec, 10,000 requests/day.
 *
 * CRITICAL DATA GAP: PRECIP_15 (15-min data) has NO recent data in
 * Miami-Dade — all stations stopped reporting 2003-2014. Primary source
 * is GHCND daily data.
 */

import { z } from "zod";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { NOAA_CDO_BASE, DEFAULTS, getNoaaCdoToken } from "../lib/config.js";
import { toCdoDate } from "../lib/dates.js";
import { fetchJson, ApiError } from "../lib/http.js";
import { acquireToken } from "../lib/rate-limiter.js";
import type { NoaaCdoResponse } from "../lib/types.js";

const SOURCE = "NOAA CDO";

function cdoHeaders(): Record<string, string> {
  return { token: getNoaaCdoToken() };
}

export function registerNoaaCdoTools(server: McpServer): void {
  // 1. Get daily rainfall (GHCND) — PRIMARY SOURCE
  server.tool(
    "noaa_get_daily_rainfall",
    "Get daily precipitation from GHCND dataset. This is the PRIMARY rainfall source for Miami-Dade (15-min data is not available for recent years). Default station: Miami Intl Airport (GHCND:USW00012839).",
    {
      station: z
        .string()
        .default(DEFAULTS.noaa_ghcnd_station)
        .describe("GHCND station ID (default: Miami Intl Airport)"),
      start_date: z.string().describe("Start date YYYY-MM-DD"),
      end_date: z.string().describe("End date YYYY-MM-DD"),
      limit: z.number().default(100).describe("Max results (default: 100, max: 1000)"),
    },
    async ({ station, start_date, end_date, limit }) => {
      await acquireToken("noaa-cdo");

      const params = new URLSearchParams({
        datasetid: "GHCND",
        stationid: station,
        datatypeid: "PRCP",
        startdate: toCdoDate(start_date),
        enddate: toCdoDate(end_date),
        units: "standard",
        limit: String(Math.min(limit, 1000)),
      });

      try {
        const data = await fetchJson<NoaaCdoResponse>(
          `${NOAA_CDO_BASE}/data?${params}`,
          { headers: cdoHeaders(), sourceName: SOURCE }
        );

        const results = data.results ?? [];
        const summary = results.length > 0
          ? `Retrieved ${results.length} daily rainfall records from ${station}.\n` +
            `Date range: ${results[0].date.slice(0, 10)} to ${results[results.length - 1].date.slice(0, 10)}\n` +
            `Total precipitation: ${results.reduce((sum, r) => sum + r.value, 0).toFixed(2)} inches`
          : `No GHCND precipitation data found for ${station} between ${start_date} and ${end_date}.\n` +
            `Verify station ID format is GHCND:XXXXXXXXXXX.`;

        return {
          content: [
            { type: "text", text: summary },
            { type: "text", text: JSON.stringify(results, null, 2) },
          ],
        };
      } catch (err) {
        const msg = err instanceof ApiError ? err.toToolResult() : String(err);
        return { content: [{ type: "text", text: msg }], isError: true };
      }
    }
  );

  // 2. Get 15-min precipitation (legacy — likely empty for recent dates)
  server.tool(
    "noaa_get_15min_precip",
    "Get 15-minute precipitation data from PRECIP_15 dataset. WARNING: This dataset has NO recent data in Miami-Dade (all stations stopped reporting 2003-2014). Use noaa_get_daily_rainfall instead for current data.",
    {
      station: z
        .string()
        .default(DEFAULTS.noaa_cdo_station)
        .describe("COOP station ID (default: Miami Intl Airport COOP:084210)"),
      start_date: z.string().describe("Start date YYYY-MM-DD"),
      end_date: z.string().describe("End date YYYY-MM-DD"),
      limit: z.number().default(1000),
    },
    async ({ station, start_date, end_date, limit }) => {
      await acquireToken("noaa-cdo");

      const params = new URLSearchParams({
        datasetid: "PRECIP_15",
        stationid: station,
        startdate: toCdoDate(start_date),
        enddate: toCdoDate(end_date),
        units: "standard",
        limit: String(Math.min(limit, 1000)),
      });

      try {
        const data = await fetchJson<NoaaCdoResponse>(
          `${NOAA_CDO_BASE}/data?${params}`,
          { headers: cdoHeaders(), sourceName: SOURCE }
        );

        const results = data.results ?? [];
        const warning =
          "⚠ DATA GAP WARNING: All PRECIP_15 stations in Miami-Dade stopped " +
          "reporting between 2003-2014. For current rainfall data, use " +
          "noaa_get_daily_rainfall (GHCND) instead.";

        const summary = results.length > 0
          ? `Retrieved ${results.length} 15-min precipitation records.`
          : `No PRECIP_15 data found (expected — see warning below).\n\n${warning}`;

        return {
          content: [
            { type: "text", text: summary },
            ...(results.length > 0
              ? [{ type: "text" as const, text: JSON.stringify(results, null, 2) }]
              : []),
            { type: "text", text: warning },
          ],
        };
      } catch (err) {
        const msg = err instanceof ApiError ? err.toToolResult() : String(err);
        return { content: [{ type: "text", text: msg }], isError: true };
      }
    }
  );

  // 3. Find rain gauges near a location
  server.tool(
    "noaa_find_rain_gauges",
    "Discover PRECIP_15 rain gauge stations within a bounding box. Note: may return empty results for narrow areas in Miami-Dade.",
    {
      min_lat: z.number().describe("Minimum latitude"),
      min_lng: z.number().describe("Minimum longitude"),
      max_lat: z.number().describe("Maximum latitude"),
      max_lng: z.number().describe("Maximum longitude"),
      limit: z.number().default(25),
    },
    async ({ min_lat, min_lng, max_lat, max_lng, limit }) => {
      await acquireToken("noaa-cdo");

      const extent = `${min_lat},${min_lng},${max_lat},${max_lng}`;
      const params = new URLSearchParams({
        datasetid: "PRECIP_15",
        extent,
        limit: String(limit),
      });

      try {
        const data = await fetchJson<NoaaCdoResponse>(
          `${NOAA_CDO_BASE}/stations?${params}`,
          { headers: cdoHeaders(), sourceName: SOURCE }
        );

        const results = data.results ?? [];
        const summary = results.length > 0
          ? `Found ${results.length} PRECIP_15 rain gauges in bounding box.`
          : `No PRECIP_15 stations found in bounding box [${extent}]. Try widening the search area.`;

        return {
          content: [
            { type: "text", text: summary },
            { type: "text", text: JSON.stringify(results, null, 2) },
          ],
        };
      } catch (err) {
        const msg = err instanceof ApiError ? err.toToolResult() : String(err);
        return { content: [{ type: "text", text: msg }], isError: true };
      }
    }
  );

  // 4. List available datasets
  server.tool(
    "noaa_list_datasets",
    "Browse all available NOAA CDO datasets. Useful for discovering alternative data sources.",
    {
      limit: z.number().default(50),
    },
    async ({ limit }) => {
      await acquireToken("noaa-cdo");

      try {
        const data = await fetchJson<NoaaCdoResponse>(
          `${NOAA_CDO_BASE}/datasets?limit=${limit}`,
          { headers: cdoHeaders(), sourceName: SOURCE }
        );

        return {
          content: [
            {
              type: "text",
              text: `Available NOAA CDO datasets:\n${JSON.stringify(data.results ?? [], null, 2)}`,
            },
          ],
        };
      } catch (err) {
        const msg = err instanceof ApiError ? err.toToolResult() : String(err);
        return { content: [{ type: "text", text: msg }], isError: true };
      }
    }
  );
}
