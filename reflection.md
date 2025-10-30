# Reflection

Short notes on decisions, constraints, and what changes next.

---

## MVP Choices (Local-first, zero-cost, fast iteration)

- Local LLM via Ollama by default; OpenAI optional fallback
- Non-persistent chat history (in-memory, 60m TTL)
- Small, fast embedding model: `all-MiniLM-L6-v2` (384-dim)
  - Why: ~50MB, fast on CPU (~100–200ms/query), strong general performance for news Q&A without heavy RAM/VRAM requirements.
- SQLite database (single file, simple ops)
- Qdrant vector database for semantic search
  - Why Qdrant: Lightweight, in-process vector search with excellent latency, no external service, easy save/load for local dev.
- Cron-based ingestion; simple bash script + logs

These choices minimize setup, keep everything runnable on a laptop, and enable rapid changes without billing or extra services.

---

## Key Obstacles (and quick fixes)

- Site-specific scraping layouts and URL patterns
  - Each site used different URL shapes for real articles vs index/marketing pages; I had to manually inspect and note patterns (e.g., date segments, section prefixes) to reliably filter to real articles.
  - Patterns implemented in code:
    - CoinTelegraph: paths start with `/news/`, exclude `/magazine/`, `/learn/`, `/price-indexes/`, `/people/`, `/category/`; require at least 2 segments and a long final slug.
    - DLNews: paths start with `/articles/` and must be `/articles/{category}/{long-article-slug}` (3+ segments); avoids category-only pages.
    - The Defiant: paths start with `/news/` and must be `/news/{category}/{long-article-slug}`; excludes `/podcasts-and-videos/`.
  - Heuristics help: path depth checks and minimum slug length reduce false positives; there is a generic fallback when a site has no explicit pattern.
  - CoinTelegraph: investigating whether JSON-LD structured data is consistently available; if so, use that rather than fragile HTML selectors.
- Pure semantic search performed worse on exact-entity queries
  - Semantic search with appropriate query embedding and filtering improved relevance.
- Staying fresh without restarts
  - Cron periodically crawls sources and pulls new articles shortly after posting; index auto-reloads when changes are detected, so the backend picks up new content without restarts.
- Moderation and guardrails
  - Detoxify is effective for rejecting harmful input at the API boundary, but occasionally the downstream LLM guardrail still triggers; both layers help keep responses safe.
- Small local models and instruction-following
  - Recommend `llama3.1:8b` or `qwen2.5:14b` for better RAG behavior.

---

## Near-Term Improvements

- Persistent chat (Redis) with the same session interface
- CoinTelegraph: investigate JSON-LD structured data; add CoinDesk/The Block scrapers
- Optional larger embedding model for accuracy (configurable)
- Basic filters: date range, source; lightweight UI controls
- Moderation tweaks and per-session rate limits
- LLM fine-tuning on crypto-specific datasets: Train or adapt the base model (e.g., via LoRA) on curated crypto news articles, whitepapers, and domain terminology to improve understanding of technical concepts (DeFi protocols, tokenomics, blockchain mechanics), entity recognition (project names, tickers, exchanges), and temporal reasoning (market cycles, event impacts). Could leverage accumulated scraped articles as training data or use specialized crypto NLP datasets.

---

## Later (when scaling matters)

- PostgreSQL for concurrent writes and richer queries
- Background workers (Celery) for ingestion/retries
- Centralized metrics/logs; simple dashboards
- Vector DB or shared storage if indexes outgrow local files
- Cross-reference live web search (DuckDuckGo, OpenAI web search) to supplement scraped articles with real-time results
- Agentic orchestration to enhance/refine user queries before sending to the LLM (query decomposition, intent extraction, multi-step planning)

---

Last updated: October 29, 2025
