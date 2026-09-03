# SerpApi Track Compliance

SerpApi is a core runtime dependency, not a decorative integration.

The live decision packet is built from SerpApi's structured Google Search results. Without live sponsor evidence, the application cannot claim the accepted sponsor path.

Final live acceptance requires:

```yaml
serpapi_integration: live
answer_mode: ollama_grounded
gate_state: READY_FOR_HUMAN | REVIEW_REQUIRED
```

A visible Human decision is recorded separately, and no action is automatically executed.
