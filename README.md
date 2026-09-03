# Diamond Evidence Gate

Diamond Evidence Gate is a local-first, Human-gated AI decision workspace built for the DevNetwork API + Cloud + AI Hackathon 2026 SerpApi challenge.

It turns live structured web evidence into a bounded AI recommendation, then stops at a visible Human Gate. The AI may recommend; only the Human may approve, hold, or reject. No downstream action is executed automatically.

## Why it exists

AI recommendations can be confident while their information is stale. Diamond Evidence Gate changes the order of operations:

```text
live SerpApi evidence
→ deterministic normalization + quality flags
→ local grounded AI brief
→ READY_FOR_HUMAN | REVIEW_REQUIRED
→ visible Human Gate
→ APPROVE | HOLD | REJECT
→ hash-bound decision receipt
```

## Core components

- **SerpApi Google Search API** — live structured web evidence.
- **Python standard library** — HTTP server, API client, evidence normalization, gate and receipt logic.
- **Ollama + qwen3:1.7b** — local grounded decision synthesis.
- **Human Gate** — records a Human decision only; it never auto-executes the proposed action.

No Python package installation is required for the app itself.

## Run on Windows

1. Have a SerpApi API key available privately.
2. Have Ollama and `qwen3:1.7b` available locally.
3. Run:

```text
run_live_demo_capture.cmd
```

The runner keeps the SerpApi key process-scoped, validates the local model path, reuses a proven compatible Ollama service when possible, chooses free local ports without killing unrelated processes, and opens the browser only after live machine acceptance passes.

## Manual run

The app reads these environment variables:

```text
SERPAPI_API_KEY
OLLAMA_URL
OLLAMA_MODEL
PORT            # optional, default 8765
```

Then run:

```bash
python app.py
```

Open the local URL shown by the server.

## Human authority boundary

The application can:

- retrieve live evidence;
- normalize and flag evidence;
- generate a grounded AI recommendation;
- prepare an evidence packet;
- record a Human decision receipt.

The application cannot:

- silently approve a proposal;
- execute the proposed action;
- publish, deploy, or mutate an external system.

Every decision receipt contains:

```yaml
action_executed: false
authority_boundary: HUMAN_DECISION_RECORDED_ONLY
```

## Tests

```bash
python -m unittest discover -s tests -v
```

The tests cover the SerpApi URL contract, result normalization, Human-Gate fail-closed behavior, local-AI fallback, no-auto-execution boundary, and the browser-visible `max=5` acceptance path.

## Live proof status

A real Windows run on 2026-09-02 reached:

```yaml
serpapi_integration: live
answer_mode: ollama_grounded
result_count: 5
unique_domain_count: 5
gate_state: READY_FOR_HUMAN
secret_material_in_proof: false
```

The raw private API key is not stored in this repository.

## Project structure

```text
app.py                         local HTTP app + gate/receipt API
src/serpapi_client.py          SerpApi live search client
src/evidence_engine.py         normalization and quality flags
src/ai_provider.py             local Ollama grounded synthesis
static/index.html              Human-visible decision workspace
tests/                         contract and safety tests
fixtures/                      test-only SerpApi fixture
run_live_demo_capture.*        bounded Windows demo runner
docs/                          architecture, safety, proof and demo notes
```

## Privacy and safety

See `docs/PRIVACY_AND_SAFETY.md`. No private Diamond OS databases, private P1/P2 records, API keys, or local runtime archives are included.
