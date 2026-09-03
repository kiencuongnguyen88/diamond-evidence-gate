# Demo Script — 2–4 minutes

## 1. Problem

Explain that AI can recommend production changes using stale context. Diamond Evidence Gate requires live evidence before a consequential recommendation reaches the Human.

## 2. Enter a concrete decision

Recommended final-demo case:

**Decision question**

> Should our team migrate one bounded agent workflow from the OpenAI Assistants API to the Responses API this week?

**Proposed action**

> Migrate one non-critical workflow to the Responses API after verifying the current Assistants API retirement status, migration guidance, and compatibility risks.

Leave Trusted domains blank for the first live run so source diversity remains visible.

## 3. Build the live brief

Show:

- `SerpApi: live`
- `Mode: ollama_grounded`
- source/domain count
- `Gate: READY_FOR_HUMAN` or, if evidence is insufficient, `REVIEW_REQUIRED`
- numbered evidence and the AI's cited rationale/uncertainties.

Do not hide a `REVIEW_REQUIRED` state. Fail-closed behavior is part of the product.

## 4. Human Gate

Explain that the AI cannot make the final decision. Select **HOLD** for the demo if material uncertainty remains; otherwise make the Human decision that matches the evidence.

Show the receipt and `action_executed=false`, then download the receipt.

## 5. Close

Summarize the product as:

> Live evidence first. Grounded AI second. Human authority third. Proof last.
