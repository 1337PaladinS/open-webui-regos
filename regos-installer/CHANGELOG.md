# Changelog

All notable changes to the RegOS Installer will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.9.0] - 2026-03-10

### Added

- **Email-based guest access** — Guests must now enter a real email address before accessing RegOS in guest mode. The email is used to create a persistent guest account, so returning guests can continue from where they left off. If the same email returns, the system checks their generation limit — if exceeded, they're told to sign up. The login page shows a two-step flow: click "Continue as Guest" → enter email → go. If the email belongs to a registered (non-guest) user, the system rejects the guest login and tells them to sign in normally.

- **Guest group auto-assignment** — New guest users are automatically added to the "guest" group (case-insensitive name lookup). This ensures guests can access the models defined for the guest group. If no "guest" group exists, the user is created without group assignment (logged as warning).

- **Guests tab in admin panel** — Admin → Users now has three tabs: Overview, Guests, and Groups. The Guests tab shows only guest users (role=guest), while Overview hides guests to keep the registered user list clean. Both tabs use the same sortable, searchable UserList component. Backend `GET /users/` now supports a `roles` query parameter with include/exclude syntax (e.g. `roles=guest` or `roles=!guest`).

### Fixed

- **Guest generation limit enforcement** — Previously, each guest click created a brand new user with a fresh UUID, so the generation limit check always found 0 previous chats and never triggered. Now, the same email maps to the same user_id, so chat history accumulates across sessions and the limit actually works. Also fixed: chat fetch limit was capped at `GUEST_MESSAGE_LIMIT + 1` (11), missing chats beyond that; now fetches up to 500 for accurate counting. The chat limit now reads from the configurable `REGOS_GUEST_MESSAGE_LIMIT` instead of the hardcoded `GUEST_MESSAGE_LIMIT`.

### Changed

- **Source patcher expanded** — `apply-patches.py` now patches 13 files (up from 7): added patches for auths.py (email-based guest endpoint), auths/index.ts (email param), users.py router (roles filter), users/index.ts (roles param), Users.svelte (Guests tab), UserList.svelte (role filter props). Fragment files stored in `source-patches/fragments/` for complex replacements.

---

## [1.8.0] - 2026-03-10

### Added

- **One-command deployment (`setup.sh`)** — New master script that orchestrates the full RegOS deployment pipeline on stock Open WebUI. Clones the source (or uses an existing checkout), runs the surgical Python patcher, optionally applies branding, builds via Docker Compose, installs the neo4j driver, and runs the full installer. Eliminates the need to maintain a separate fork. Usage: `./setup.sh --clone --token <jwt>`.

- **Source patcher (`source-patches/apply-patches.py`)** — Python script that surgically injects RegOS features into stock Open WebUI source files. Patches 7 files (config.py, main.py, configs.py, configs/index.ts, admin layout, app layout, auth page) using anchor-based injection. Copies 3 new files (RegOS.svelte, RegOSDisclaimerModal.svelte, regos route page). Idempotent — safe to re-run on already-patched source.

- **Branding support** — `setup.sh` looks for a `branding/` directory containing custom static assets (logos, favicons, splash screens) and an `app_name.txt` for the display name. If present, assets are copied into the source tree before Docker build.

### Changed

- **README overhauled** — `setup.sh` is now the primary entry point. Added full usage guide, options table, and updated repo structure. `install.sh` documented as advanced/granular alternative.

- **Repo structure** — Added `source-patches/` directory with patcher and new files, documented `branding/` convention.

---

## [1.7.0] - 2026-03-10

### Added

- **Guest generation limit** — Configurable limit on total AI responses (generations) a guest can receive across all chats per session (default: 50). Separate from the existing chat limit (default: 10). Enforced server-side in `chat_completion`. Configurable via Admin → RegOS → Guest Access.

- **Safe rebuild documentation** — Added comprehensive "Rebuilding After Source Changes" section to README with step-by-step safe rebuild process, recovery instructions for wrong-volume incidents, and post-rebuild checklist. Updated docs/readme1.md with matching warnings.

### Changed

- **RegOS admin tab moved to top-level** — RegOS is now a top-level tab in the admin navigation bar (alongside Users, Analytics, Evaluations, Functions, Settings) instead of a sub-tab inside Settings.

- **README overhauled** — Added `--configure` usage example, `REGOS_GUEST_GENERATION_LIMIT` to config table, "Configure RegOS settings" to post-install steps, `test-admin-panel.sh` to repo structure.

### Fixed

- **Docker volume safety** — Documented that `docker compose up -d --build` must always be used instead of raw `docker run`. Using `docker run -v open-webui:/app/backend/data` creates an empty volume (the compose volume is `open-webui-regos_open-webui`), causing apparent data loss. Added recovery instructions.

---

## [1.6.0] - 2026-03-10

### Added

- **RegOS Admin Panel Tab** — Custom settings tab in Open WebUI admin panel (Admin → Settings → RegOS) with three configurable sections:
  - **Onboarding Disclaimer**: Enable/disable, editable markdown body with live preview, configurable title and accept button label
  - **Guest Access**: Enable/disable guest mode, show/hide the login page button, configurable message limit and session TTL
  - **Confidence Display**: Enable/disable confidence banners, style selector (emoji_blockquote/plain_text/hidden), configurable HIGH and MEDIUM threshold sliders with live band preview

- **Backend API endpoints for RegOS config**:
  - `GET /api/v1/configs/regos` — Admin-only, returns all RegOS settings
  - `POST /api/v1/configs/regos` — Admin-only, updates RegOS settings
  - `GET /api/v1/configs/regos/public` — Authenticated users, returns disclaimer config for modal rendering
  - `GET /api/v1/configs/regos/guest-status` — Unauthenticated, returns guest button visibility for login page

- **13 PersistentConfig entries** — All RegOS settings stored in the Open WebUI config database, surviving container restarts

- **Configurable confidence thresholds (graphrag_filter v0.20.0)** — Added `confidence_high_threshold` and `confidence_medium_threshold` Valves to the graphrag_filter. Previously hardcoded at 0.70/0.45, now configurable via Valves or synced from the admin panel.

- **Step 10 installer script** (`steps/10-regos-admin.sh`) — Verifies admin panel API endpoints, optionally pushes initial configuration, syncs confidence thresholds to graphrag_filter valves. Use `--configure` flag to push defaults.

- **Dynamic guest button on login page** — "Continue as Guest" button now reads visibility from the RegOS admin config (`/configs/regos/guest-status`). Admins can show/hide the button without redeploying.

- **Dynamic disclaimer modal** — Disclaimer modal now reads title, body, and accept label from admin config. Supports full markdown with fallback to hardcoded default content.

### Changed

- **install.sh** — Added `--configure` flag and step 10 to the run sequence
- **README.md** — Added admin panel to components table and step 10 to installation steps

---

## [1.5.0] - 2026-03-09

### Added

- **Color-Coded Confidence Banners (graphrag_filter v0.19.0)** — Replaced the plain-text italic disclaimer at the bottom of responses with a visually distinct, color-coded markdown blockquote banner. Each response now ends with a confidence indicator using colored circle emoji and bold labeling:
  - 🟢 **HIGH CONFIDENCE** (≥70% + full retrieval) — green circle, confirms response is well-supported by cited sections
  - 🟠 **MODERATE CONFIDENCE** (45–69% or partial retrieval) — orange circle, acknowledges possible gaps
  - 🔴 **LOW CONFIDENCE** (<45% or ≤1 section) — red circle, advises verification against full regulation text
  - Banner uses markdown blockquote (`>`) for universal rendering across Open WebUI versions
  - Includes section reference range (e.g., "Sections [G1]–[G5]") and actionable guidance per band

- **`show_confidence` Valve Now Functional** — The `show_confidence` valve (previously defined but never checked) is now wired into the outlet logic. When disabled, confidence banners are suppressed while confidence data is still recorded for audit.

### Changed

- **Disclaimer no longer gated by `enterprise_format`** — Previously, the confidence disclaimer only appeared when both `has_confidence` and `enterprise_format` were true. Now, the confidence banner is controlled independently by the `show_confidence` valve, making it usable with any response format.

- **Outlet logging added** — The outlet now logs `[OUTLET] Appending confidence banner: score=X, band=Y` when a banner is appended, aiding debugging of the disclaimer pipeline.

### Fixed

- **Missing disclaimer due to `neo4j` module** — Identified that the `neo4j` Python driver must be installed inside the Docker container (`pip install neo4j`) for the graph retrieval pipeline to function. Without it, the inlet catches a `ModuleNotFoundError`, nulls out confidence data, and the outlet has nothing to append. The LLM still produces enterprise-formatted responses (with hallucinated citation references) but no confidence scoring or disclaimer.

- **HTML rendering issue** — Initial implementation used inline HTML (`<div>`, `<span>` with `style` attributes) for the confidence banner. Open WebUI's markdown sanitizer strips these tags, causing raw HTML to display as text. Switched to pure markdown (blockquote + emoji + bold) which renders correctly across all Open WebUI versions.

---

## [1.4.0] - 2026-03-08

### Added

- **Guest Access Mode** — ChatGPT-style anonymous guest experience allowing visitors to try RegOS without creating an account:
  - New `POST /api/v1/auths/guest` endpoint that creates a throwaway user with `role: "guest"`, issues a 3-hour JWT, and returns locked-down permissions
  - Guest rate limiting: max 10 chats per session (configurable via `GUEST_MESSAGE_LIMIT`)
  - Comprehensive permission lockdown via `GUEST_USER_PERMISSIONS` — workspace, chat management, knowledge, and model access all disabled
  - Frontend "Continue as Guest" button on login page
  - Enhanced error display for guest limit with signup link
  - Auth gate updated to accept `guest` role alongside `user` and `admin`

- **Onboarding Disclaimer Modal** — One-time service agreement modal for all users on first visit:
  - Fires on first page load for admin, user, and guest roles
  - Persisted via `regosDisclaimerAcked` in user settings
  - Chains after changelog modal if both need to show

- **Step 09 verification script** — `steps/09-guest-disclaimer.sh` validates guest endpoint, permissions lockdown, JWT TTL, source file presence, and frontend build artifacts

- **Documentation** — `RegOS_Disclaimer_GuestMode_Build_Documentation.docx` covering executive summary, technical implementation, Docker build pipeline, bugs encountered, config reference, security considerations, and testing checklist

### Environment Variables (New)

| Variable | Default | Description |
|---|---|---|
| `GUEST_MESSAGE_LIMIT` | `10` | Max chats per guest session |
| `GUEST_MESSAGE_WINDOW` | `10800` | Guest rate window in seconds (3 hours) |

---

## [1.3.0] - 2026-03-06

### Added

- **Neo4j Failover Handling (graphrag_filter)** — Connection failures to the Neo4j knowledge graph are now detected separately from zero-retrieval guardrails. Previously, if Neo4j was down the exception was silently caught and the user saw a raw LLM response with no regulatory context and no warning. Now:
  - Neo4j-specific exceptions (`ServiceUnavailable`, `SessionExpired`, `DriverError`, connection refused/timeout) are identified by class name and error message pattern.
  - **Degraded mode (default):** When `neo4j_fallback_to_kb = True`, the query passes through to the LLM with Knowledge Base context only. A system notice is injected so the LLM knows graph context is missing, and a "Degraded Mode — Knowledge Base Only" banner is appended to the response.
  - **Hard block mode:** When `neo4j_fallback_to_kb = False`, a "System Temporarily Unavailable" guardrail notice is shown and the query does not reach the LLM.
  - The cached Neo4j driver is invalidated on failure so the next request retries with a fresh connection.
  - Both modes log the event to the audit DB via the existing `graphrag_guardrail` message dict (type: `neo4j_unavailable` or `neo4j_degraded`).
  - New Valve: `neo4j_fallback_to_kb` (default: `True`)

- **End-User Guide (`docs/RegOS_User_Guide.docx`)** — New document for colleagues covering: what RegOS is, how to access it, understanding response sections (citations, confidence scores, action items), document upload and analysis, tips for better results, limitations, and sidecar API overview.

### Changed

- **Install script Step 05 — function registration fixed** — `lib/api.sh` now uses the correct Open WebUI API paths with the `/id/` segment: `GET /api/v1/functions/id/{id}` for existence checks and `POST /api/v1/functions/id/{id}/update` for updates. The `api::register_function` function was rewritten to build JSON payloads via Python (avoiding shell escaping issues with large files) and write to a temp file for `curl -d @file`.

- **`threshold_eval` removed from function registration** — `steps/05-register-functions.sh` no longer registers `threshold_eval:filter` since threshold evaluation is built into `graphrag_filter` (integrated in v0.14.0).

- **Config placeholder fixed** — `config/install.conf` no longer contains a hardcoded `https://<your-openwebui-host>` placeholder that overrode CLI `--api-url` arguments. Now uses `${OPENWEBUI_URL:-http://localhost:3000}`.

- **Debug logging removed from graphrag_filter** — All `/tmp/doc-debug.log` file-writing debug functions (`_dbg()`, `_vdbg()`) have been removed from production code. Error logging via `_doc_logger` is preserved.

---

## [1.2.0] - 2026-03-05

### Added

- **Document Analysis in GraphRAG filter (v0.18.0)** — The core filter now automatically detects uploaded files (PDF, DOCX, XLSX, PPTX, images) and sends them to a configurable vision model (default: GPT-4o via OpenRouter) for structured analysis. The vision model extracts form fields, table data, filled/empty status, and compliance concerns. The analysis is injected into the user message as context so the primary model can reason over document content without needing vision capabilities itself.
  - New Valves: `doc_analysis_enabled`, `doc_vision_model`, `doc_openwebui_url`, `doc_max_pages`, `doc_analysis_detail`
  - Supports PDF (via pdftoppm), Office documents (via LibreOffice headless), and direct images
  - Document analysis persists through all code paths: guardrail early returns, zero-retrieval, and retrieval errors
  - Sets `file_handler = True` to intercept file uploads before Open WebUI's default RAG processing

---

## [1.1.0] - 2026-03-05

### Added

- **Sidecar API (`api/regos_api.py`)** — New single-endpoint FastAPI proxy that chains Open WebUI's inlet → LLM → outlet pipeline into one HTTP call. External consumers POST a question and get back a fully-scored, cited, trace-enabled response without needing to know Open WebUI internals.
  - Blocking mode: POST `/api/regos/query` returns a complete `RegOSResponse` with content, model, confidence band, and usage stats.
  - Streaming mode: `"stream": true` returns Server-Sent Events (SSE) with real-time token delivery, followed by outlet-appended confidence/trace chunks.
  - Reasoning/thinking token support: `"show_reasoning": true` (disabled by default) streams the model's chain-of-thought as separate SSE events with `reasoning_start` / `reasoning_end` markers. Supports OpenRouter/DeepSeek (`reasoning_content`), Anthropic (`thinking`), and generic (`reasoning`) field names.
  - Health endpoint: `GET /api/regos/health` checks connectivity to Open WebUI.
  - Info endpoint: `GET /api/regos/info` returns sidecar version, model config, and available endpoints.
  - Default model changed to `better-hardeepai` (configurable via `REGOS_MODEL_ID` env var).

- **API source tagging for audit records** — All sidecar API calls are tagged with `regos-api:<uuid>` prefix on `session_id` and `api-<uuid>` prefix on `chat_id`, allowing audit records to be filtered by origin (API vs browser UI).

- **Diagnostic logging in sidecar** — `[OUTLET]` and `[OUTLET-STREAM]` log lines for debugging outlet filter calls, including response status and message counts.

- **Python module init (`api/__init__.py`)** — Empty init file to make the `api/` directory a proper Python package, required for `python -m uvicorn api.regos_api:app` to resolve correctly.

### Changed

- **audit_logger.py v0.4.0 → v0.5.0** — Updated to support API-originated queries where Open WebUI's dunder parameters (`__chat_id__`, `__session_id__`, `__message_id__`) are empty:
  - **Inlet**: Falls back to `body.get("chat_id")`, `body.get("id")`, and `body.get("session_id")` when the corresponding dunder params are empty. This ensures API calls via the sidecar have their source tags written to audit records.
  - **Outlet UPDATE**: Now also sets `chat_id` and `session_id` on the audit record if they were empty at inlet time (using `CASE WHEN chat_id = '' THEN ? ELSE chat_id END` pattern).

### Environment Variables (New)

| Variable | Default | Description |
|---|---|---|
| `OPENWEBUI_URL` | `https://<your-openwebui-host>` | Open WebUI base URL (e.g. `https://eqcb.apas.ai`) |
| `OPENWEBUI_TOKEN` | *(required)* | Open WebUI admin API token |
| `REGOS_MODEL_ID` | `better-hardeepai` | Model ID to use for queries |
| `REGOS_DEFAULT_STREAM` | `false` | Default streaming mode |
| `REGOS_API_PORT` | `8300` | Sidecar API listen port |

### Testing

All tests passed on 2026-03-05 against a live Open WebUI Docker instance:

| Test | Result |
|---|---|
| Health check (`GET /api/regos/health`) | PASSED |
| Blocking query (`POST /api/regos/query`) | PASSED |
| Streaming query (`stream: true`) | PASSED |
| Reasoning streaming (`show_reasoning: true`) | PASSED |
| Audit logging (records written to `audit.db`) | PASSED |
| Source tagging (`regos-api:` prefix in `session_id`) | PASSED |
| Outlet integration (200 response, confidence appended) | PASSED |

---

## [1.0.0] - 2026-03-01

### Added

- Initial release of regos-installer
- Modular install steps (01-08): container detection, neo4j driver install, data file copy, script copy, function registration, model creation, group setup, verification
- Open WebUI filter functions: `graphrag_filter`, `audit_logger` (v0.4.0), `threshold_eval`
- Data files: `regulatory_thresholds.json` (96 limits), `concepts.json`, `apas_metric_mappings.json`
- Demo scripts: hash verification, record display, tamper simulation
- Custom model creation: "RegOS Compliance Copilot" with system prompt
- Configuration via `config/install.conf` and `.env` overrides
- Makefile for common operations
- Full documentation in `docs/`
