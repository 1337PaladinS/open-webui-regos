# Inventory

This folder contains a structured inventory of the entire `open-webui-regos` directory — classifying every component as stock Open WebUI, custom RegOS work, or a modified stock file.

## For Humans

Start with **REGOS_MAP.md** to understand what RegOS adds on top of Open WebUI. If you need to audit which stock files were changed, read **SOURCE_PATCHES.md**.

## For LLMs

1. **Parse `MANIFEST.yaml`** — programmatic index of every file/folder with type labels (`baseline`, `custom`, `modified`, `ephemeral`). Use this to instantly classify any file.
2. **Read `BASELINE.md`** — understand what stock Open WebUI 0.8.1 looks like so you never confuse upstream code with custom work.
3. **Read `REGOS_MAP.md`** — understand all custom RegOS components organized by functional area.
4. **Read `SOURCE_PATCHES.md`** — understand exactly which stock files were modified, what changed, and how the installer applies patches.

## Files

| File                      | Purpose                                              |
| ------------------------- | ---------------------------------------------------- |
| `MANIFEST.yaml`           | Master index --- every file/folder classified        |
| `BASELINE.md`             | Stock Open WebUI 0.8.1 reference                     |
| `REGOS_MAP.md`            | All custom RegOS work, by functional area            |
| `SOURCE_PATCHES.md`       | Modified stock files --- 15 patches across 13 files  |
| `REMOVAL_CANDIDATES.md`   | Files/dirs flagged for deletion (pending approval)   |
| `STRATEGY.md`             | How this inventory was built (methodology)           |

## Key Facts

- **Open WebUI version:** 0.8.1
- **Inventory date:** 2026-03-20
- **Stock files modified:** 13 (via 15 surgical patches)
- **New files injected into stock tree:** 3 Svelte components
- **RegOS features:** 12 (audit logging, GraphRAG, confidence, formatting, sources panel, disclaimers, escalation, threshold eval, SCADA, APAS bridge, guardrails, integrated threshold eval)
- **Middleware status:** Fully stock (6 modifications attempted and rolled back)
