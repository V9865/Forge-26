# LLM Provider Limits & Quotas (Free Tier)

This document records the official free-tier rate limits and quotas for configured LLM providers in EmberRoute (`LLM_CHAIN`). Limits should be verified against the official provider documentation and management consoles.

| Provider | Model | Requests / Min (RPM) | Tokens / Min (TPM) | Tokens / Day (TPD) | Source URL | Notes |
|:---|:---|:---:|:---:|:---:|:---|:---|
| **Groq** | `llama-3.1-8b-instant` | 30 | 6,000 | 500,000 | https://console.groq.com/docs/rate-limits | Primary planner model; ultra-low latency |
| **Groq** | `llama-3.3-70b-versatile` | 30 | 6,000 | 100,000 | https://console.groq.com/docs/rate-limits | Primary operational briefing model |
| **Ollama (Local)** | `qwen2.5:7b-instruct` | Unlimited | Unlimited | Unlimited | http://localhost:11434 | Local backup fallback; no rate limits |
| **Ollama (Local)** | `llama3.1:8b` | Unlimited | Unlimited | Unlimited | http://localhost:11434 | Local backup fallback; no rate limits |

## Budget Discipline Rules
1. **Daily Token Budget**: EmberRoute enforces `LLM_DAILY_TOKEN_BUDGET=100000` across all pipeline and orchestrator executions. Once reached, calls raise `LLMUnavailable("budget")` and fall back gracefully to deterministic planning and template briefings without making outbound API requests.
2. **Context Compactness**: All tool outputs passed to the LLM are compacted to $\le 300$ tokens (`compact()` helper). No raw GeoJSON geometries or coordinate arrays are ever sent to the LLM.
3. **Execution Caps**: Tool calling is hard-capped at 5 invocations per planning cycle. Repeated tool signatures trigger immediate fallback to deterministic simulation.

