/**
 * PumpIQ MCP Server — NOAA CO-OPS Tools
 *
 * Tools for NOAA Center for Operational Oceanographic Products and Services.
 * Station 8723214 = Virginia Key, Biscayne Bay, FL.
 * Used for Equation 3: Tidal Infiltration in I&I engine.
 *
 * No authentication required.
 */

import { z } from "zod";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import {
  NOAA_COOPS_BASE,
  NOAA_COOPS_METADATA,
  DEFAULTS,
} from "../lib/config.js";
import { toCoopsDate, daysAgoISO, todayISO } from "../lib/dates.js";
import { fetchJson, ApiError } from "../lib/http.js";
import { acquireToken } from "../lib/rate-limiter.js";
import type {
  NoaaCoopsResponse,
  NoaaCoopsReading,
  HighLowTide,
} from "../lib/types.js";

const SOURCE = "NOAA CO-OPS";

// ─── Shared query builder ────────────────────────────────────────────

function coopsUrl(params: Record<string, string>): string {
  const qs = new URLSearchParams({
    format: "json",
    time_zone: DEFAULTS.timezone,
    units: DEFAULTS.units,
    application: DEFAULTS.application,
    ...params,
  });
  return `${NOAA_COOPS_BASE}?${qs.toString()}`;
}

// ─── Tool registrations ──────────────────────────────────────────────

export function registerNoaaCoopsTools(server: McpServer): void {
  // 1. Get water levels (6-min readings)
  server.tool(
    "noaa_get_water_levels",
    "Get 6-minute water level readings from a NOAA tidal station. Returns real-time or historical data. Default station is Virginia Key (8723214), Biscayne Bay, FL.",
    {
      station: z
        .string()
        .default(DEFAULTS.noaa_station)
        .describe("NOAA station ID (default: 8723214 Virginia Key)"),
      start_date: z
        .string()
        .optional()
        .describe("Start date in YYYY-MM-DD format. If omitted, uses range."),
      end_date: z
        .string()
        .optional()
        .describe("End date in YYYY-MM-DD format."),
      range: z
        .number()
        .default(24)
        .describe("Hours of data to retrieve (default: 24). Ignored if start/end provided."),
      datum: z
        .string()
        .default(DEFAULTS.datum)
        .describe("Tidal datum reference (default: MLLW)"),
    },
    async ({ station, start_date, end_date, range, datum }) => {
      await acquireToken("noaa-coops");

      const params: Record<string, string> = {
        station,
        product: "water_level",
        datum,
      };

      if (start_date && end_date) {
        params.begin_date = toCoopsDate(start_date);
        params.end_date = toCoopsDate(end_date);
      } else {
        params.range = String(range);
      }

      try {
        const data = await fetchJson<NoaaCoopsResponse>(coopsUrl(params), {
          sourceName: SOURCE,
        });

        const readings = data.data ?? [];
        const summary = readings.length > 0
          ? `Retrieved ${readings.length} water level readings from station ${station}.\n` +
            `Time range: ${readings[0].t} to ${readings[readings.length - 1].t}\n` +
            `Value range: ${Math.min(...readings.map(r => parseFloat(r.v))).toFixed(3)} to ` +
            `${Math.max(...readings.map(r => parseFloat(r.v))).toFixed(3)} ft (${datum})`
          : `No water level data available for station ${station} in the requested time range.`;

        return {
          content: [
            { type: "text", text: summary },
            { type: "text", text: JSON.stringify(readings.slice(0, 50), null, 2) },
            ...(readings.length > 50
              ? [{ type: "text" as const, text: `... and ${readings.length - 50} more readings (truncated for display).` }]
              : []),
          ],
        };
      } catch (err) {
        const msg = err instanceof ApiError ? err.toToolResult() : String(err);
        return { content: [{ type: "text", text: msg }], isError: true };
      }
    }
  );

  // 2. Get tidal predictions
  server.tool(
    "noaa_get_tidal_predictions",
    "Get predicted tidal levels based on harmonic analysis. Used for predicted vs actual comparison in anomaly detection.",
    {
      station: z.string().default(DEFAULTS.noaa_station),
      start_date: z.string().describe("Start date YYYY-MM-DD"),
      end_date: z.string().describe("End date YYYY-MM-DD"),
      datum: z.string().default(DEFAULTS.datum),
    },
    async ({ station, start_date, end_date, datum }) => {
      await acquireToken("noaa-coops");

      const url = coopsUrl({
        station,
        product: "predictions",
        datum,
        begin_date: toCoopsDate(start_date),
        end_date: toCoopsDate(end_date),
      });

      try {
        const data = await fetchJson<NoaaCoopsResponse>(url, {
          sourceName: SOURCE,
        });

        const predictions = data.predictions ?? [];
        const summary = predictions.length > 0
          ? `Retrieved ${predictions.length} tidal predictions for station ${station}.\n` +
            `Time range: ${predictions[0].t} to ${predictions[predictions.length - 1].t}\n` +
            `Value range: ${Math.min(...predictions.map(r => parseFloat(r.v))).toFixed(3)} to ` +
            `${Math.max(...predictions.map(r => parseFloat(r.v))).toFixed(3)} ft (${datum})`
          : `No tidal predictions available for station ${station} in the requested range.`;

        return {
          content: [
            { type: "text", text: summary },
            { type: "text", text: JSON.stringify(predictions.slice(0, 50), null, 2) },
          ],
        };
      } catch (err) {
        const msg = err instanceof ApiError ? err.toToolResult() : String(err);
        return { content: [{ type: "text", text: msg }], isError: true };
      }
    }
  );

  // 3. Get air pressure
  server.tool(
    "noaa_get_air_pressure",
    "Get 6-minute barometric pressure readings. Supplementary data for storm event correlation.",
    {
      station: z.string().default(DEFAULTS.noaa_station),
      range: z.number().default(24).describe("Hours of data (default: 24)"),
    },
    async ({ station, range }) => {
      await acquireToken("noaa-coops");

      const url = coopsUrl({
        station,
        product: "air_pressure",
        range: String(range),
      });

      try {
        const data = await fetchJson<NoaaCoopsResponse>(url, {
          sourceName: SOURCE,
        });

        const readings = data.data ?? [];
        const summary = readings.length > 0
          ? `Retrieved ${readings.length} air pressure readings from station ${station}.\n` +
            `Note: Air pressure quality flags use 3 fields (e.g., "0,0,0"), not 4 like water levels.`
          : `No air pressure data available for station ${station}.`;

        return {
          content: [
            { type: "text", text: summary },
            { type: "text", text: JSON.stringify(readings.slice(0, 50), null, 2) },
          ],
        };
      } catch (err) {
        const msg = err instanceof ApiError ? err.toToolResult() : String(err);
        return { content: [{ type: "text", text: msg }], isError: true };
      }
    }
  );

  // 4. Get station metadata
  server.tool(
    "noaa_get_station_metadata",
    "Get station details: coordinates, available products, and operational status. Always check this BEFORE querying a new station.",
    {
      station: z.string().default(DEFAULTS.noaa_station),
    },
    async ({ station }) => {
      await acquireToken("noaa-coops");

      const url = `${NOAA_COOPS_METADATA}/${station}.json?expand=details`;

      try {
        const data = await fetchJson<Record<string, unknown>>(url, {
          sourceName: SOURCE,
        });

        return {
          content: [
            {
              type: "text",
              text: `Station ${station} metadata:\n${JSON.stringify(data, null, 2)}`,
            },
          ],
        };
      } catch (err) {
        const msg = err instanceof ApiError ? err.toToolResult() : String(err);
        return { content: [{ type: "text", text: msg }], isError: true };
      }
    }
  );

  // 5. Compute high/low tides (derived from 6-min data)
  server.tool(
    "noaa_compute_high_low_tides",
    "Compute high and low tide events from 6-minute water level data. NOTE: Station 8723214 does NOT support the native high_low product, so this tool derives them locally from raw readings.",
    {
      station: z.string().default(DEFAULTS.noaa_station),
      start_date: z
        .string()
        .default(daysAgoISO(2))
        .describe("Start date YYYY-MM-DD (default: 2 days ago)"),
      end_date: z
        .string()
        .default(todayISO())
        .describe("End date YYYY-MM-DD (default: today)"),
      datum: z.string().default(DEFAULTS.datum),
    },
    async ({ station, start_date, end_date, datum }) => {
      await acquireToken("noaa-coops");

      const url = coopsUrl({
        station,
        product: "water_level",
        datum,
        begin_date: toCoopsDate(start_date),
        end_date: toCoopsDate(end_date),
      });

      try {
        const data = await fetchJson<NoaaCoopsResponse>(url, {
          sourceName: SOURCE,
        });

        const readings = data.data ?? [];
        if (readings.length < 3) {
          return {
            content: [
              {
                type: "text",
                text: "Insufficient data to compute high/low tides (need at least 3 readings).",
              },
            ],
          };
        }

        // Simple peak/trough detection with smoothing window
        const values = readings.map((r) => ({
          t: r.t,
          v: parseFloat(r.v),
        }));

        const events: HighLowTide[] = [];
        for (let i = 1; i < values.length - 1; i++) {
          const prev = values[i - 1].v;
          const curr = values[i].v;
          const next = values[i + 1].v;

          if (curr > prev && curr > next) {
            events.push({ time: values[i].t, value: curr, type: "high" });
          } else if (curr < prev && curr < next) {
            events.push({ time: values[i].t, value: curr, type: "low" });
          }
        }

        const summary =
          `Computed ${events.length} tidal events (` +
          `${events.filter((e) => e.type === "high").length} highs, ` +
          `${events.filter((e) => e.type === "low").length} lows) ` +
          `from ${readings.length} raw readings.\n` +
          `Station: ${station} | Datum: ${datum} | Period: ${start_date} to ${end_date}`;

        return {
          content: [
            { type: "text", text: summary },
            { type: "text", text: JSON.stringify(events, null, 2) },
          ],
        };
      } catch (err) {
        const msg = err instanceof ApiError ? err.toToolResult() : String(err);
        return { content: [{ type: "text", text: msg }], isError: true };
      }
    }
  );
}
