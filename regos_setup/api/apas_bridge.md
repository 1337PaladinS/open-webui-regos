# apas_bridge.py — APAS Telemetry Bridge

## Status: Active (v0.1.0)

A polling bridge that connects the APAS Telemetry Analytics platform to the RegOS threshold evaluation pipeline. APAS stores SCADA sensor data in TimescaleDB and exposes it via REST API with JWT auth. This bridge polls APAS for new readings, maps metrics to Chapter 24 parameters, applies unit conversions, and feeds results into the SCADA streaming pipeline.

## Architecture

```
APAS Telemetry API (TimescaleDB)
        |
    [JWT auth, polling every 30s]
        |
    apas_bridge.py
        |
    [metric mapping, unit conversion]
        |
    scada_stream.py (evaluate + broadcast)
        |
    breach SQLite DB + SSE subscribers
```

## Components

**Metric Mapping Registry** — Loads `data/apas_metric_mappings.json`. Maps APAS metric names (e.g., `rtu.*.temperature`) to RegOS threshold parameters (e.g., `Temperature`). Supports wildcards via `fnmatch`, configurable unit conversions, and an `evaluate` flag per metric.

**APAS API Client** — JWT auth with auto-refresh (re-auth on 401, proactive at 50 min). Handles pagination and 10-metric-per-query batching. Exponential backoff on errors (1s to 16s cap).

**Polling Loop** — Each cycle: fetch catalog, filter to evaluable metrics, query latest readings, map, convert, evaluate, broadcast.

## Management Endpoints

| Method | Path                    | Purpose                                 |
| ------ | ----------------------- | --------------------------------------- |
| GET    | `/api/apas/status`      | Poller state, throughput, error tracking |
| POST   | `/api/apas/start`       | Start the polling loop                  |
| POST   | `/api/apas/stop`        | Stop the polling loop                   |
| GET    | `/api/apas/mappings`    | List all metric mappings                |
| GET    | `/api/apas/catalog`     | Proxy APAS catalog with mapping annotations |
| POST   | `/api/apas/test-poll`   | Execute one poll cycle manually         |

## Configuration

- `APAS_API_URL` — APAS Telemetry API base URL
- `APAS_USERNAME` / `APAS_PASSWORD` — JWT credentials
- `APAS_POLL_INTERVAL` — polling interval (default 30s)
- Metric mappings in `data/apas_metric_mappings.json`
