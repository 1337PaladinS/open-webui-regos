/**
 * PumpIQ MCP Server — Shared Types
 *
 * Type definitions for all external API responses, tool inputs/outputs,
 * and internal data structures.
 */

// ─── NOAA CO-OPS Types ───────────────────────────────────────────────

export interface NoaaCoopsReading {
  t: string;   // timestamp e.g. "2026-03-31 12:00"
  v: string;   // value
  s?: string;  // sigma (standard deviation)
  f: string;   // quality flags
  q?: string;  // quality assurance
}

export interface NoaaCoopsResponse {
  metadata?: {
    id: string;
    name: string;
    lat: string;
    lon: string;
  };
  data?: NoaaCoopsReading[];
  predictions?: NoaaCoopsReading[];
  error?: { message: string };
}

export interface NoaaStationMetadata {
  id: string;
  name: string;
  lat: number;
  lng: number;
  state: string;
  products?: { name: string }[];
  details?: Record<string, unknown>;
}

export interface HighLowTide {
  time: string;
  value: number;
  type: "high" | "low";
}

// ─── NOAA CDO Types ──────────────────────────────────────────────────

export interface NoaaCdoDataResult {
  date: string;
  datatype: string;
  station: string;
  attributes: string;
  value: number;
}

export interface NoaaCdoResponse {
  metadata?: {
    resultset: {
      offset: number;
      count: number;
      limit: number;
    };
  };
  results?: NoaaCdoDataResult[];
}

export interface NoaaCdoStation {
  id: string;
  name: string;
  latitude: number;
  longitude: number;
  mindate: string;
  maxdate: string;
  datacoverage: number;
}

export interface NoaaCdoDataset {
  id: string;
  name: string;
  mindate: string;
  maxdate: string;
  datacoverage: number;
}

// ─── USGS NWIS Types ─────────────────────────────────────────────────

export interface UsgsTimeSeries {
  sourceInfo: {
    siteName: string;
    siteCode: { value: string; network: string }[];
    geoLocation: {
      geogLocation: {
        srs: string;
        latitude: number;
        longitude: number;
      };
    };
  };
  variable: {
    variableName: string;
    variableCode: { value: string }[];
    unit: { unitCode: string };
  };
  values: {
    value: {
      value: string;
      dateTime: string;
      qualifiers: string[];
    }[];
  }[];
}

export interface UsgsNwisResponse {
  value: {
    timeSeries: UsgsTimeSeries[];
  };
}

export interface UsgsOgcCollection {
  id: string;
  title: string;
  description?: string;
  links?: { href: string; rel: string }[];
}

// ─── SFWMD Types ─────────────────────────────────────────────────────

export interface SfwmdFeature {
  geometry: {
    x: number;
    y: number;
  };
  attributes: Record<string, unknown>;
}

export interface SfwmdFeatureResponse {
  features?: SfwmdFeature[];
  error?: { code: number; message: string };
}

// ─── Bounding Box ────────────────────────────────────────────────────

export interface BoundingBox {
  min_lat: number;
  min_lng: number;
  max_lat: number;
  max_lng: number;
}

// ─── Data Readiness ──────────────────────────────────────────────────

export interface DataSourceStatus {
  source: string;
  available: boolean;
  record_count: number;
  date_range?: { start: string; end: string };
  warnings?: string[];
}

export interface IIReadinessReport {
  location: string;
  date_range: { start: string; end: string };
  sources: DataSourceStatus[];
  equations_ready: {
    eq2_gwi: boolean;   // Groundwater Infiltration
    eq3_ti: boolean;    // Tidal Infiltration
    eq4_rdii: boolean;  // Rainfall-Driven I&I
    eq5_swi: boolean;   // Saltwater Intrusion
  };
  overall_readiness: "full" | "partial" | "insufficient";
}
