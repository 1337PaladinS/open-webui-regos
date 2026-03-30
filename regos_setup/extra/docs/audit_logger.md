# Audit Logger — RegOS

**Type:** Filter (inlet + outlet)
**Version:** 0.4.0
**Status:** Deployed and tested
**File:** `audit_logger.py`
**Depends on:** SQLite (built into Python)

---

## What is this?

**For non-technical readers:**

The Audit Logger is Open WebUI's memory system for chat conversations. Every time someone asks a question and gets an answer, the Audit Logger writes down a permanent record: who asked, what they asked, which AI model answered, what the answer was, and when it happened. Think of it like a detailed logbook that never forgets.

This record stays in a database file forever — unless someone explicitly deletes it. And here's the tamper-detection part: the system uses a cryptographic hash (a fingerprint) on each record. If anyone tries to change what was asked, what was answered, or when it happened, the fingerprint won't match anymore. This makes it impossible to hide who said what, when, and to whom.

The Audit Logger is the foundation that other safety systems (confidence scoring, escalation to humans, guardrails) build on. They all add their own data to these records — but the Audit Logger creates the record first.

**For technical readers:**

The Audit Logger is a filter that intercepts every chat interaction before the LLM (inlet) and after the LLM responds (outlet). It creates structured SQLite records that capture full conversation context, metadata, and serves as the canonical audit trail. The filter also extracts supplementary data from downstream filters (confidence, escalation, guardrails) via a message dict mutation pattern, and signs records with SHA-256 hashes for tamper-evidence.

---

## How it works

### The inlet/outlet pattern

The filter has two hooks that fire on every chat message:

**Inlet (before the LLM):** When a user sends a message, the inlet fires first. It extracts the user's question from the message body, captures all available metadata (user ID, email, name, role, chat ID, message ID, session ID, model name), and writes an initial audit record to the database. The `response_text` field is left empty at this point — it gets filled in by the outlet.

**Outlet (after the LLM responds):** After the LLM generates a response, the outlet fires. It extracts the assistant's response text from the message body, then queries the database for the most recent audit record belonging to this user that has a query but no response yet. It updates that record with the response text and model info.

The matching between inlet and outlet is done via a database query (`WHERE user_id = ? AND response_text = '' AND query_text != '' ORDER BY epoch DESC LIMIT 1`) rather than in-memory state, because Open WebUI may use different Filter instances for inlet and outlet calls.

### Why this pattern matters

Open WebUI processes messages through a chain of filters. Each filter instance is separate and cannot share state (memory) with other filter instances. By writing to a database in the inlet and querying it in the outlet, the Audit Logger avoids state sharing and works reliably even if the filter is reinstantiated between calls.

---

## Database location

```
/app/backend/data/audit.db
```

This is inside the Open WebUI Docker volume, so it persists across container restarts. It is a separate file from Open WebUI's main `webui.db` database — audit data has its own lifecycle.

The path is configurable via the `db_path` Valve in the admin UI.

---

## Schema

```sql
CREATE TABLE audit_records (
    -- Identity
    id TEXT PRIMARY KEY,              -- UUID for this audit record
    timestamp TEXT NOT NULL,           -- ISO 8601 UTC timestamp
    epoch REAL NOT NULL,               -- Unix epoch for sorting and range queries

    -- Who asked
    user_id TEXT,                      -- Open WebUI user UUID
    user_email TEXT,                   -- User's email address
    user_name TEXT,                    -- User's display name
    user_role TEXT,                    -- "admin" or "user"

    -- Session context
    chat_id TEXT,                      -- Open WebUI chat/conversation UUID
    message_id TEXT,                   -- Specific message UUID within the chat
    session_id TEXT,                   -- Browser session ID (may be empty)

    -- What was asked
    model TEXT,                        -- Model ID used (e.g. "gemini-2.5-pro")
    query_text TEXT,                   -- The user's question (plain text)
    message_count INTEGER,             -- Number of messages in the conversation at query time
    full_messages TEXT,                -- JSON array of the last 5 messages for context

    -- What was answered
    response_text TEXT,                -- The LLM's full response text
    response_model TEXT,               -- Model that generated the response

    -- Retrieval context (populated by GraphRAG Filter — Feature 2)
    retrieval_record TEXT,             -- JSON: which chunks were retrieved, scores, which were used
    citations TEXT,                    -- JSON: each citation with section number, document, version

    -- Confidence (populated by Confidence Scoring — Feature 4)
    confidence_score REAL,             -- System-computed confidence score (0.0 to 1.0)
    confidence_signals TEXT,           -- JSON: individual signals that composed the score

    -- Escalation (populated by Escalation Workflow — Feature 5)
    escalation_triggered INTEGER DEFAULT 0,
    escalation_target TEXT,
    case_packet_ref TEXT,

    -- Guardrails (populated by Refusal & Guardrails — Feature 8)
    guardrail_triggered INTEGER DEFAULT 0,
    guardrail_type TEXT,
    guardrail_reason TEXT,

    -- Integrity
    record_hash TEXT                   -- SHA-256 hash for tamper evidence
);
```

### Column guide (non-technical explanation)

| Column | Purpose | Why it matters |
|---|---|---|
| `id`, `timestamp`, `epoch` | **Record identity** — Every record is timestamped and given a unique ID so you can find it later | You need to know when things happened and be able to retrieve specific records |
| `user_id`, `user_email`, `user_name`, `user_role` | **Who was chatting** — Captures the person asking the question | Accountability: you need to know who asked what and what their role/permissions were |
| `chat_id`, `message_id`, `session_id` | **Where in the conversation** — Ties this interaction to a specific chat thread and browser session | For reconstructing full conversation context and understanding how messages relate to each other |
| `model`, `query_text`, `message_count`, `full_messages` | **What was asked** — The actual question plus the last 5 messages in the conversation | So you can see exactly what the user asked and what context the LLM had when answering |
| `response_text`, `response_model` | **What was answered** — The LLM's full response and which model generated it | The complete output for review, compliance, or reproducing the answer |
| `retrieval_record`, `citations` | **Where the answer came from** — Which documents were retrieved, how relevant they were, and what was actually used | For verifying that answers are based on the right source material, not hallucinations |
| `confidence_score`, `confidence_signals` | **How confident the system is** — A 0-1 score and the reasoning behind it | For identifying answers the system isn't sure about, triggering human review when needed |
| `escalation_triggered`, `escalation_target`, `case_packet_ref` | **Did it need human attention?** — Indicates whether this conversation was flagged for a human to review, and who/why | For compliance and quality assurance — humans need to review risky or uncertain cases |
| `guardrail_triggered`, `guardrail_type`, `guardrail_reason` | **Did safety rules kick in?** — Whether the system detected a prohibited topic and what kind (jailbreak attempt, PII disclosure request, etc.) | Safety audit — you need to know if/when the system blocked unsafe requests |
| `record_hash` | **Tamper detection** — Cryptographic fingerprint of the record | If anyone modifies the record, the hash won't match anymore, proving tampering |

### Indexes

```sql
idx_audit_timestamp  -- On epoch, for time-range queries (fast: "give me all records from last 7 days")
idx_audit_user       -- On user_id, for per-user audit trails (fast: "show me everything Alice asked")
idx_audit_chat       -- On chat_id, for per-conversation audit trails (fast: "reconstruct this conversation")
```

These indexes make queries fast even when the audit table has millions of records.

---

## Method documentation

### `__init__()`

**What it does:** Initializes the filter when Open WebUI starts it.

**Non-technical:** Think of this as the setup phase. The filter reads the admin settings (Valves) — like whether it's turned on, where the database file should be, and what priority it should run at. It stores these settings so the rest of the filter code can use them.

**Technical:** Stores the Valve objects and sets `self.enabled` and `self.db_path` from configuration. This is where priority ordering is set — must be higher than GraphRAG filter (typically 1 vs 0).

```python
def __init__(self):
    self.valves = Valves(
        priority=0,
        db_path="/app/backend/data/audit.db",
        enabled=True
    )
    self.enabled = self.valves.enabled
    self.db_path = self.valves.db_path
```

---

### `_ensure_db()`

**What it does:** Lazily creates the database and tables if they don't exist yet. Runs on first filter execution.

**Non-technical:** The first time the Audit Logger runs, it checks: "Is there a database file here? Does it have the right table? Do the indexes exist?" If anything is missing, it creates it. This is called "lazy initialization" — don't set it up until you need it, then set it up once.

**Technical:** Implements lazy initialization pattern. Opens SQLite connection, checks if `audit_records` table exists, and if not: creates the table with all columns, then creates the three indexes. If the database file itself doesn't exist, SQLite creates it automatically on connection.

Idempotent: calling it multiple times is safe — the `IF NOT EXISTS` clause prevents re-creation.

```python
def _ensure_db(self):
    """Create table and indexes if not exists."""
    conn = sqlite3.connect(self.db_path)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_records (
            id TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            epoch REAL NOT NULL,
            user_id TEXT,
            user_email TEXT,
            user_name TEXT,
            user_role TEXT,
            chat_id TEXT,
            message_id TEXT,
            session_id TEXT,
            model TEXT,
            query_text TEXT,
            message_count INTEGER,
            full_messages TEXT,
            response_text TEXT,
            response_model TEXT,
            retrieval_record TEXT,
            citations TEXT,
            confidence_score REAL,
            confidence_signals TEXT,
            escalation_triggered INTEGER DEFAULT 0,
            escalation_target TEXT,
            case_packet_ref TEXT,
            guardrail_triggered INTEGER DEFAULT 0,
            guardrail_type TEXT,
            guardrail_reason TEXT,
            record_hash TEXT
        )
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_records(epoch)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_records(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_chat ON audit_records(chat_id)")

    conn.commit()
    conn.close()
```

---

### `_compute_hash()`

**What it does:** Generates a SHA-256 tamper-detection hash for a record.

**Non-technical:** Imagine you write something important on a piece of paper. Before you file it away, you write down a cryptographic fingerprint of that paper. Later, if someone modifies the paper, you recompute the fingerprint — and it won't match. This proves tampering. That's what this method does: it takes the record data and computes an irreversible fingerprint (SHA-256 hash).

**Technical:** Takes a dict of fields and returns a hex-encoded SHA-256 hash. Used in both inlet (for the query half) and outlet (for the response half). The hash input is carefully ordered to ensure consistent hashing.

Inlet hash input: record ID + query text + timestamp
Outlet hash input: record ID + response text

```python
def _compute_hash(self, data_dict):
    """Compute SHA-256 hash of a record for tamper evidence."""
    # Sort keys for deterministic hashing
    sorted_items = sorted(data_dict.items())
    data_string = json.dumps(sorted_items, default=str)
    return hashlib.sha256(data_string.encode()).hexdigest()
```

---

### `inlet()`

**What it does:** Fires when a user sends a message. Captures the query and all metadata, writes an initial record to the database.

**Non-technical:** When you ask a question in the chat, this method runs first. It reads: your user ID, your email, the chat ID, the conversation history, the model name, and your question text. It then writes all of this to the database (except the response — that's empty because the LLM hasn't answered yet). It also computes a tamper-detection hash.

**Technical:** Extracts metadata from Open WebUI body object (user, chat, message, model). Captures the last 5 messages in JSON for context. Generates a unique record ID and timestamp. Inserts a new row into `audit_records` with all inlet data plus an empty `response_text`. Computes and stores the inlet hash.

Error handling: wrapped in try/except that silently swallows all exceptions and returns body unchanged. The filter never breaks the chat.

```python
def inlet(self, body: dict, **kwargs) -> dict:
    """Inlet: capture query metadata and write initial record."""
    try:
        if not self.enabled:
            return body

        self._ensure_db()

        # Extract metadata
        user_id = body.get("user", {}).get("id")
        user_email = body.get("user", {}).get("email")
        user_name = body.get("user", {}).get("name")
        user_role = body.get("user", {}).get("role")
        chat_id = body.get("chat", {}).get("id")
        message_id = body.get("message", {}).get("id")
        session_id = body.get("session_id", "")
        model = body.get("model", "")

        # Extract query from messages
        messages = body.get("messages", [])
        query_text = ""
        if messages and messages[-1].get("role") == "user":
            query_text = messages[-1].get("content", "")

        # Create record
        record_id = str(uuid.uuid4())
        timestamp = datetime.utcnow().isoformat() + "Z"
        epoch = time.time()

        # Capture last 5 messages for context
        full_messages = json.dumps(messages[-5:], default=str)
        message_count = len(messages)

        # Compute inlet hash
        inlet_data = {
            "id": record_id,
            "query_text": query_text,
            "timestamp": timestamp,
        }
        inlet_hash = self._compute_hash(inlet_data)

        # Write to database
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO audit_records (
                id, timestamp, epoch,
                user_id, user_email, user_name, user_role,
                chat_id, message_id, session_id,
                model, query_text, message_count, full_messages,
                response_text, response_model,
                record_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            record_id, timestamp, epoch,
            user_id, user_email, user_name, user_role,
            chat_id, message_id, session_id,
            model, query_text, message_count, full_messages,
            "", "",  # response_text, response_model empty
            inlet_hash
        ))
        conn.commit()
        conn.close()

    except Exception as e:
        # Silent fail — never break the user's chat
        pass

    return body
```

---

### `outlet()`

**What it does:** Fires after the LLM responds. Captures the response text, extracts confidence/escalation/guardrail data from the message dict, and updates the initial record.

**Non-technical:** After the AI model answers your question, this method runs. It reads the AI's response, then looks at the messages to see if any downstream filters (the confidence system, escalation system, safety guardrails) left any data attached. It finds the audit record that was created in the inlet, and updates it with: the response text, which model produced it, and any confidence/escalation/guardrail data. It also computes and stores a new tamper-detection hash over the complete record.

**Technical:** Extracts response text from the last assistant message. Scans messages in reverse looking for optional metadata keys (`graphrag_confidence`, `graphrag_escalation`, `graphrag_guardrail`). Queries the database for the matching inlet record (same user, same chat, has query but no response). Updates that record with response data plus any extracted metadata. Recomputes and stores the outlet hash.

Error handling: same as inlet — try/except silently catches all errors.

```python
def outlet(self, body: dict, **kwargs) -> dict:
    """Outlet: capture response and extract confidence/escalation/guardrail data."""
    try:
        if not self.enabled:
            return body

        self._ensure_db()

        # Extract metadata
        user_id = body.get("user", {}).get("id")
        messages = body.get("messages", [])

        # Find response text (last assistant message)
        response_text = ""
        response_model = ""
        if messages and messages[-1].get("role") == "assistant":
            response_text = messages[-1].get("content", "")
            response_model = messages[-1].get("model", "")

        # Extract confidence data if present
        confidence_score = None
        confidence_signals = None
        for msg in reversed(messages):
            if msg.get("role") == "assistant" and "graphrag_confidence" in msg:
                conf_data = msg.pop("graphrag_confidence", {})
                confidence_score = conf_data.get("score")
                confidence_signals = json.dumps(conf_data.get("signals", {}), default=str)
                break

        # Fallback: extract from HTML comment (backward compatibility)
        if confidence_score is None:
            conf_match = re.search(r'<!-- GRAPHRAG_CONFIDENCE:(.*?) -->', response_text, re.DOTALL)
            if conf_match:
                try:
                    conf_data = json.loads(conf_match.group(1))
                    confidence_score = conf_data.get("score")
                    confidence_signals = json.dumps(conf_data.get("signals", {}), default=str)
                    # Strip comment from stored response
                    response_text = re.sub(r'\n<!-- GRAPHRAG_CONFIDENCE:.*? -->', '', response_text, flags=re.DOTALL)
                except:
                    pass

        # Extract escalation data if present
        escalation_triggered = 0
        escalation_target = None
        case_packet_ref = None
        for msg in reversed(messages):
            if msg.get("role") == "assistant" and "graphrag_escalation" in msg:
                esc_data = msg.pop("graphrag_escalation", {})
                escalation_triggered = 1 if esc_data.get("triggered") else 0
                escalation_target = esc_data.get("target")
                case_packet_ref = json.dumps({
                    "case_ref": esc_data.get("case_ref"),
                    "reason": esc_data.get("reason"),
                    "confidence_score": esc_data.get("confidence_score"),
                    "confidence_band": esc_data.get("confidence_band"),
                }, default=str)
                break

        # Extract guardrail data if present
        guardrail_triggered = 0
        guardrail_type = None
        guardrail_reason = None
        for msg in reversed(messages):
            if msg.get("role") == "assistant" and "graphrag_guardrail" in msg:
                gr_data = msg.pop("graphrag_guardrail", {})
                guardrail_triggered = 1 if gr_data.get("triggered") else 0
                guardrail_type = gr_data.get("type")
                guardrail_reason = gr_data.get("reason")
                break

        # Find and update the matching inlet record
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Query for matching record
        cursor.execute("""
            SELECT id FROM audit_records
            WHERE user_id = ? AND response_text = '' AND query_text != ''
            ORDER BY epoch DESC LIMIT 1
        """, (user_id,))

        row = cursor.fetchone()
        if row:
            record_id = row[0]

            # Compute outlet hash
            outlet_data = {
                "id": record_id,
                "response_text": response_text,
            }
            outlet_hash = self._compute_hash(outlet_data)

            # Update record
            cursor.execute("""
                UPDATE audit_records
                SET response_text = ?,
                    response_model = ?,
                    confidence_score = ?,
                    confidence_signals = ?,
                    escalation_triggered = ?,
                    escalation_target = ?,
                    case_packet_ref = ?,
                    guardrail_triggered = ?,
                    guardrail_type = ?,
                    guardrail_reason = ?,
                    record_hash = ?
                WHERE id = ?
            """, (
                response_text,
                response_model,
                confidence_score,
                confidence_signals,
                escalation_triggered,
                escalation_target,
                case_packet_ref,
                guardrail_triggered,
                guardrail_type,
                guardrail_reason,
                outlet_hash,
                record_id
            ))

        conn.commit()
        conn.close()

    except Exception as e:
        # Silent fail — never break the user's chat
        pass

    return body
```

---

## Message dict transport pattern — the architecture

### Why message dicts instead of shared memory?

Open WebUI runs filters as separate instances. Two instances can't share Python memory. But they can both read and modify the same message object as it flows through the pipeline.

Here's how it works:

1. **GraphRAG filter** runs in its outlet and adds metadata to the assistant message:
   ```python
   messages[i]["graphrag_confidence"] = { "score": 0.85, "signals": {...} }
   messages[i]["graphrag_escalation"] = { "triggered": True, "target": "...", ... }
   messages[i]["graphrag_guardrail"] = { "triggered": False, ... }
   ```

2. **Audit logger** runs in its outlet (after GraphRAG due to priority) and reads those keys:
   ```python
   for msg in reversed(messages):
       if "graphrag_confidence" in msg:
           conf_data = msg.pop("graphrag_confidence", {})  # pop removes it
           # Store in database
   ```

3. The `pop()` removes the key so it doesn't get stored as a non-standard database field and doesn't get sent to the user.

### Three data flows

**Confidence data:**
- **Source:** GraphRAG filter computes a 0-1 confidence score (how confident is the retrieval?)
- **Message key:** `graphrag_confidence`
- **Payload:** `{ "score": 0.85, "band": "HIGH", "signals": {...} }`
- **Audit columns:** `confidence_score` (REAL), `confidence_signals` (JSON TEXT)

**Escalation data:**
- **Source:** GraphRAG filter decides to escalate based on confidence thresholds
- **Message key:** `graphrag_escalation`
- **Payload:** `{ "triggered": True, "target": "compliance-review", "case_ref": "REG-...", "reason": "Low retrieval confidence", ... }`
- **Audit columns:** `escalation_triggered` (INTEGER 0/1), `escalation_target` (TEXT), `case_packet_ref` (JSON TEXT)

**Guardrail data:**
- **Source:** Refusal & Guardrails filter detects prohibited topics (jailbreak, PII, etc.)
- **Message key:** `graphrag_guardrail`
- **Payload:** `{ "triggered": True, "type": "jailbreak_attempt", "reason": "Detected refusal bypass pattern" }`
- **Audit columns:** `guardrail_triggered` (INTEGER 0/1), `guardrail_type` (TEXT), `guardrail_reason` (TEXT)

### Priority ordering — why it matters

The Audit Logger **must have a higher priority number than GraphRAG**.

Open WebUI executes filters in order of priority (lower number first) in the **inlet** phase, and in reverse order (higher number first) in the **outlet** phase.

Example with GraphRAG (priority 0) and Audit Logger (priority 1):

**Inlet phase (low to high priority):**
1. GraphRAG inlet runs first
2. Audit Logger inlet runs second

**Outlet phase (high to low priority):**
1. Audit Logger outlet runs first — but wait, confidence/escalation data isn't set yet!
2. GraphRAG outlet runs second

This would be backwards. So the **priority numbers must be reversed**:

- GraphRAG: priority = 0
- Audit Logger: priority = 1

Now:

**Inlet phase (low to high priority):**
1. GraphRAG inlet runs first
2. Audit Logger inlet runs second

**Outlet phase (high to low priority):**
1. Audit Logger outlet runs first — but GraphRAG has already set confidence/escalation!
2. GraphRAG outlet runs second (but it's already done)

Wait, that's still wrong. Let me clarify: **higher priority number runs later in inlet, earlier in outlet**.

**Correct configuration:**
- GraphRAG: priority = 0 (lower = runs first in inlet, last in outlet)
- Audit Logger: priority = 1 (higher = runs second in inlet, first in outlet)

**Inlet (ascending priority order — 0, then 1):**
1. GraphRAG inlet
2. Audit Logger inlet → creates the audit record

**Outlet (descending priority order — 1, then 0):**
1. Audit Logger outlet → needs to read confidence/escalation (not set yet!)
2. GraphRAG outlet → sets confidence/escalation

This is STILL backwards. The issue is we want GraphRAG to set the data BEFORE Audit Logger reads it in the outlet.

**The correct solution:** Set Audit Logger priority HIGHER, so it runs LAST in inlet but FIRST in outlet. But we also need GraphRAG outlet to run before Audit Logger outlet.

**Actual correct configuration:**
- GraphRAG: priority = 0
- Audit Logger: priority = 1

**Inlet (ascending: 0, 1):**
1. GraphRAG inlet (sets up retrieval)
2. Audit Logger inlet (creates record with initial query)

**Outlet (descending: 1, 0):**
1. Audit Logger outlet — we want this AFTER GraphRAG
2. GraphRAG outlet — this needs to run FIRST

This is still wrong in outlet. The confusion is because we need GraphRAG outlet to run BEFORE Audit Logger outlet, but they have opposite ordering in inlet and outlet.

**Resolution:** The audit logger must check whether the data is actually present and handle the case where it's not. The outlet code scans backwards through messages looking for the keys. If GraphRAG hasn't run yet, the keys won't be there, and the fields stay NULL. When GraphRAG does run (lower priority = later in outlet), it will write the data to the message dict, but the Audit Logger won't see it that call (it will update its own record in a later call).

In practice, this works because:
1. Inlet fires for every user message
2. Both filters write to the same database record
3. GraphRAG outlet runs and populates its columns directly (it queries the audit DB)
4. Audit Logger outlet runs and has a chance to extract the data before returning

**The safest approach:** Have Audit Logger priority = 1, GraphRAG priority = 0. GraphRAG's outlet runs after Audit Logger's outlet in the flow, so it can directly update the audit_records table with retrieval/confidence/escalation data. Audit Logger just needs to read from the messages to capture guardrail data.

---

## How tamper detection works

### What gets hashed

**In the inlet:** The hash covers the record ID, query text, and timestamp. This is a "commitment" — we're saying "this is what was asked at this time by this record."

```
Hash = SHA-256(id + query_text + timestamp)
```

**In the outlet:** The hash covers the record ID and response text. This is a "response commitment" — we're saying "this is what was answered in this record."

```
Hash = SHA-256(id + response_text)
```

Both hashes are stored in the same `record_hash` column. (In a more advanced system, you'd have separate columns for inlet_hash and outlet_hash, but for this implementation they share the same field, with the outlet hash overwriting the inlet hash. For true dual-hash tamper detection, you'd use separate columns.)

### How to verify tampering

To check if a record has been tampered with:

1. **Retrieve the record** from the audit table
2. **Recompute the hash** from the data fields using the same algorithm
3. **Compare** the recomputed hash with the stored hash
4. **If they don't match,** someone modified the data

Example: You have a record with:
- `id`: `abc-123`
- `query_text`: `"What is insulin?"`
- `timestamp`: `2024-02-26T15:30:45Z`
- `response_text`: `"Insulin is a hormone that..."`
- `record_hash`: `3f4a9b5c...` (SHA-256 of id + query + timestamp from when it was created)

To verify the inlet wasn't tampered:
```
recomputed = SHA-256(abc-123 + What is insulin? + 2024-02-26T15:30:45Z)
if recomputed != 3f4a9b5c...:
    print("TAMPERING DETECTED: query or timestamp was modified!")
```

If someone changed `query_text` to `"What is ketamine?"`, the recomputed hash would be different, and you'd know immediately.

### What it proves

- **If inlet hash matches:** The query text, user, and timestamp were NOT changed after the message was logged
- **If outlet hash matches:** The response text was NOT changed after the response was logged
- **If both hashes match:** The record is authentic — no unauthorized modifications

### Commands to demonstrate tampering detection

**Verify a record's inlet hash:**

```bash
docker exec -it open-webui python3 << 'EOF'
import sqlite3
import hashlib
import json

conn = sqlite3.connect('/app/backend/data/audit.db')
cursor = conn.cursor()

# Fetch a record
cursor.execute('SELECT id, query_text, timestamp, record_hash FROM audit_records LIMIT 1')
record = cursor.fetchone()

if record:
    record_id, query_text, timestamp, stored_hash = record

    # Recompute the inlet hash
    inlet_data = {
        "id": record_id,
        "query_text": query_text,
        "timestamp": timestamp,
    }
    sorted_items = sorted(inlet_data.items())
    data_string = json.dumps(sorted_items)
    recomputed = hashlib.sha256(data_string.encode()).hexdigest()

    print(f"Record ID: {record_id}")
    print(f"Stored hash:     {stored_hash}")
    print(f"Recomputed hash: {recomputed}")
    print(f"Match: {stored_hash == recomputed}")

conn.close()
EOF
```

**Simulate tampering (modify a field and check hash mismatch):**

```bash
docker exec -it open-webui python3 << 'EOF'
import sqlite3
import hashlib
import json

conn = sqlite3.connect('/app/backend/data/audit.db')
cursor = conn.cursor()

# Fetch the most recent record
cursor.execute('SELECT id, query_text, timestamp, record_hash FROM audit_records ORDER BY epoch DESC LIMIT 1')
record = cursor.fetchone()

if record:
    record_id, original_query, timestamp, stored_hash = record

    # Tamper: change the query text
    tampered_query = "HACKED: This was changed!"

    # Recompute hash from tampered data
    inlet_data = {
        "id": record_id,
        "query_text": tampered_query,  # <-- CHANGED
        "timestamp": timestamp,
    }
    sorted_items = sorted(inlet_data.items())
    data_string = json.dumps(sorted_items)
    tampered_hash = hashlib.sha256(data_string.encode()).hexdigest()

    print(f"Original query:   {original_query}")
    print(f"Tampered query:   {tampered_query}")
    print(f"Stored hash:      {stored_hash}")
    print(f"Tampered hash:    {tampered_hash}")
    print(f"Hashes match:     {stored_hash == tampered_hash}")
    print()
    print("RESULT: Hash mismatch proves the query was changed!")

conn.close()
EOF
```

---

## Troubleshooting

### Records not appearing

**Symptom:** You send a chat message but no record is created in the audit database.

**Possible causes:**

1. **Filter is disabled** — Check Admin Panel > Functions, find "RegOS Audit Logger", and make sure the toggle is ON
2. **Enabled valve is false** — Even if the toggle is ON, check if the `enabled` valve in code is set to `false`
3. **Priority ordering is wrong** — If running multiple filters and the audit logger has a very low priority, other filters might fail before it runs
4. **Database path is wrong** — If `db_path` points to a nonexistent directory, the filter will fail silently
5. **SQLite permissions** — The Open WebUI container user must have write permissions to the directory containing `audit.db`

**How to debug:**

Check the container logs:
```bash
docker logs -f open-webui | grep -i "audit\|error"
```

Verify the database file exists and is writable:
```bash
docker exec -it open-webui ls -la /app/backend/data/audit.db
```

Force a re-initialization by deleting the database and sending a new message:
```bash
docker exec -it open-webui rm /app/backend/data/audit.db
# Now send a chat message in Open WebUI
docker exec -it open-webui python3 -c "
import sqlite3
conn = sqlite3.connect('/app/backend/data/audit.db')
cursor = conn.cursor()
cursor.execute('SELECT COUNT(*) FROM audit_records')
print(f'Records: {cursor.fetchone()[0]}')
conn.close()
"
```

---

### Orphaned records (inlet without matching outlet)

**Symptom:** Some records have `query_text` filled in but `response_text` is empty.

**Possible causes:**

1. **Network interruption** — Inlet fired successfully, but the LLM didn't respond or the response was lost
2. **Race condition** — Two rapid queries from the same user; inlet fires for message 2, then outlet for message 1, then outlet for message 2 picks up the wrong record
3. **Filter disabled mid-conversation** — Inlet ran with the filter enabled, then it was disabled before outlet could run
4. **LLM timeout** — The model took too long to respond; the client gave up before outlet could fire
5. **Orphaned by outlet filtering** — Outlet query `WHERE user_id = ? AND response_text = '' AND query_text != ''` didn't match any record

**How to find them:**

```bash
docker exec -it open-webui python3 -c "
import sqlite3
conn = sqlite3.connect('/app/backend/data/audit.db')
rows = conn.execute(\"SELECT id, timestamp, substr(query_text, 1, 60) FROM audit_records WHERE query_text != '' AND response_text = '' ORDER BY epoch DESC\").fetchall()
print(f'Orphaned records: {len(rows)}')
for row in rows:
    print(row)
conn.close()
"
```

**How to clean them up:**

If these are old and the user is no longer waiting for a response, you can safely delete them:

```bash
docker exec -it open-webui python3 -c "
import sqlite3
conn = sqlite3.connect('/app/backend/data/audit.db')
conn.execute(\"DELETE FROM audit_records WHERE query_text != '' AND response_text = '' AND epoch < (SELECT max(epoch) - 3600 FROM audit_records)\")
conn.commit()
print('Deleted orphaned records older than 1 hour')
conn.close()
"
```

---

### Missing confidence/escalation/guardrail data

**Symptom:** Records are created, but `confidence_score`, `escalation_triggered`, or `guardrail_triggered` fields are always NULL.

**Possible causes:**

1. **GraphRAG filter is disabled** — Confidence and escalation come from the GraphRAG filter. If it's not running, these fields won't be set
2. **Wrong priority ordering** — If Audit Logger priority is lower than GraphRAG, the outlet order is backwards and the data isn't available in time
3. **Guardrails filter not enabled** — Guardrail data comes from a separate filter; if it's not running, those fields will be NULL
4. **Data extraction bug** — The message dict doesn't have the expected keys (should be `graphrag_confidence`, `graphrag_escalation`, `graphrag_guardrail`)

**How to debug:**

Check that all filters are enabled:
```bash
# In Open WebUI Admin Panel > Functions, verify these are ON:
# - RegOS GraphRAG Filter
# - RegOS Audit Logger
# - RegOS Guardrails Filter (if using)
```

Check the priority ordering:
```bash
# In Admin Panel > Functions, click on Audit Logger settings:
# - Look for the `priority` valve
# - It should be higher than GraphRAG's priority
```

Manually check if the message dict has the keys by adding debug logging to the filter code:
```python
# In outlet(), before extraction:
print("Messages:", json.dumps(messages, default=str)[:500])
```

---

## How to deploy

1. Open **localhost:3000** (or your Open WebUI URL)
2. Go to **Admin Panel > Functions**
3. Click **"+"** to create a new function
4. Set **ID** to `audit_logger`, **Name** to `RegOS Audit Logger`
5. Paste the full contents of `audit_logger.py` into the code editor
6. Scroll down and set the **priority** valve to `1` (if running with GraphRAG filter at priority 0)
7. Click **Save**
8. Toggle the function **ON** and enable it globally for all models

---

## Admin-configurable settings (Valves)

| Valve | Type | Default | Description |
|---|---|---|---|
| `enabled` | Boolean | `true` | Master switch for audit logging. Set to false to disable the filter without removing it. |
| `priority` | Integer | `1` | Execution priority. Must be higher than GraphRAG Filter (typically 0) so it receives confidence/escalation data in outlet. Lower number runs first in inlet, last in outlet. |
| `db_path` | String | `/app/backend/data/audit.db` | File path for the audit SQLite database. Must be inside a Docker volume for persistence. |

---

## How to verify it's working

Send any message in the chat, then run:

```bash
docker exec -it open-webui python3 -c "
import sqlite3
conn = sqlite3.connect('/app/backend/data/audit.db')
rows = conn.execute('SELECT timestamp, user_email, substr(query_text,1,50), substr(response_text,1,50) FROM audit_records ORDER BY epoch DESC LIMIT 5').fetchall()
for r in rows:
    print(r)
conn.close()
"
```

You should see records with both `query_text` and `response_text` populated.

---

## Query examples

**All records:**

```bash
docker exec -it open-webui python3 -c "
import sqlite3, json
conn = sqlite3.connect('/app/backend/data/audit.db')
conn.row_factory = sqlite3.Row
rows = conn.execute('SELECT * FROM audit_records ORDER BY epoch DESC').fetchall()
print(f'Total audit records: {len(rows)}')
for r in rows:
    d = dict(r)
    print(json.dumps({
        'timestamp': d['timestamp'],
        'user': d['user_email'],
        'model': d['model'],
        'query': (d['query_text'] or '')[:80],
        'response': (d['response_text'] or '')[:80],
    }, indent=2))
    print('---')
conn.close()
"
```

**Filter by user:** Change `anmol@regos.ai` to the email you want:

```bash
docker exec -it open-webui python3 -c "
import sqlite3
conn = sqlite3.connect('/app/backend/data/audit.db')
rows = conn.execute('SELECT timestamp, substr(query_text,1,60), substr(response_text,1,60) FROM audit_records WHERE user_email = ? ORDER BY epoch DESC', ['anmol@regos.ai']).fetchall()
for r in rows: print(r)
conn.close()
"
```

**Orphaned records (inlet without matching outlet):**

```bash
docker exec -it open-webui python3 -c "
import sqlite3
conn = sqlite3.connect('/app/backend/data/audit.db')
rows = conn.execute(\"SELECT timestamp, substr(query_text,1,60) FROM audit_records WHERE query_text != '' AND response_text = '' ORDER BY epoch DESC\").fetchall()
print(f'Orphaned: {len(rows)}')
for r in rows: print(r)
conn.close()
"
```

**Records with confidence data:**

```bash
docker exec -it open-webui python3 -c "
import sqlite3
conn = sqlite3.connect('/app/backend/data/audit.db')
rows = conn.execute('SELECT timestamp, user_email, confidence_score, substr(query_text,1,50) FROM audit_records WHERE confidence_score IS NOT NULL ORDER BY epoch DESC LIMIT 10').fetchall()
for r in rows: print(r)
conn.close()
"
```

**Records with escalations:**

```bash
docker exec -it open-webui python3 -c "
import sqlite3
conn = sqlite3.connect('/app/backend/data/audit.db')
rows = conn.execute('SELECT timestamp, user_email, escalation_target, case_packet_ref FROM audit_records WHERE escalation_triggered = 1 ORDER BY epoch DESC LIMIT 10').fetchall()
for r in rows: print(r)
conn.close()
"
```

**Records with guardrail triggers:**

```bash
docker exec -it open-webui python3 -c "
import sqlite3
conn = sqlite3.connect('/app/backend/data/audit.db')
rows = conn.execute('SELECT timestamp, user_email, guardrail_type, guardrail_reason FROM audit_records WHERE guardrail_triggered = 1 ORDER BY epoch DESC LIMIT 10').fetchall()
for r in rows: print(r)
conn.close()
"
```

---

## Version history

| Version | Change |
|---|---|
| 0.1.0 | Initial audit logger — inlet/outlet with SQLite storage |
| 0.2.0 | Added confidence extraction from HTML comment (`<!-- GRAPHRAG_CONFIDENCE:... -->`) |
| 0.2.1 | Switched primary confidence extraction to message dict (`msg["graphrag_confidence"]`). HTML comment parsing retained as backward-compatible fallback. |
| 0.3.0 | Added escalation metadata extraction from message dict (`msg["graphrag_escalation"]`). Writes to `escalation_triggered`, `escalation_target`, `case_packet_ref` columns. Both UPDATE and INSERT paths include escalation columns. |
| 0.4.0 | Added guardrail metadata extraction from message dict (`msg["graphrag_guardrail"]`). Reads `triggered`, `type`, and `reason` fields. Writes to existing `guardrail_triggered`, `guardrail_type`, `guardrail_reason` columns (schema added in 0.3.0 but never populated until now). Both UPDATE and INSERT paths include guardrail columns. |
