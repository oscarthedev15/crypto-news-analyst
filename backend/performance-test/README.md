# Testing Guide

Comprehensive performance and security test suite for the crypto news agent.

## Quick Start

```bash
# From backend directory
python performance-test/test_crypto_news_agent.py
```

**Prerequisites:**
- Backend server running on `http://localhost:8000`
- Search index built (`python scripts/ingest_news.py`)

## Test Suite

### 1. Concurrent Request Handling
- 10 simultaneous requests with various crypto questions
- Measures response times, success rates, system stability

### 2. Error Handling
- Invalid inputs (empty, too long, missing fields)
- Malformed requests, invalid endpoints
- No-results scenarios
- Validates proper HTTP status codes (422, 404, 405)

### 3. Content Moderation
- Threatening/inappropriate content detection
- Verifies blocking (400) or safe handling (200 with no articles)
- Logs responses to validate unhelpful/safe content

## Results

Results are saved to `results/test_results.json` with:
- Overall success rates and performance metrics
- Response time statistics (min, max, mean, median, std dev)
- Error breakdown by type
- Detailed results for each test case

## Output

The test suite provides:
- Console output with formatted results
- Error explanations for failed tests
- Sources count and response previews for moderation tests
- JSON file with detailed results

## Troubleshooting

```bash
# Check server is running
curl http://localhost:8000/api/health

# Build search index if needed
python scripts/ingest_news.py
```
