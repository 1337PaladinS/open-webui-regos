/**
 * PumpIQ MCP Server — Prompt Templates
 *
 * Pre-built prompt templates that guide AI assistants through
 * common PumpIQ environmental data workflows.
 */

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { DEFAULTS, } from "../lib/config.js";
import { daysAgoISO, todayISO } from "../lib/dates.js";

export function registerPrompts(server: McpServer): void {
  // 1. Tidal I&I Investigation
  server.prompt(
    "tidal_ii_investigation",
    "Investigate tidal influence on infiltration. Pulls tidal data, compares predicted vs actual levels, and identifies anomalies that may indicate infrastructure infiltration.",
    {
      station: z
        .string()
        .default(DEFAULTS.noaa_station)
        .describe("NOAA station ID"),
      days_back: z
        .string()
        .default("7")
        .describe("Number of days to analyze"),
    },
    ({ station, days_back }) => {
      const days = parseInt(days_back ?? "7", 10);
      const start = daysAgoISO(days);
      const end = todayISO();

      return {
        messages: [
          {
            role: "user",
            content: {
              type: "text",
              text: [
                `Perform a Tidal Infiltration (I&I Equation 3) investigation for NOAA station ${station} over the last ${days} days (${start} to ${end}).`,
                "",
                "Steps:",
                `1. Use noaa_get_water_levels to get actual water levels (station: ${station}, start_date: ${start}, end_date: ${end})`,
                `2. Use noaa_get_tidal_predictions to get predicted levels for the same period`,
                `3. Use noaa_compute_high_low_tides to identify peak tidal events`,
                `4. Compare predicted vs actual — flag discrepancies > 0.5 ft as potential storm surge or anomaly`,
                `5. Use noaa_get_air_pressure to check for storm correlation during any anomalies`,
                "",
                "Deliver a summary with:",
                "- Number of tidal cycles observed",
                "- Max/min actual vs predicted levels",
                "- Any anomalies with timestamps and magnitude",
                "- Correlation with barometric pressure drops (if any)",
                "- Assessment of tidal infiltration risk for the period",
              ].join("\n"),
            },
          },
        ],
      };
    }
  );

  // 2. Rainfall I&I Analysis
  server.prompt(
    "rainfall_ii_analysis",
    "Analyze rainfall patterns for I&I correlation. Pulls daily precipitation data and identifies storm events that could drive inflow/infiltration.",
    {
      start_date: z
        .string()
        .default(daysAgoISO(30))
        .describe("Start date YYYY-MM-DD"),
      end_date: z
        .string()
        .default(todayISO())
        .describe("End date YYYY-MM-DD"),
    },
    ({ start_date, end_date }) => ({
      messages: [
        {
          role: "user",
          content: {
            type: "text",
            text: [
              `Perform a Rainfall-Driven I&I (Equation 4) analysis for ${start_date} to ${end_date}.`,
              "",
              "Steps:",
              `1. Use noaa_get_daily_rainfall (GHCND) for the date range`,
              `2. Identify storm events (daily rainfall > 0.5 inches)`,
              `3. Note: 15-min data is NOT available (use noaa_get_15min_precip to confirm if needed)`,
              "",
              "Deliver a summary with:",
              "- Total rainfall for the period",
              "- Number of rain days vs dry days",
              "- Storm events (> 0.5 in) with dates and amounts",
              "- Maximum single-day rainfall",
              "- Assessment of RDII risk level (low/moderate/high)",
              "- Note the limitation of daily-only resolution for storm response modeling",
            ].join("\n"),
          },
        },
      ],
    })
  );

  // 3. Groundwater Assessment
  server.prompt(
    "groundwater_assessment",
    "Evaluate groundwater levels and saltwater intrusion risk for a county. Pulls data from USGS and SFWMD.",
    {
      county_fips: z
        .string()
        .default(DEFAULTS.miami_dade_fips)
        .describe("County FIPS code"),
      period: z
        .string()
        .default("P7D")
        .describe("USGS period (e.g. P7D)"),
    },
    ({ county_fips, period }) => ({
      messages: [
        {
          role: "user",
          content: {
            type: "text",
            text: [
              `Perform a groundwater assessment for county FIPS ${county_fips} over period ${period}.`,
              "",
              "Steps:",
              `1. Use usgs_get_active_wells to identify monitoring wells`,
              `2. Use usgs_get_realtime_gw_levels for groundwater depth data`,
              `3. Use usgs_get_conductivity for saltwater intrusion indicators`,
              `4. Use sfwmd_get_wells_open_data to supplement with regional data`,
              "",
              "Deliver a summary with:",
              "- Number of active wells reporting",
              "- Average groundwater level and trend (rising/falling/stable)",
              "- Highest and lowest recorded levels with locations",
              "- Conductivity readings indicating saltwater intrusion risk",
              "- Wells near coastline with elevated readings",
              "- Overall groundwater infiltration risk (I&I Equations 2 & 5)",
            ].join("\n"),
          },
        },
      ],
    })
  );

  // 4. Full I&I Readiness Check
  server.prompt(
    "full_ii_readiness",
    "Run a comprehensive data availability check across all environmental sources. Determines which I&I equations can currently be computed for a given date range.",
    {
      start_date: z
        .string()
        .default(daysAgoISO(7))
        .describe("Start date YYYY-MM-DD"),
      end_date: z
        .string()
        .default(todayISO())
        .describe("End date YYYY-MM-DD"),
    },
    ({ start_date, end_date }) => ({
      messages: [
        {
          role: "user",
          content: {
            type: "text",
            text: [
              `Run a full I&I data readiness check for ${start_date} to ${end_date}.`,
              "",
              "Steps:",
              `1. Use pumpiq_ii_data_check to validate all 4 data sources`,
              `2. For any source marked as unavailable, explain why and suggest alternatives`,
              `3. Reference the ii-equations resource to map sources to equations`,
              "",
              "Deliver:",
              "- A clear READY / PARTIAL / NOT READY verdict",
              "- Status of each I&I equation (Eq2-GWI, Eq3-TI, Eq4-RDII, Eq5-SWI)",
              "- Data gaps with workarounds",
              "- Recommendations for improving data coverage",
            ].join("\n"),
          },
        },
      ],
    })
  );
}
