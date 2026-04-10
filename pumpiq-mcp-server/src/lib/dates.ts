/**
 * PumpIQ MCP Server — Date Format Utilities
 *
 * Each external API uses a different date format:
 *   NOAA CO-OPS: YYYYMMDD  (no hyphens)
 *   NOAA CDO:    YYYY-MM-DD (with hyphens)
 *   USGS NWIS:   ISO 8601 period (P1D, P7D, P30D)
 *
 * These utilities normalize user-friendly input (YYYY-MM-DD)
 * into the correct format for each API.
 */

/**
 * Convert YYYY-MM-DD to YYYYMMDD for NOAA CO-OPS.
 */
export function toCoopsDate(date: string): string {
  return date.replace(/-/g, "");
}

/**
 * Ensure date is in YYYY-MM-DD format for NOAA CDO.
 * Accepts both YYYYMMDD and YYYY-MM-DD inputs.
 */
export function toCdoDate(date: string): string {
  const clean = date.replace(/-/g, "");
  if (clean.length !== 8) {
    throw new Error(`Invalid date "${date}": expected YYYY-MM-DD or YYYYMMDD`);
  }
  return `${clean.slice(0, 4)}-${clean.slice(4, 6)}-${clean.slice(6, 8)}`;
}

/**
 * Validate an ISO 8601 period string (e.g. P1D, P7D, P30D).
 */
export function validatePeriod(period: string): string {
  if (!/^P\d+[DWMY]$/i.test(period)) {
    throw new Error(
      `Invalid period "${period}": expected ISO 8601 format like P1D, P7D, P30D`
    );
  }
  return period.toUpperCase();
}

/**
 * Get today's date in YYYY-MM-DD format.
 */
export function todayISO(): string {
  return new Date().toISOString().slice(0, 10);
}

/**
 * Get a date N days ago in YYYY-MM-DD format.
 */
export function daysAgoISO(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d.toISOString().slice(0, 10);
}
