# breach_api.py — Compliance Breach REST API

## Status: Active (v1.0.0)

A standalone FastAPI service that provides REST endpoints for querying the compliance breach database. Designed to power external dashboards and reporting tools.

## Endpoints

| Method | Path                              | Purpose                                                  |
| ------ | --------------------------------- | -------------------------------------------------------- |
| GET    | `/api/breaches/summary`           | Counts, breach rate, top breached parameters             |
| GET    | `/api/breaches`                   | List breach records (filterable by date)                 |
| GET    | `/api/breaches/evaluations`       | All evaluations (breach + compliant)                     |
| POST   | `/api/breaches/check`             | Run threshold check via API                              |
| GET    | `/api/breaches/parameters`        | List available parameters                                |
| GET    | `/api/breaches/thresholds/{param}`| Get thresholds for a specific parameter                  |
| GET    | `/api/breaches/verify/{hash}`     | Verify SHA-256 evidence hash integrity                   |

## Dependencies

- `functions/threshold_eval.py` — ThresholdEvaluationService and ThresholdRegistry
- SQLite breach database (shared with graphrag_filter.py and scada_stream.py)
- FastAPI with CORS (can run standalone or be mounted)

## Data Flow

Chat queries and SCADA readings both write evaluations to the same breach SQLite DB. This API reads from that DB and also supports running new evaluations via the POST endpoint.
