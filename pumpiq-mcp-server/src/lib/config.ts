/**
 * PumpIQ MCP Server — Configuration
 *
 * All external API base URLs, default parameters, and environment
 * variable mappings. Mirrors the Postman environment file.
 */

// ─── Base URLs ───────────────────────────────────────────────────────

export const NOAA_COOPS_BASE =
  "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter";

export const NOAA_COOPS_METADATA =
  "https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations";

export const NOAA_CDO_BASE =
  "https://www.ncei.noaa.gov/cdo-web/api/v2";

export const USGS_NWIS_IV =
  "https://waterservices.usgs.gov/nwis/iv";

export const USGS_NWIS_GW =
  "https://waterservices.usgs.gov/nwis/gwlevels";

export const USGS_OGC_BASE =
  "https://api.waterdata.usgs.gov/ogcapi/v0";

export const SFWMD_ARCGIS =
  "https://geoweb.sfwmd.gov/agsext2/rest/services/MonitoringLocations/DBHYDRO_Wells/FeatureServer";

export const SFWMD_OPEN_DATA =
  "https://services1.arcgis.com/JUFjVsTLBSJBNwGq/arcgis/rest/services/Wells_and_Boreholes/FeatureServer/0/query";

// ─── Default Parameters (Miami-Dade) ─────────────────────────────────

export const DEFAULTS = {
  noaa_station: "8723214",           // Virginia Key, Biscayne Bay
  noaa_cdo_station: "COOP:084210",   // Miami Intl Airport
  noaa_ghcnd_station: "GHCND:USW00012839", // Miami Intl Airport (GHCND)
  miami_dade_fips: "12086",
  usgs_gw_param: "62610",           // GW level above NGVD 1929
  usgs_conductivity_param: "00095", // Specific conductance (µS/cm)
  datum: "MLLW",
  timezone: "gmt",
  units: "english",
  application: "PumpIQ",
} as const;

// ─── Environment Variables ───────────────────────────────────────────

export function getNoaaCdoToken(): string {
  const token = process.env.NOAA_CDO_TOKEN;
  if (!token) {
    throw new Error(
      "NOAA_CDO_TOKEN environment variable is not set. " +
      "Register at https://www.ncdc.noaa.gov/cdo-web/token to get a free token."
    );
  }
  return token;
}

export function getSfwmdApiKey(): string | null {
  return process.env.SFWMD_API_KEY ?? null;
}
