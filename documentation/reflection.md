# Reflection

Concise notes on lessons learned and where this project is headed next.

---

## Challenges and solutions (selected)

- Challenge: Fragile scrapers broke when sites changed markup.
  - Solution: Added per-source URL-shape heuristics (path depth, slug length) with graceful fallbacks and opportunistic JSON-LD parsing to reduce selector dependence.
- Challenge: Pure semantic search struggled with entity-heavy queries (tickers, project names).
  - Solution: Implemented hybrid search (keyword + vector) and made embedding model configurable to trade accuracy for latency as needed.
- Challenge: Index freshness required restarts after cron ingestion.
  - Solution: Introduced dynamic index reloading based on Qdrant metrics so the service refreshes results without server restarts.
- Challenge: Simple moderation under-blocked at api boundary allowing for some innapropriate but polite queries to reach LLM.
  - Solution: Layered moderation with prompt engineering inside the LLM system message.
- Challenge: Small local models were fast but sometimes missed instructions and weakened RAG grounding.
  - Solution: Defaulted to stronger mid-size models (`llama3.1:8b`, `qwen2.5:14b`) with a fallback to smaller models when latency is critical.


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
