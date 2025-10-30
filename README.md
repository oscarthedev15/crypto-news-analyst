# 🚀 Crypto News Agent

AI-powered semantic search engine for cryptocurrency news with streaming LLM responses, source citations, and content moderation.

## What is this?

A local-first RAG (Retrieval-Augmented Generation) system that:

- **Scrapes** crypto news from CoinTelegraph, DL News, and The Defiant
- **Indexes** articles using hybrid search (semantic + keyword matching)
- **Answers** questions with AI-generated responses backed by real sources
- **Streams** responses in real-time with proper citations
- **Runs locally** with free LLM (Ollama) or OpenAI

**Key Features:**

- 🔍 Hybrid search (FAISS + BM25) for accurate entity matching
- 🤖 Choice of LLM: Ollama (free, local) or OpenAI (cloud)
- 📰 Auto-refresh with cron jobs (no server restart needed)
- 💬 Conversational context with session management
- 🛡️ Content moderation with Detoxify
- ⚡ Streaming responses via Server-Sent Events

**📖 Documentation**

- [Architecture](./architecture.md) - System design and data flows
- [Development Notes](./reflection.md) - MVP decisions, obstacles, and future improvements

---

## 📋 Prerequisites

- Python 3.9+
- Node.js 18+
- **LLM Provider** (choose one):
  - [Ollama](https://ollama.com) (recommended, free, local) OR
  - OpenAI API key (optional, paid)
- ~2GB disk space (+ 4-7GB per Ollama model)

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

### 3. Initial Data Ingestion

```bash
# Fetch and index articles (5-10 minutes)
python scripts/ingest_news.py --max-articles-per-source 30
```

---

### 4. Start Backend

```bash
uvicorn app.main:app --reload --port 8000
```

Verify LLM provider:

```bash
curl http://localhost:8000/api/health
# Should show: {"status":"healthy","llm_provider":{"provider":"ollama"...}}
```

---

### 5. Frontend Setup

```bash
# New terminal
cd frontend
npm install
npm run dev
```

Access at `http://localhost:5173`

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
- ✅ Rebuilds search indexes (FAISS + BM25)
- ✅ Server picks up changes **without restart**

Monitor logs:

```bash
tail -f backend/logs/cron.log
```

---

## 📖 Usage

### Web UI

1. Ask questions: "What's the latest Bitcoin news?", "Explain Ethereum Layer 2"
2. View results: Source cards with metadata, streaming AI responses with citations

### API Endpoints

- `POST /api/ask` - Hybrid search with streaming LLM response
  - Headers: `X-Session-Id` (optional)
  - Parameters: `question`, `recent_only`, `top_k`, `keyword_boost`
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

- **"FAISS index not found"**: Run `python backend/scripts/ingest_news.py`
- **No articles found**: Increase count: `--max-articles-per-source 50`
- **Hybrid search not working**: Rebuild: `POST http://localhost:8000/api/rebuild-index`

**Quality Issues:**

- **Irrelevant answers**: Upgrade to `llama3.1:8b` or `qwen2.5:14b` (smaller models struggle with instructions)
- **Slow responses**: Normal for larger models; trade-off for better quality

---

## 🛠️ Tech Stack

**Backend:** FastAPI, SQLAlchemy, FAISS, BM25, sentence-transformers, LangChain, Detoxify, SQLite

**Frontend:** React 18, Vite, Server-Sent Events

**Infrastructure:** Python 3.9+, Node.js 18+, Cron, Ollama/OpenAI

---

## 📄 License

MIT License

---

Made with ❤️ for crypto enthusiasts
