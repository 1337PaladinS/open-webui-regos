/**
 * PumpIQ MCP Server — USGS NWIS Tools
 *
 * Tools for USGS National Water Information System.
 * County FIPS 12086 = Miami-Dade County, FL.
 * Parameter 62610 = groundwater level above NGVD 1929 (feet).
 * Parameter 00095 = specific conductance (µS/cm) — saltwater intrusion.
 *
 * Used for Equations 2 (GWI), 3 (TI), and 5 (SWI) in I&I engine.
 * No authentication required.
 *
 * CRITICAL FIXES (from Postman V2):
 *   - countyCd must be used ALONE (never combine with stateCd → error 400)
 *   - parameterCd 62610 (128 wells), NOT 72019 (0 wells in Miami-Dade)
 *   - bBox format: minLON,minLAT,maxLON,maxLAT (longitude FIRST!)
 */

import { z } from "zod";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { USGS_NWIS_IV, USGS_OGC_BASE, DEFAULTS } from "../lib/config.js";
import { validatePeriod } from "../lib/dates.js";
import { fetchJson, ApiError } from "../lib/http.js";
import { acquireToken } from "../lib/rate-limiter.js";
import type { UsgsNwisResponse } from "../lib/types.js";

const SOURCE = "USGS NWIS";

export function registerUsgsNwisTools(server: McpServer): void {
  // 1. Get active groundwater wells in a county
  server.tool(
    "usgs_get_active_wells",
    "List active groundwater monitoring wells in a county. Default: Miami-Dade (FIPS 12086) with parameter 62610 (GW level above NGVD 1929, 128 wells). IMPORTANT: Do NOT combine countyCd with stateCd — it causes HTTP 400.",
    {
      county_fips: z
        .string()
        .default(DEFAULTS.miami_dade_fips)
        .describe("County FIPS code (default: 12086 Miami-Dade)"),
      parameter: z
        .string()
        .default(DEFAULTS.usgs_gw_param)
        .describe("USGS parameter code (default: 62610 GW level)"),
      period: z
        .string()
        .default("P1D")
        .describe("ISO 8601 period (default: P1D = last 24 hours)"),
    },
    async ({ county_fips, parameter, period }) => {
      await acquireToken("usgs");

      const validPeriod = validatePeriod(period);
      const params = new URLSearchParams({
        countyCd: county_fips,
        parameterCd: parameter,
        siteStatus: "active",
        period: validPeriod,
        format: "json",
      });

      try {
        const data = await fetchJson<UsgsNwisResponse>(
          `${USGS_NWIS_IV}?${params}`,
          { sourceName: SOURCE, timeoutMs: 45_000 }
        );

        const sites = data.value?.timeSeries ?? [];
        const summary =
          `Found ${sites.length} active groundwater wells in county ${county_fips} ` +
          `with parameter ${parameter} (period: ${validPeriod}).\n\n` +
          sites
            .slice(0, 20)
            .map((s) => {
              const loc = s.sourceInfo.geoLocation.geogLocation;
              const lastVal = s.values?.[0]?.value?.slice(-1)?.[0];
              return (
                `• ${s.sourceInfo.siteName} (${s.sourceInfo.siteCode[0].value})\n` +
                `  Lat: ${loc.latitude}, Lon: ${loc.longitude}\n` +
                (lastVal
                  ? `  Latest: ${lastVal.value} ${s.variable.unit.unitCode} at ${lastVal.dateTime}`
                  : `  No recent readings`)
              );
            })
            .join("\n\n") +
          (sites.length > 20
            ? `\n\n... and ${sites.length - 20} more wells.`
            : "");

        return {
          content: [{ type: "text", text: summary }],
        };
      } catch (err) {
        const msg = err instanceof ApiError ? err.toToolResult() : String(err);
        return { content: [{ type: "text", text: msg }], isError: true };
      }
    }
  );

  // 2. Get real-time groundwater levels
  server.tool(
    "usgs_get_realtime_gw_levels",
    "Get real-time 15-minute groundwater depth readings for a county. Primary feed — groundwater height drives infiltration calculations via Darcy's law.",
    {
      county_fips: z.string().default(DEFAULTS.miami_dade_fips),
      period: z
        .string()
        .default("P7D")
        .describe("ISO 8601 period (default: P7D = last 7 days)"),
    },
    async ({ county_fips, period }) => {
      await acquireToken("usgs");

      const validPeriod = validatePeriod(period);
      const params = new URLSearchParams({
        countyCd: county_fips,
        parameterCd: DEFAULTS.usgs_gw_param,
        siteStatus: "active",
        period: validPeriod,
        format: "json",
      });

      try {
        const data = await fetchJson<UsgsNwisResponse>(
          `${USGS_NWIS_IV}?${params}`,
          { sourceName: SOURCE, timeoutMs: 60_000 }
        );

        const series = data.value?.timeSeries ?? [];
        const totalReadings = series.reduce(
          (sum, s) => sum + (s.values?.[0]?.value?.length ?? 0),
          0
        );

        const summary =
          `Retrieved groundwater level data from ${series.length} wells ` +
          `(${totalReadings} total readings) in county ${county_fips}.\n` +
          `Parameter: 62610 (GW level above NGVD 1929, feet)\n` +
          `Period: ${validPeriod}`;

        // Return summary + first 3 well details for context
        const details = series.slice(0, 3).map((s) => ({
          site: s.sourceInfo.siteName,
          siteCode: s.sourceInfo.siteCode[0].value,
          lat: s.sourceInfo.geoLocation.geogLocation.latitude,
          lon: s.sourceInfo.geoLocation.geogLocation.longitude,
          parameter: s.variable.variableName,
          unit: s.variable.unit.unitCode,
          readingCount: s.values?.[0]?.value?.length ?? 0,
          latestReading: s.values?.[0]?.value?.slice(-1)?.[0] ?? null,
        }));

        return {
          content: [
            { type: "text", text: summary },
            { type: "text", text: JSON.stringify(details, null, 2) },
          ],
        };
      } catch (err) {
        const msg = err instanceof ApiError ? err.toToolResult() : String(err);
        return { content: [{ type: "text", text: msg }], isError: true };
      }
    }
  );

  // 3. Get conductivity — saltwater intrusion
  server.tool(
    "usgs_get_conductivity",
    "Get specific conductance (µS/cm) readings for detecting saltwater intrusion into the Biscayne Aquifer. Expect ~50 active monitoring sites in Miami-Dade.",
    {
      county_fips: z.string().default(DEFAULTS.miami_dade_fips),
      period: z.string().default("P7D"),
    },
    async ({ county_fips, period }) => {
      await acquireToken("usgs");

      const validPeriod = validatePeriod(period);
      const params = new URLSearchParams({
        countyCd: county_fips,
        parameterCd: DEFAULTS.usgs_conductivity_param,
        siteStatus: "active",
        period: validPeriod,
        format: "json",
      });

      try {
        const data = await fetchJson<UsgsNwisResponse>(
          `${USGS_NWIS_IV}?${params}`,
          { sourceName: SOURCE, timeoutMs: 60_000 }
        );

        const series = data.value?.timeSeries ?? [];
        const summary =
          `Retrieved conductivity data from ${series.length} monitoring sites ` +
          `in county ${county_fips} (period: ${validPeriod}).\n` +
          `Parameter: 00095 (Specific conductance, µS/cm)\n` +
          `Use case: Saltwater intrusion detection in Biscayne Aquifer (I&I Equation 5: SWI)`;

        const details = series.slice(0, 5).map((s) => ({
          site: s.sourceInfo.siteName,
          siteCode: s.sourceInfo.siteCode[0].value,
          lat: s.sourceInfo.geoLocation.geogLocation.latitude,
          lon: s.sourceInfo.geoLocation.geogLocation.longitude,
          readingCount: s.values?.[0]?.value?.length ?? 0,
          latestReading: s.values?.[0]?.value?.slice(-1)?.[0] ?? null,
        }));

        return {
          content: [
            { type: "text", text: summary },
            { type: "text", text: JSON.stringify(details, null, 2) },
          ],
        };
      } catch (err) {
        const msg = err instanceof ApiError ? err.toToolResult() : String(err);
        return { content: [{ type: "text", text: msg }], isError: true };
      }
    }
  );

  // 4. Get wells by bounding box
  server.tool(
    "usgs_get_wells_by_bbox",
    "Spatial search for groundwater wells within a bounding box. IMPORTANT: Coordinate order is longitude,latitude (opposite of most mapping tools).",
    {
      min_lng: z.number().describe("Minimum longitude (west)"),
      min_lat: z.number().describe("Minimum latitude (south)"),
      max_lng: z.number().describe("Maximum longitude (east)"),
      max_lat: z.number().describe("Maximum latitude (north)"),
      parameter: z.string().default(DEFAULTS.usgs_gw_param),
      period: z.string().default("P7D"),
    },
    async ({ min_lng, min_lat, max_lng, max_lat, parameter, period }) => {
      await acquireToken("usgs");

      const validPeriod = validatePeriod(period);
      // USGS bBox format: minLON,minLAT,maxLON,maxLAT
      const bbox = `${min_lng},${min_lat},${max_lng},${max_lat}`;
      const params = new URLSearchParams({
        bBox: bbox,
        parameterCd: parameter,
        period: validPeriod,
        format: "json",
      });

      try {
        const data = await fetchJson<UsgsNwisResponse>(
          `${USGS_NWIS_IV}?${params}`,
          { sourceName: SOURCE, timeoutMs: 45_000 }
        );

        const series = data.value?.timeSeries ?? [];
        const summary =
          `Found ${series.length} wells in bounding box [${bbox}]\n` +
          `Parameter: ${parameter} | Period: ${validPeriod}`;

        return {
          content: [
            { type: "text", text: summary },
            {
              type: "text",
              text: JSON.stringify(
                series.slice(0, 10).map((s) => ({
                  site: s.sourceInfo.siteName,
                  code: s.sourceInfo.siteCode[0].value,
                  lat: s.sourceInfo.geoLocation.geogLocation.latitude,
                  lon: s.sourceInfo.geoLocation.geogLocation.longitude,
                  readings: s.values?.[0]?.value?.length ?? 0,
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

  // 5. List USGS OGC API collections (future-proof)
  server.tool(
    "usgs_list_ogc_collections",
    "Browse modern USGS OGC API collections. This is the future replacement for legacy NWIS endpoints (migration target: 2027). Includes 'latest-continuous' (real-time) and 'field-measurements' (manual readings).",
    {},
    async () => {
      await acquireToken("usgs");

      try {
        const data = await fetchJson<{ collections: unknown[] }>(
          `${USGS_OGC_BASE}/collections?f=json`,
          { sourceName: SOURCE }
        );

        return {
          content: [
            {
              type: "text",
              text: `USGS OGC API Collections:\n${JSON.stringify(data.collections ?? data, null, 2)}`,
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
