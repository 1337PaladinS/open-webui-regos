/**
 * PumpIQ MCP Server — I&I Data Readiness Check
 *
 * Cross-cutting utility tool that validates data availability across
 * all 4 external sources for a given location and date range.
 * Returns a readiness matrix for the I&I engine equations.
 */

import { z } from "zod";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import {
  NOAA_COOPS_BASE,
  NOAA_CDO_BASE,
  USGS_NWIS_IV,
  SFWMD_OPEN_DATA,
  DEFAULTS,
  getNoaaCdoToken,
} from "../lib/config.js";
import { toCoopsDate, toCdoDate } from "../lib/dates.js";
import { fetchJson } from "../lib/http.js";
import type { IIReadinessReport, DataSourceStatus } from "../lib/types.js";

export function registerIIReadinessTools(server: McpServer): void {
  server.tool(
    "pumpiq_ii_data_check",
    "Validate data availability across all 4 environmental sources (NOAA tides, NOAA rainfall, USGS groundwater, SFWMD wells) for a given location and date range. Returns a readiness matrix showing which I&I equations can be computed.",
    {
      start_date: z.string().describe("Start date YYYY-MM-DD"),
      end_date: z.string().describe("End date YYYY-MM-DD"),
      station_noaa: z.string().default(DEFAULTS.noaa_station),
      station_ghcnd: z.string().default(DEFAULTS.noaa_ghcnd_station),
      county_fips: z.string().default(DEFAULTS.miami_dade_fips),
    },
    async ({ start_date, end_date, station_noaa, station_ghcnd, county_fips }) => {
      const sources: DataSourceStatus[] = [];

      // 1. Check NOAA CO-OPS (tidal data)
      try {
        const tidalParams = new URLSearchParams({
          station: station_noaa,
          product: "water_level",
          datum: DEFAULTS.datum,
          begin_date: toCoopsDate(start_date),
          end_date: toCoopsDate(end_date),
          time_zone: DEFAULTS.timezone,
          units: DEFAULTS.units,
          format: "json",
          application: DEFAULTS.application,
        });
        const tidalData = await fetchJson<{ data?: unknown[] }>(
          `${NOAA_COOPS_BASE}?${tidalParams}`,
          { sourceName: "NOAA CO-OPS", timeoutMs: 15_000, maxRetries: 1 }
        );
        const count = tidalData.data?.length ?? 0;
        sources.push({
          source: "NOAA CO-OPS (Tidal)",
          available: count > 0,
          record_count: count,
          date_range: { start: start_date, end: end_date },
        });
      } catch {
        sources.push({
          source: "NOAA CO-OPS (Tidal)",
          available: false,
          record_count: 0,
          warnings: ["API unreachable or returned error"],
        });
      }

      // 2. Check NOAA CDO (rainfall)
      try {
        const token = getNoaaCdoToken();
        const rainParams = new URLSearchParams({
          datasetid: "GHCND",
          stationid: station_ghcnd,
          datatypeid: "PRCP",
          startdate: toCdoDate(start_date),
          enddate: toCdoDate(end_date),
          units: "standard",
          limit: "5",
        });
        const rainData = await fetchJson<{ results?: unknown[] }>(
          `${NOAA_CDO_BASE}/data?${rainParams}`,
          {
            headers: { token },
            sourceName: "NOAA CDO",
            timeoutMs: 15_000,
            maxRetries: 1,
          }
        );
        const count = rainData.results?.length ?? 0;
        sources.push({
          source: "NOAA CDO (Rainfall/GHCND)",
          available: count > 0,
          record_count: count,
          date_range: { start: start_date, end: end_date },
          warnings:
            count === 0
              ? [
                  "GHCND daily data may not be available for very recent dates. " +
                    "PRECIP_15 (15-min) is unavailable for Miami-Dade since 2014.",
                ]
              : undefined,
        });
      } catch {
        sources.push({
          source: "NOAA CDO (Rainfall/GHCND)",
          available: false,
          record_count: 0,
          warnings: [
            "API unreachable or NOAA_CDO_TOKEN not set. Register at https://www.ncdc.noaa.gov/cdo-web/token",
          ],
        });
      }

      // 3. Check USGS (groundwater)
      try {
        const gwParams = new URLSearchParams({
          countyCd: county_fips,
          parameterCd: DEFAULTS.usgs_gw_param,
          siteStatus: "active",
          period: "P1D",
          format: "json",
        });
        const gwData = await fetchJson<{ value?: { timeSeries?: unknown[] } }>(
          `${USGS_NWIS_IV}?${gwParams}`,
          { sourceName: "USGS NWIS", timeoutMs: 20_000, maxRetries: 1 }
        );
        const count = gwData.value?.timeSeries?.length ?? 0;
        sources.push({
          source: "USGS NWIS (Groundwater)",
          available: count > 0,
          record_count: count,
        });
      } catch {
        sources.push({
          source: "USGS NWIS (Groundwater)",
          available: false,
          record_count: 0,
          warnings: ["API unreachable"],
        });
      }

      // 4. Check SFWMD (regional wells)
      try {
        const sfwmdParams = new URLSearchParams({
          where: "COUNTY='MIAMI-DADE'",
          outFields: "*",
          f: "json",
          resultRecordCount: "5",
        });
        const sfwmdData = await fetchJson<{ features?: unknown[] }>(
          `${SFWMD_OPEN_DATA}?${sfwmdParams}`,
          { sourceName: "SFWMD", timeoutMs: 15_000, maxRetries: 1 }
        );
        const count = sfwmdData.features?.length ?? 0;
        sources.push({
          source: "SFWMD (Regional Wells)",
          available: count > 0,
          record_count: count,
        });
      } catch {
        sources.push({
          source: "SFWMD (Regional Wells)",
          available: false,
          record_count: 0,
          warnings: ["Open Data Hub unreachable"],
        });
      }

      // Build readiness report
      const tidalOk = sources[0].available;
      const rainOk = sources[1].available;
      const gwOk = sources[2].available;
      const sfwmdOk = sources[3].available;

      const equations = {
        eq2_gwi: gwOk,
        eq3_ti: tidalOk && gwOk,
        eq4_rdii: rainOk,
        eq5_swi: gwOk, // conductivity check could be added
      };

      const readyCount = Object.values(equations).filter(Boolean).length;
      const overall: IIReadinessReport["overall_readiness"] =
        readyCount === 4 ? "full" : readyCount >= 2 ? "partial" : "insufficient";

      const report: IIReadinessReport = {
        location: `County FIPS ${county_fips}`,
        date_range: { start: start_date, end: end_date },
        sources,
        equations_ready: equations,
        overall_readiness: overall,
      };

      const emoji = overall === "full" ? "✅" : overall === "partial" ? "⚠️" : "❌";
      const summary =
        `${emoji} I&I DATA READINESS: ${overall.toUpperCase()}\n\n` +
        `Equation 2 (Groundwater Infiltration): ${equations.eq2_gwi ? "READY" : "NOT READY"}\n` +
        `Equation 3 (Tidal Infiltration):       ${equations.eq3_ti ? "READY" : "NOT READY"}\n` +
        `Equation 4 (Rainfall-Driven I&I):      ${equations.eq4_rdii ? "READY" : "NOT READY"}\n` +
        `Equation 5 (Saltwater Intrusion):       ${equations.eq5_swi ? "READY" : "NOT READY"}\n\n` +
        `Data Sources:\n` +
        sources
          .map(
            (s) =>
              `  ${s.available ? "✅" : "❌"} ${s.source}: ${s.record_count} records` +
              (s.warnings ? ` — ${s.warnings.join("; ")}` : "")
          )
          .join("\n");

      return {
        content: [
          { type: "text", text: summary },
          { type: "text", text: JSON.stringify(report, null, 2) },
        ],
      };
    }
  );
}
