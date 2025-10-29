# 🚀 Crypto News Agent

An AI-powered semantic search engine for cryptocurrency news with streaming LLM responses, source citations, and OpenAI moderation.

## ✨ Features

- **Multi-Source Ingestion**: Automatically scrapes from CoinTelegraph, DL News, and The Defiant
- **Hybrid Search**: Combines semantic (FAISS embeddings) + keyword matching (BM25) for optimal results
- **Semantic Search**: FAISS vector database with sentence-transformers for intelligent similarity search
- **Keyword Boosting**: Adjustable keyword matching weight (30% default) for brand names and specific terms
- **Streaming LLM Responses**: Real-time GPT-4 responses with source citations
- **Content Moderation**: Powered by OpenAI's Moderation API for safe queries
- **Web Search Comparison**: Compare database results with OpenAI's web search
- **Automated Refresh**: Cron job integration with dynamic index reloading (configurable: every minute by default)
- **Modern UI**: React + Vite frontend with dark theme

## 🛠️ Tech Stack

**Backend:** FastAPI, SQLAlchemy, FAISS, BM25 (rank-bm25), sentence-transformers, httpx, BeautifulSoup, OpenAI API (LLM, web search & moderation), SQLite

**Frontend:** React 18, Vite, Modern CSS

**Infrastructure:** Python 3.9+, Node.js 18+, Cron

## 📋 Prerequisites

- Python 3.9+
- Node.js 18+
- OpenAI API key
- ~2GB disk space

## 🚀 Quick Start

### 1. Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Setup environment
cp .env.example .env
# Edit .env and add: OPENAI_API_KEY=sk_...
```

### 2. Initial Data Ingestion

```bash
# Fetch and index articles (takes 5-10 minutes on first run)
# This will build both FAISS (semantic) and BM25 (keyword) indexes
python scripts/ingest_news.py --max-articles-per-source 30
```

**Note:** If upgrading from a version without hybrid search, rebuild indexes via API:

```bash
curl -X POST http://localhost:8000/api/rebuild-index
```

### 3. Start Backend

```bash
uvicorn app.main:app --reload --port 8000
```

You should see: `✓ Database initialized ✓ FAISS index loaded successfully ✓ API running at http://localhost:8000/docs`

### 4. Frontend Setup (New Terminal)

```bash
cd frontend
npm install
npm run dev
```

Access at `http://localhost:5173`

## 📖 Usage

### Web UI

1. **Select Mode**: 🗄️ Database Search (fast, ~500ms) or 🌐 Web Search (live, 2-5s)
2. **Ask Questions**: "What's the latest Bitcoin news?", "Explain Ethereum Layer 2", etc.
3. **View Results**: Source cards with metadata, streaming LLM response with citations

### API Endpoints

- `POST /api/ask` - Hybrid search with chat history support:
  - Headers: `X-Session-Id` (optional): Session ID for conversation context
  - Parameters:
    - `question` (required): User's question
    - `recent_only` (optional, default: true): Filter to last 30 days
    - `top_k` (optional, default: 5): Number of results
    - `keyword_boost` (optional, default: 0.3): Keyword weight (0.0-1.0)
- `POST /api/ask-websearch` - Web search (OpenAI)
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

1. **User Question** → OpenAI Moderation API check
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

### Web Search Pipeline

1. User Question → Moderation check
2. OpenAI GPT-4 with web search
3. Streaming response
4. URL citation extraction

## 🔐 Environment Variables

**Required:** `OPENAI_API_KEY` - Your OpenAI API key

**Optional:**

- `DATABASE_URL` - Default: `sqlite:///./news_articles.db`
- `EMBEDDING_MODEL` - Default: `all-MiniLM-L6-v2`
- `TOP_K_ARTICLES` - Default: 5
- `SIMILARITY_THRESHOLD` - Default: 0.3

## ⚡ Performance

- Database search: ~500ms
- Web search: 2-5 seconds
- Scraping: ~2-3 sec per article
- Initial index: 10-30 seconds

## 🐛 Troubleshooting

**FAISS index not found:** Run `python backend/scripts/ingest_news.py`

**OpenAI API error:** Check API key in `.env` file

**No articles found:** Run ingestion with more articles: `--max-articles-per-source 50`

**Frontend can't connect:** Ensure backend is running: `curl http://localhost:8000/health`

**Hybrid search not working:** Rebuild indexes: `POST http://localhost:8000/api/rebuild-index`

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
