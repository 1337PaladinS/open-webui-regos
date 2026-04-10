/**
 * PumpIQ MCP Server — SFWMD DBHYDRO Tools
 *
 * Tools for South Florida Water Management District.
 * ArcGIS endpoints are open (no login required).
 * Full REST API access requires credentials (pending).
 *
 * Supplements USGS with regional wells, canal stages, and water quality.
 *
 * NOTE: ArcGIS FeatureServer may time out from cloud environments.
 * Open Data Hub is used as automatic fallback.
 */

import { z } from "zod";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import {
  SFWMD_ARCGIS,
  SFWMD_OPEN_DATA,
  getSfwmdApiKey,
} from "../lib/config.js";
import { toCdoDate } from "../lib/dates.js";
import { fetchJson, ApiError } from "../lib/http.js";
import { acquireToken } from "../lib/rate-limiter.js";
import type { SfwmdFeatureResponse } from "../lib/types.js";

const SOURCE = "SFWMD";

export function registerSfwmdTools(server: McpServer): void {
  // 1. Get wells by county (ArcGIS FeatureServer)
  server.tool(
    "sfwmd_get_wells_by_county",
    "Query SFWMD well locations from ArcGIS FeatureServer. Open, no login required. May time out from cloud environments — use sfwmd_get_wells_open_data as fallback.",
    {
      county: z
        .string()
        .default("MIAMI-DADE")
        .describe("County name in uppercase (default: MIAMI-DADE)"),
      limit: z
        .number()
        .default(50)
        .describe("Max results (default: 50, max: 2000)"),
    },
    async ({ county, limit }) => {
      await acquireToken("sfwmd");

      const params = new URLSearchParams({
        where: `COUNTY='${county}'`,
        outFields: "*",
        f: "json",
        resultRecordCount: String(Math.min(limit, 2000)),
      });

      try {
        const data = await fetchJson<SfwmdFeatureResponse>(
          `${SFWMD_ARCGIS}/0/query?${params}`,
          { sourceName: SOURCE, timeoutMs: 20_000 }
        );

        const features = data.features ?? [];
        const summary = features.length > 0
          ? `Retrieved ${features.length} well records from SFWMD ArcGIS for ${county} county.`
          : `No wells found for ${county}. The ArcGIS server may be unreachable — try sfwmd_get_wells_open_data instead.`;

        return {
          content: [
            { type: "text", text: summary },
            {
              type: "text",
              text: JSON.stringify(
                features.slice(0, 10).map((f) => ({
                  x: f.geometry.x,
                  y: f.geometry.y,
                  ...f.attributes,
                })),
                null,
                2
              ),
            },
          ],
        };
      } catch (err) {
        // Auto-suggest fallback on timeout
        const isTimeout =
          err instanceof Error &&
          (err.message.includes("abort") || err.message.includes("timeout"));
        const msg = err instanceof ApiError ? err.toToolResult() : String(err);
        const fallbackHint = isTimeout
          ? "\n\nThe ArcGIS server timed out (common from cloud environments). Use sfwmd_get_wells_open_data as a reliable alternative."
          : "";

        return {
          content: [{ type: "text", text: msg + fallbackHint }],
          isError: true,
        };
      }
    }
  );

  // 2. Get wells by bounding box (ArcGIS)
  server.tool(
    "sfwmd_get_wells_by_bbox",
    "Spatial query for SFWMD wells within a bounding box using ArcGIS envelope geometry. May time out from cloud — use Open Data Hub fallback if needed.",
    {
      min_lng: z.number().describe("Minimum longitude (west)"),
      min_lat: z.number().describe("Minimum latitude (south)"),
      max_lng: z.number().describe("Maximum longitude (east)"),
      max_lat: z.number().describe("Maximum latitude (north)"),
    },
    async ({ min_lng, min_lat, max_lng, max_lat }) => {
      await acquireToken("sfwmd");

      const geometry = `${min_lng},${min_lat},${max_lng},${max_lat}`;
      const params = new URLSearchParams({
        geometry,
        geometryType: "esriGeometryEnvelope",
        spatialRel: "esriSpatialRelIntersects",
        outFields: "*",
        f: "json",
      });

      try {
        const data = await fetchJson<SfwmdFeatureResponse>(
          `${SFWMD_ARCGIS}/0/query?${params}`,
          { sourceName: SOURCE, timeoutMs: 20_000 }
        );

        const features = data.features ?? [];
        return {
          content: [
            {
              type: "text",
              text: `Found ${features.length} wells in bounding box [${geometry}].`,
            },
            {
              type: "text",
              text: JSON.stringify(
                features.slice(0, 10).map((f) => ({
                  x: f.geometry.x,
                  y: f.geometry.y,
                  ...f.attributes,
                })),
                null,
                2
              ),
            },
          ],
        };
      } catch (err) {
        const msg = err instanceof ApiError ? err.toToolResult() : String(err);
        return { content: [{ type: "text", text: msg }], isError: true };
      }
    }
  );

  // 3. Get wells from Open Data Hub (reliable fallback)
  server.tool(
    "sfwmd_get_wells_open_data",
    "Query SFWMD wells via Open Data Hub (accessible from anywhere). Use this as PRIMARY well discovery when the main ArcGIS FeatureServer times out or is unreachable.",
    {
      county: z.string().default("MIAMI-DADE"),
      limit: z.number().default(25),
    },
    async ({ county, limit }) => {
      await acquireToken("sfwmd");

      const params = new URLSearchParams({
        where: `COUNTY='${county}'`,
        outFields: "*",
        f: "json",
        resultRecordCount: String(limit),
      });

      try {
        const data = await fetchJson<SfwmdFeatureResponse>(
          `${SFWMD_OPEN_DATA}?${params}`,
          { sourceName: `${SOURCE} Open Data Hub` }
        );

        const features = data.features ?? [];
        return {
          content: [
            {
              type: "text",
              text: `Retrieved ${features.length} well records from SFWMD Open Data Hub for ${county}.`,
            },
            {
              type: "text",
              text: JSON.stringify(
                features.slice(0, 10).map((f) => ({
                  x: f.geometry.x,
                  y: f.geometry.y,
                  ...f.attributes,
                })),
                null,
                2
              ),
            },
          ],
        };
      } catch (err) {
        const msg = err instanceof ApiError ? err.toToolResult() : String(err);
        return { content: [{ type: "text", text: msg }], isError: true };
      }
    }
  );

  // 4. Get hydrology time series (PLACEHOLDER — awaiting credentials)
  server.tool(
    "sfwmd_get_hydrology_timeseries",
    "PLACEHOLDER: Get hydrology time series data from SFWMD DBhydro Insights API. This endpoint requires credentials that are currently pending (email DataRequests@sfwmd.gov). Will return an informational message until credentials are configured.",
    {
      station: z.string().describe("SFWMD station identifier"),
      parameter: z
        .string()
        .default("GW_LEVEL")
        .describe("Parameter name (e.g. GW_LEVEL)"),
      start_date: z.string().describe("Start date YYYY-MM-DD"),
      end_date: z.string().describe("End date YYYY-MM-DD"),
    },
    async ({ station, parameter, start_date, end_date }) => {
      const apiKey = getSfwmdApiKey();

      if (!apiKey) {
        return {
          content: [
            {
              type: "text",
              text:
                "SFWMD DBhydro Insights API credentials are NOT YET CONFIGURED.\n\n" +
                "Status: PENDING — email DataRequests@sfwmd.gov to request API access.\n\n" +
                "Once you receive credentials, set the SFWMD_API_KEY environment variable.\n\n" +
                "In the meantime, use these alternatives:\n" +
                "• sfwmd_get_wells_by_county — well locations (open, no login)\n" +
                "• sfwmd_get_wells_open_data — well locations via Open Data Hub\n" +
                "• usgs_get_realtime_gw_levels — USGS groundwater data (open, 128 wells in Miami-Dade)",
            },
          ],
        };
      }

      // Future implementation once credentials are available
      const url =
        `https://apps.sfwmd.gov/dbhydroInsights/api/v1/data` +
        `?station=${encodeURIComponent(station)}` +
        `&parameter=${encodeURIComponent(parameter)}` +
        `&startDate=${toCdoDate(start_date)}` +
        `&endDate=${toCdoDate(end_date)}`;

      try {
        const data = await fetchJson<unknown>(url, {
          headers: { Authorization: `Bearer ${apiKey}` },
          sourceName: `${SOURCE} DBhydro`,
        });

        return {
          content: [
            {
              type: "text",
              text: `SFWMD hydrology data:\n${JSON.stringify(data, null, 2)}`,
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
