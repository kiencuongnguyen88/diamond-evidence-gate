# Architecture

```text
Human decision question + proposed action
        ↓
SerpApi live Google Search
        ↓
normalize evidence + diversity/freshness flags
        ↓
local Ollama qwen3:1.7b grounded brief
        ↓
READY_FOR_HUMAN | REVIEW_REQUIRED
        ↓
visible Human Gate
        ↓
APPROVE | HOLD | REJECT
        ↓
hash-bound receipt; action_executed=false
```

## Authority invariant

```text
AI:    retrieve → normalize → recommend → prepare gate
Human:                                  approve | hold | reject
Execution: none
```

`APPROVE` fails closed unless `gate_state=READY_FOR_HUMAN`.

The decision API records a receipt only. No subprocess, shell, deployment, publish, database mutation, or external action path exists in `app.py`.
