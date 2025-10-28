# 🚀 Crypto News Agent

An AI-powered semantic search engine for cryptocurrency news with streaming LLM responses, source citations, and OpenAI moderation.

## ✨ Features

- **Multi-Source Ingestion**: Automatically scrapes from CoinTelegraph, DL News, and The Defiant
- **Semantic Search**: FAISS vector database with sentence-transformers for intelligent similarity search
- **Streaming LLM Responses**: Real-time GPT-4 responses with source citations
- **Content Moderation**: Powered by OpenAI's Moderation API for safe queries
- **Web Search Comparison**: Compare database results with OpenAI's web search
- **Automated Refresh**: Cron job integration (default: every 6 hours)
- **Modern UI**: React + Vite frontend with dark theme

## 🛠️ Tech Stack

**Backend:** FastAPI, SQLAlchemy, FAISS, sentence-transformers, httpx, BeautifulSoup, OpenAI API (LLM, web search & moderation), SQLite

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
python scripts/ingest_news.py --max-articles-per-source 30
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

- `POST /api/ask` - Semantic search (`{"question": "..."}`)
- `POST /api/ask-websearch` - Web search
- `GET /api/index-stats` - Database statistics
- `GET /api/health` - Health check
- Interactive docs: `http://localhost:8000/docs`

## ⏰ Automated Data Refresh

Make executable and add to crontab:

```bash
chmod +x cron_refresh.sh
crontab -e

# Add: 0 */6 * * * /path/to/crypto-news-agent/cron_refresh.sh
```

Manual refresh: `python backend/scripts/ingest_news.py --max-articles-per-source 25`

Monitor logs: `tail -f backend/logs/cron.log`

## 🔍 How It Works

### Semantic Search Pipeline

1. User Question → OpenAI Moderation API check
2. Generate 384-dim embedding
3. FAISS search for top-K similar articles
4. Optional date filtering & score conversion
5. Build prompt with article context
6. Stream LLM response with citations

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

## 🚧 Obstacles Overcome

**Web Scraping Challenges:**

- Fixed 403 errors by adding proper User-Agent headers to bypass bot detection
- Updated CSS selectors for DL News (`story-container` divs) and The Defiant (DOM tree walking for headings)
- Resolved NoneType errors with proper type checking in selector lambdas
- CoinTelegraph still in progress (complex HTML structure)

**Key Learnings:** Modern news sites use dynamic class names (Tailwind), requiring DOM inspection over assumptions. User-Agent headers are essential for scraper success.

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
