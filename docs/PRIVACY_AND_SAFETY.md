# Privacy and Safety

- `SERPAPI_API_KEY` is read from a process environment variable and is not rendered in the UI or proof payload.
- The Windows runner requests the key interactively and removes it from its session during cleanup.
- The app uses local Ollama for synthesis; the evidence packet is not sent to a second cloud AI provider by this code.
- Test fixture mode is explicitly separate from live sponsor proof.
- Human approval records a receipt but does not execute the proposed action.
- No private Diamond OS databases, private user records, runtime source archives, or local account data are included in the public candidate.
