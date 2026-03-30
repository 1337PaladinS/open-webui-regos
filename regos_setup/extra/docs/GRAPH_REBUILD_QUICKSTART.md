# Graph Rebuild — Quick Start

> **OBSOLETE**: This file described the v1 LLM extraction approach (18 batches of Claude Code entity extraction). It was replaced by the Fixed Entity Architecture (FEA) pipeline in Session 6. See `RegOS_Graph_Rebuild_Strategy_v2.docx` for the current strategy and `.claude/worktrees/serene-mclaren/fea_pipeline.py` for the pipeline code.

## Current approach: FEA Pipeline

The graph is now built using `fea_pipeline.py` with the `--output-mode direct` flag:

```bash
python fea_pipeline.py \
  --output-mode direct \
  --neo4j-uri "neo4j+s://<YOUR_AURA_URI>" \
  --neo4j-user "neo4j" \
  --neo4j-password "<YOUR_PASSWORD>" \
  --api-key "<YOUR_OPENROUTER_KEY>" \
  --api-base "https://openrouter.ai/api/v1" \
  --embedding-model "openai/text-embedding-3-small" \
  --llm-model "openai/gpt-4o-mini" \
  --concepts-file ../../concepts.json \
  --sections-dir "../../Chapter 24/" \
  --similarity-threshold 0.35
```

This produces: 30 Concept nodes, 144 Section nodes, ~5,600 RELATES_TO edges, 151 thresholds, 15 penalties, 2,363 obligations, 12 roles, 37 standards, 170 cross-references, 90 hierarchy edges. ~30 LLM calls total (HyDE generation only).
