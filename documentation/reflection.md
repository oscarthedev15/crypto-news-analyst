# Reflection

Concise notes on lessons learned and where this project is headed next.

---

## Lessons learned (selected)

- Scraping reliability requires URL-shape heuristics per source (path depth, slug length) with graceful fallbacks; explore JSON-LD where available to reduce selector fragility.
- Hybrid search improves relevance over pure semantic for entity-heavy queries; keep embeddings configurable to trade accuracy vs. latency.
- Dynamic index reloading via Qdrant metrics avoids server restarts and keeps results fresh with cron ingestion.
- Layered safety (transformers moderation + LLM guardrails) reduces harmful outputs; occasional double-triggering is acceptable for safety.
- Model size matters: small local models answer fast but may miss instructions; `llama3.1:8b` or `qwen2.5:14b` yield better RAG grounding.

---

## Future roadmap

### Near term

- Persistent chat (Redis) using the existing session interface.
- Scraping upgrades: JSON-LD parsing for CoinTelegraph; add CoinDesk and The Block.
- Optional larger embedding model for accuracy (configurable).
- Search UX: filters for date range and source; lightweight UI controls.
- Safety and reliability: moderation tuning and per-session rate limits.
- Query quality: LLM-assisted query rewriting and selective tool calling.

### Later (scale and robustness)

- PostgreSQL for concurrent writes and richer queries.
- Background workers (Celery) for ingestion/retries.
- Centralized metrics/logging with simple dashboards.
- Vector storage evolution or shared storage if local files outgrow bounds.
- Augment with live web search for time-sensitive questions.
- Agentic orchestration for multi-step planning and evidence verification.

---

Last updated: October 30, 2025
