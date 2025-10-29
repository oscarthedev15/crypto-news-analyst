# 🚀 Crypto News Agent

An AI-powered semantic search engine for cryptocurrency news with streaming LLM responses, source citations, and content moderation.

## ✨ Features

- **Multi-Source Ingestion**: Automatically scrapes from CoinTelegraph, DL News, and The Defiant
- **Hybrid Search**: Combines semantic (FAISS embeddings) + keyword matching (BM25) for optimal results
- **Semantic Search**: FAISS vector database with sentence-transformers for intelligent similarity search
- **Keyword Boosting**: Adjustable keyword matching weight (30% default) for brand names and specific terms
- **Streaming LLM Responses**: Real-time AI responses with source citations
- **Multiple LLM Providers**:
  - **Ollama** (default, free, local) - Uses Llama 3.1 8B, Qwen 2.5, or any Ollama model
  - **OpenAI** (optional, paid) - GPT-4o-mini with cloud-based inference
  - **Auto-detection**: Tries Ollama first, falls back to OpenAI if configured
- **Content Moderation**: Powered by Detoxify for detecting toxic, inappropriate, or violent content
- **Automated Refresh**: Cron job integration with dynamic index reloading (configurable: every minute by default)
- **Modern UI**: React + Vite frontend with dark theme

## 🛠️ Tech Stack

**Backend:** FastAPI, SQLAlchemy, FAISS, BM25 (rank-bm25), sentence-transformers, httpx, BeautifulSoup, OpenAI API (LLM, optional), Detoxify (moderation), SQLite

**Frontend:** React 18, Vite, Modern CSS

**Infrastructure:** Python 3.9+, Node.js 18+, Cron

## 📋 Prerequisites

- Python 3.9+
- Node.js 18+
- **LLM Provider (choose one or both):**
  - **[Ollama](https://ollama.com)** (recommended, free, local) - OR -
  - **OpenAI API key** (optional, paid, cloud-based)
- ~2GB disk space (+ 4-7GB per Ollama model if using local LLM)

## 🚀 Quick Start

### 1. Choose Your LLM Provider

#### Option A: Ollama (Recommended - FREE! 🎉)

**Install Ollama:**

```bash
# macOS / Linux
curl -fsSL https://ollama.com/install.sh | sh

# Or download from: https://ollama.com/download
```

**Pull a model:**

```bash
# Recommended: Best balance of speed and quality (~4.7GB)
ollama pull llama3.1:8b

# Fastest/Lightest option (~2GB, but may give less relevant answers)
ollama pull llama3.2:3b

# Best quality option (~9GB, excellent at following instructions)
ollama pull qwen2.5:14b

# Or use Mistral
ollama pull mistral:7b
```

**Start Ollama (usually runs automatically):**

```bash
ollama serve
```

That's it! The system will auto-detect Ollama and use it by default.

#### Option B: OpenAI (Optional)

If you prefer OpenAI or want it as a fallback:

1. Get an API key from [platform.openai.com](https://platform.openai.com)
2. Add to `.env` file: `OPENAI_API_KEY=sk-...`

**Smart Fallback:** The system automatically tries Ollama first, then falls back to OpenAI if configured.

### 2. Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Setup environment (optional - only needed for OpenAI)
cp .env.example .env
# Edit .env and add: OPENAI_API_KEY=sk-... (if using OpenAI)
```

### 3. Initial Data Ingestion

```bash
# Fetch and index articles (takes 5-10 minutes on first run)
# This will build both FAISS (semantic) and BM25 (keyword) indexes
python scripts/ingest_news.py --max-articles-per-source 30
```

**Note:** If upgrading from a version without hybrid search, rebuild indexes via API:

```bash
curl -X POST http://localhost:8000/api/rebuild-index
```

### 4. Start Backend

```bash
uvicorn app.main:app --reload --port 8000
```

You should see:

```
✓ Database initialized
✓ FAISS index loaded successfully
✅ Initialized Ollama with model: llama3.1:8b  # or OpenAI if configured
✓ API running at http://localhost:8000/docs
```

**Verify your LLM provider:**

```bash
curl http://localhost:8000/api/health
# Should show: {"status":"healthy","llm_provider":{"provider":"ollama"...}}
```

### 5. Frontend Setup (New Terminal)

```bash
cd frontend
npm install
npm run dev
```

Access at `http://localhost:5173`

## 📖 Usage

### Web UI

1. **Ask Questions**: "What's the latest Bitcoin news?", "Explain Ethereum Layer 2", etc.
2. **View Results**: Source cards with metadata, streaming LLM response with citations

### API Endpoints

- `POST /api/ask` - Hybrid search with chat history support:
  - Headers: `X-Session-Id` (optional): Session ID for conversation context
  - Parameters:
    - `question` (required): User's question
    - `recent_only` (optional, default: true): Filter to last 30 days
    - `top_k` (optional, default: 5): Number of results
    - `keyword_boost` (optional, default: 0.3): Keyword weight (0.0-1.0)
- `DELETE /api/session/{session_id}` - Clear chat session
- `GET /api/sessions/stats` - Active session statistics (debug)
- `GET /api/index-stats` - Database statistics
- `POST /api/rebuild-index` - Rebuild search indexes
- `GET /api/health` - Health check
- Interactive docs: `http://localhost:8000/docs`

## ⏰ Automated Data Refresh

### One-Command Setup

Set up automated article ingestion with a single command:

```bash
# Default: every minute
./cron_refresh.sh --setup

# Every 5 minutes
./cron_refresh.sh --setup 5

# Every 10 minutes
./cron_refresh.sh --setup 10

# Every 30 minutes
./cron_refresh.sh --setup 30

# Every hour
./cron_refresh.sh --setup hourly

# Daily at midnight
./cron_refresh.sh --setup daily
```

This will:

- ✅ Install a cron job with your chosen schedule
- ✅ Automatically fetch new crypto articles from all sources
- ✅ Rebuild the vector database (FAISS + BM25 indexes)
- ✅ Server picks up changes **dynamically without restart**

### Change Schedule

Simply re-run setup with a different interval:

```bash
./cron_refresh.sh --setup 10  # Change to every 10 minutes
```

### Monitor Activity

Watch logs in real-time:

```bash
tail -f backend/logs/cron.log
```

### Manual Operations

Run ingestion manually:

```bash
./cron_refresh.sh
# or
python backend/scripts/ingest_news.py --max-articles-per-source 25
```

View installed cron jobs:

```bash
crontab -l
```

Remove cron job:

```bash
crontab -r
```

### How Dynamic Reloading Works

The server automatically detects when the cron job updates the indexes:

1. Cron job runs on your configured schedule and rebuilds indexes
2. Server checks index file modification times before each search
3. If indexes are newer, they're automatically reloaded
4. **No server restart required** - new articles appear immediately!

## 🔍 How It Works

### Hybrid Search Pipeline

1. **User Question** → Detoxify moderation check (detects toxic/inappropriate content)
2. **Semantic Search**: Generate 384-dim embedding → FAISS vector similarity search
3. **Keyword Search**: Tokenize query → BM25 scoring for exact term matching
4. **Hybrid Ranking**: Combine scores (default: 70% semantic + 30% keyword)
5. **Filtering**: Date filtering & relevance threshold
6. **LLM Context**: Build prompt with top-ranked articles
7. **Stream Response**: GPT-4 streaming with source citations

### Why Hybrid Search?

Pure semantic search struggles with:

- **Brand names**: "pump.fun" vs "pumpfun"
- **Specific entities**: Company names, protocols, ticker symbols
- **Exact phrases**: Technical terms that need literal matching

**Hybrid search** solves this by combining:

- **Semantic similarity** (70%): Understands context and meaning
- **Keyword matching** (30%): Prioritizes exact term matches

You can adjust the `keyword_boost` parameter (0.0-1.0) via API for different use cases.

## 🔐 Environment Variables

Create a `.env` file in the `backend/` directory:

```bash
# LLM Provider Settings
LLM_PROVIDER=auto  # Options: "auto" (default), "ollama", "openai"

# Ollama Settings (if using local LLM)
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b  # Recommended: llama3.1:8b, qwen2.5:14b, llama3.2:3b (fast)
OLLAMA_TEMPERATURE=0.1  # Lower = more focused responses (better for staying on topic)
OLLAMA_MAX_TOKENS=1000

# OpenAI Settings (optional, only needed if using OpenAI)
OPENAI_API_KEY=sk-...  # Your OpenAI API key
OPENAI_MODEL=gpt-4o-mini
OPENAI_TEMPERATURE=0.5
OPENAI_MAX_TOKENS=800

# Database & Search
DATABASE_URL=sqlite:///./news_articles.db
EMBEDDING_MODEL=all-MiniLM-L6-v2
TOP_K_ARTICLES=5
SIMILARITY_THRESHOLD=0.3
```

**LLM_PROVIDER Options:**

- `auto` (default): Smart detection with automatic fallback
  - First checks if Ollama is running (health check to http://localhost:11434)
  - If Ollama is running → uses Ollama ✅
  - If Ollama is NOT running → checks for OpenAI API key
  - If OpenAI key exists → uses OpenAI ✅
  - If neither available → shows error with setup instructions
- `ollama`: Force local Ollama only (will error if not running)
- `openai`: Force OpenAI only (will error if API key not set)

## ⚡ Performance

- Database search: ~500ms
- Scraping: ~2-3 sec per article
- Initial index: 10-30 seconds

## 🐛 Troubleshooting

**LLM Provider Issues:**

- **"No LLM provider available"**: Install Ollama or set `OPENAI_API_KEY` in `.env`
- **"Ollama not running"**: Start Ollama with `ollama serve` or check if it's already running at `http://localhost:11434`
- **"OpenAI API error"**: Check API key in `.env` file or switch to Ollama
- **Check current provider**: `curl http://localhost:8000/api/health` to see which LLM is being used

**Ollama Specific:**

- **Model not found**: Pull the model first: `ollama pull llama3.1:8b`
- **Check available models**: Run `ollama list` to see installed models
- **Irrelevant answers / sources not showing**: The smaller `llama3.2:3b` model struggles with instruction following. Upgrade to:
  - `llama3.1:8b` (recommended, ~4.7GB): Much better at citing sources and staying on topic
  - `qwen2.5:14b` (~9GB): Excellent at instruction following and RAG tasks
  - `qwen2.5:32b` (~20GB): Best quality but needs significant RAM
- **Slow responses**: This is normal for larger models; `llama3.1:8b` is 2-3x slower than `3b` but gives much better results
- **Memory issues**: Ollama needs 8GB+ RAM; close other applications or use a smaller model

**General Issues:**

- **FAISS index not found:** Run `python backend/scripts/ingest_news.py`
- **No articles found:** Run ingestion with more articles: `--max-articles-per-source 50`
- **Frontend can't connect:** Ensure backend is running: `curl http://localhost:8000/api/health`
- **Hybrid search not working:** Rebuild indexes: `POST http://localhost:8000/api/rebuild-index`

## 🚧 Obstacles Overcome

**Web Scraping Challenges:**

- Fixed 403 errors by adding proper User-Agent headers to bypass bot detection
- Updated CSS selectors for DL News (`story-container` divs) and The Defiant (DOM tree walking for headings)
- Resolved NoneType errors with proper type checking in selector lambdas
- CoinTelegraph still in progress (complex HTML structure)

**Key Learnings:** Modern news sites use dynamic class names (Tailwind), requiring DOM inspection over assumptions. User-Agent headers are essential for scraper success.

**Semantic Search Limitations:**

The initial implementation used pure semantic search (FAISS with `all-MiniLM-L6-v2` embeddings), which had critical limitations:

- **Poor performance on brand names**: Query "pump.fun" returned low relevance (42%) even when exact matches existed
- **Weak exact-term matching**: Embeddings capture _meaning_ not _keywords_, so specific entities (protocols, companies, tickers) scored poorly
- **Context drift**: Articles without the exact term but "semantically similar" ranked higher than exact matches
- **Low confidence scores**: Most results scored 30-45% relevance, making it hard to trust top results

**Real Example:** Searching "tell me about pump.fun" returned article "Pumpfun Acquires Memecoin Trading Terminal Padre" at only 42% relevance, while a generic memecoin article with no mention scored 40%.

**Solution - Hybrid Search:**

Implemented BM25 keyword matching alongside semantic search:

- **70% semantic** (FAISS embeddings): Captures context and meaning
- **30% keyword** (BM25): Prioritizes exact term matches
- **Configurable**: Adjust `keyword_boost` parameter (0.0-1.0) per query

This is standard in production search systems (Elasticsearch, Pinecone, Weaviate all use hybrid approaches). Pure semantic search alone is rarely optimal for real-world applications.

**Key Learnings:** Semantic embeddings are powerful but insufficient for queries with specific entities. Hybrid search (semantic + keyword) is essential for production-grade search, especially in domains with technical terminology and brand names like crypto.

## 🏗️ Design Considerations

### Chat History & Session Management

**Current Implementation (MVP):**

- **In-memory storage**: Sessions stored in Python dictionary with 60-minute auto-expiration
- **Session isolation**: Each browser tab gets unique session ID (stored in sessionStorage)
- **Conversation context**: LLM receives full chat history for contextual responses
- **Automatic cleanup**: Expired sessions removed periodically to prevent memory bloat

**Trade-offs:**

- ✅ **Pros**: Zero infrastructure, instant reads/writes, simple implementation
- ❌ **Cons**: Lost on server restart, not suitable for multi-server deployments

**Production Recommendations:**

For production deployments, consider these alternatives based on scale:

1. **SQLite Database** (Single server, < 100 concurrent users)
   - Add `ChatHistory` table to existing SQLite database
   - Persist conversations across restarts
   - Easy to implement, minimal overhead
2. **Redis** (Multi-server, < 10K concurrent users)
   - Fast in-memory cache with persistence
   - TTL-based expiration built-in
   - Supports distributed deployments
3. **Blob Storage + Database** (Large scale, > 10K concurrent users)
   - **Metadata**: Store session metadata in PostgreSQL/MySQL
   - **Messages**: Store full conversation history in S3/Azure Blob/GCS
   - **Benefits**: Cost-effective for long conversations, unlimited scalability
   - **Pattern**: Keep recent messages in cache (Redis), archive to blob storage

**Recommended Architecture for Production:**

```
PostgreSQL (metadata) + Redis (hot cache) + S3 (cold storage)
  ├── Active sessions: Redis (60min TTL)
  ├── Session metadata: PostgreSQL (user_id, created_at, last_accessed)
  └── Full history: S3 (gzipped JSON, partitioned by date)
```

This hybrid approach balances performance, cost, and scalability for production chat applications.

## 📚 Future Enhancements

- **Sources:** Add CoinDesk, Crypto Media, The Block
- **Features:** Sentiment analysis, historical trend visualizations, fact-checking
- **Search:** Advanced filters (date range, categories, tags)
- **Platforms:** Mobile app (React Native), browser extension
- **Internationalization:** Multi-language support

## 📄 License

MIT License - Feel free to use for personal or commercial projects

## 🙏 Credits

Built with [FastAPI](https://fastapi.tiangolo.com/), [FAISS](https://github.com/facebookresearch/faiss), [Sentence Transformers](https://www.sbert.net/), [OpenAI](https://openai.com/api/), and news from CoinTelegraph, DL News, The Defiant.

---

Made with ❤️ for crypto enthusiasts
