# scada_stream.py — SCADA Streaming API

## Status: Active (v0.1.0)

A FastAPI service that receives SCADA (Supervisory Control and Data Acquisition) sensor data in real-time, evaluates each reading against Chapter 24 regulatory thresholds, and streams back compliance determinations.

## Transport Modes

| Mode      | Endpoint              | Pattern                                         |
| --------- | --------------------- | ----------------------------------------------- |
| WebSocket | `/ws/scada`           | Full-duplex streaming. Send readings, receive determinations in real-time. |
| SSE       | `/api/scada/stream`   | One-way push for monitoring clients. Filterable by status and parameter.   |
| REST      | `/api/scada/ingest`   | Batch POST for polling-style integrations. Immediate sync response.        |

## Management Endpoints

- `/api/scada/ingest/single` — single-reading shortcut
- `/api/scada/recent` — last 200 determinations (in-memory buffer)
- `/api/scada/status` — throughput metrics, connection counts
- `/api/scada/health` — health check

## Infrastructure

- Token-bucket rate limiting (configurable, default 100/s)
- Bearer token auth via `SCADA_API_KEY` env var
- Writes to shared breach SQLite DB with SHA-256 evidence hashes
- Broadcasts determinations to all connected SSE subscribers

## Dependencies

- `functions/threshold_eval.py` — ThresholdEvaluationService.evaluate()
- Shared breach SQLite database
