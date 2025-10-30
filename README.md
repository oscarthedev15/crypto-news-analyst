# 🚀 Crypto News Agent

AI-powered semantic search engine for cryptocurrency news with streaming LLM responses, source citations, and content moderation.

## What is this?

A local-first RAG (Retrieval-Augmented Generation) **agent** that:

- **Scrapes** crypto news from CoinTelegraph, DL News, and The Defiant
- **Indexes** articles using semantic search
- **Intelligently decides** when to search vs. use chat history (agent pattern)
- **Answers** questions with AI-generated responses backed by real sources
- **Prioritizes** article information over general LLM knowledge
- **Streams** responses in real-time with proper citations
- **Runs locally** with free LLM (Ollama) or OpenAI

**Key Features:**

- 🤖 **RAG Agent**: Intelligently decides when to search vs. use chat history
- 🔍 Semantic search for accurate article retrieval (only when needed)
- 📝 Query improvement: Auto-expands abbreviations for better search
- 📰 Auto-refresh with cron jobs (no server restart needed)
- 💬 Conversational context with session management
- 🎯 Article-first responses: Prioritizes retrieved articles over general knowledge
- 🛡️ Content moderation with transformers pipeline (unitary/toxic-bert)
- ⚡ Streaming responses via Server-Sent Events

**📖 Documentation**

- [Architecture](./architecture.md) - System design and data flows
- [Development Notes](./reflection.md) - MVP decisions, obstacles, and future improvements
- [Testing Guide](./backend/performance-test/README.md) - Performance and security test suite

---

## 📋 Prerequisites

- Python 3.9+
- Node.js 18+
- **LLM Provider** (choose one):
  - [Ollama](https://ollama.com) (recommended, free, local) OR
  - OpenAI API key (optional, paid)
- ~2GB disk space (+ 4-7GB per Ollama model)

> Note on embeddings: The backend uses Hugging Face sentence-transformers for embeddings by default. Internet access is required on first run to download the embedding model, and whenever a new model is used. To run offline, ensure the model is already cached locally (e.g., run once online), or switch to a local embedding model via Ollama and update `EMBEDDING_MODEL` accordingly.

---

## 🚀 Setup Instructions

### 1. Choose Your LLM Provider

#### Option A: Ollama (Recommended - FREE)

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull a model (choose one)
ollama pull llama3.1:8b     # Recommended (~4.7GB)
ollama pull llama3.2:3b     # Faster/lighter (~2GB)
ollama pull qwen2.5:14b     # Best quality (~9GB)

# Start Ollama (usually auto-starts)
ollama serve
```

#### Option B: OpenAI (Optional)

1. Get API key from [platform.openai.com](https://platform.openai.com)
2. Add to `.env`: `OPENAI_API_KEY=sk-...`

**Note:** System auto-detects Ollama first, falls back to OpenAI if configured.

---

### 2. Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Optional: Setup OpenAI
cp .env.example .env
# Edit .env and add: OPENAI_API_KEY=sk-... (if using OpenAI)
```

---

### 3. Start Qdrant (Vector DB)

```bash
# From project root of this repo
docker compose up -d qdrant

# Verify Qdrant is healthy
curl http://localhost:6333/
# Expect JSON with version information
```

Qdrant configuration used by the backend:

- URL: `http://localhost:6333` (see `backend/app/config.py`)
- Docker config: see `docker-compose.yml` (`qdrant` service, ports 6333/6334)

If you prefer running without Docker, install and run Qdrant natively and ensure it listens on port 6333 or update `QDRANT_URL` in `backend/.env` accordingly.

---

### 4. Initial Data Ingestion

```bash
# Fetch and index articles (5-10 minutes)
python scripts/ingest_news.py --max-articles-per-source 30
```

---

### 5. Start Backend

```bash
uvicorn app.main:app --reload --port 8000
```

Verify LLM provider:

```bash
curl http://localhost:8000/api/health
# Should show: {"status":"healthy","llm_provider":{"provider":"ollama"...}}
```

---

### 6. Frontend Setup

```bash
# New terminal
cd frontend
npm install
npm run dev
```

Access at `http://localhost:5173`

---

## 🧪 Testing

Run the comprehensive performance and security test suite:

```bash
cd backend
python performance-test/test_crypto_news_agent.py
```

**Tests include:**

- ✅ Concurrent request handling (10 simultaneous requests)
- ✅ Error handling (invalid inputs, missing fields, edge cases)
- ✅ Content moderation (threatening/inappropriate content detection)

Results are saved to `backend/performance-test/results/test_results.json`.

See [Testing Guide](./backend/performance-test/README.md) for detailed documentation.

---

## ⏰ Automated Data Refresh

Set up cron job to auto-refresh articles:

```bash
# Default: every minute
./cron_refresh.sh --setup

# Other options
./cron_refresh.sh --setup 5       # Every 5 minutes
./cron_refresh.sh --setup 10      # Every 10 minutes
./cron_refresh.sh --setup hourly  # Every hour
./cron_refresh.sh --setup daily   # Daily at midnight
```

**Features:**

- ✅ Auto-fetches new articles from all sources
- ✅ Rebuilds search indexes
- ✅ Server picks up changes **without restart**

Monitor logs:

```bash
tail -f backend/logs/cron.log
```

---

## 🤖 RAG Agent Architecture

The system uses an **intelligent agent** that decides when to search vs. use chat history:

- **Agent Decision**: Heuristic-based rules prevent unnecessary searches
  - Skips search for: greetings, conversation questions ("what did I ask?"), follow-ups
  - Performs search for: new information queries about crypto news
- **Query Improvement**: Auto-expands abbreviations (BTC → Bitcoin) for better search
- **Article-First**: System prioritizes retrieved articles over general LLM knowledge
- **Smart Caching**: Uses chat history when context is available, avoiding redundant searches

**Future Expansions:**

- LLM-based tool calling (let LLM decide when to search)
- Multi-step reasoning with iterative searches
- Query rewriting based on chat history
- Source verification across multiple articles

See [Architecture](./architecture.md) for detailed flow diagrams.

---

## 📖 Usage

### Web UI

1. Ask questions: "What's the latest Bitcoin news?", "Explain Ethereum Layer 2"
2. View results: Source cards with metadata, streaming AI responses with citations
3. **Agent Behavior**: Notice it skips search for follow-ups like "what did I just ask?"

### API Endpoints

- `POST /api/ask` - Semantic search with streaming LLM response
  - Headers: `X-Session-Id` (optional)
  - Parameters: `question`, `top_k`
- `DELETE /api/session/{session_id}` - Clear chat session
- `GET /api/index-stats` - Database statistics
- `POST /api/rebuild-index` - Manual index rebuild
- `GET /api/health` - Health check
- Interactive docs: `http://localhost:8000/docs`

---

## 🔐 Environment Variables

Create `.env` in `backend/` directory:

```bash
# LLM Provider
LLM_PROVIDER=auto  # Options: auto, ollama, openai

# Ollama Settings
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b
OLLAMA_TEMPERATURE=0.1
OLLAMA_MAX_TOKENS=1000

# OpenAI Settings (optional)
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
OPENAI_TEMPERATURE=0.5
OPENAI_MAX_TOKENS=800

# Database & Search
DATABASE_URL=sqlite:///./news_articles.db
EMBEDDING_MODEL=all-MiniLM-L6-v2
TOP_K_ARTICLES=5
SIMILARITY_THRESHOLD=0.3
```

---

## 🐛 Troubleshooting

**LLM Issues:**

- **"No LLM provider available"**: Install Ollama or set `OPENAI_API_KEY`
- **"Ollama not running"**: Run `ollama serve`
- **"Model not found"**: Run `ollama pull llama3.1:8b`
- **Check provider**: `curl http://localhost:8000/api/health`

**Search Issues:**

- **"Search index not found"**: Run `python backend/scripts/ingest_news.py`
- **No articles found**: Increase count: `--max-articles-per-source 50`
- **Search not working**: Rebuild: `POST http://localhost:8000/api/rebuild-index`

**Quality Issues:**

- **Irrelevant answers**: Upgrade to `llama3.1:8b` or `qwen2.5:14b` (smaller models struggle with instructions)
- **Slow responses**: Normal for larger models; trade-off for better quality

---

## 📦 Storage Architecture

**Data Storage:**

- **SQLite Database** (`backend/news_articles.db`): Article metadata (title, content, URL, dates, source)
- **Qdrant Vector Database** (`qdrant-storage/`): Vector embeddings + metadata for semantic search
  - Created automatically when Docker container starts
  - Stores dense vectors (embeddings), sparse vectors (BM25), and article metadata
  - Single source of truth for search indexes - no separate mapping files needed

**Key Design Decision:** All search-related data (vectors, metadata, article IDs) is stored in Qdrant. This eliminates the need for separate pickle files or mapping directories, simplifying the architecture and ensuring consistency.

---

## 🛠️ Tech Stack

**Backend:** FastAPI, SQLAlchemy, Qdrant, sentence-transformers, LangChain, transformers (unitary/toxic-bert), SQLite

**Frontend:** React 18, Vite, Server-Sent Events

**Infrastructure:** Python 3.9+, Node.js 18+, Cron, Ollama/OpenAI

---

## 📄 License

MIT License

---

Made with ❤️ for crypto enthusiasts
