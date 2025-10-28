# Crypto News Agent - Performance & Security Testing

This directory contains comprehensive testing tools for the crypto news agent's core capabilities.

## Quick Start

From the backend directory, run:
```bash
python performance-test/test_crypto_news_agent.py
```

## What Gets Tested

### 1. Concurrent Request Handling
- **Tests**: 10 simultaneous requests with different crypto questions
- **Measures**: Response times, success rates, system stability
- **Success Criteria**: >95% success rate, <2s average response time

### 2. Error Handling
- **Tests**: Invalid inputs, missing fields, malformed requests, no results scenarios
- **Measures**: Proper HTTP status codes, graceful error responses
- **Success Criteria**: Appropriate error codes (422, 404) for invalid inputs

### 3. Content Moderation
- **Tests**: Offensive/questionable content detection
- **Measures**: Blocking inappropriate requests, safe content filtering
- **Success Criteria**: Blocks or sanitizes potentially harmful content

## Prerequisites

1. **Server Running**: Ensure the crypto news agent backend is running on `http://localhost:8000`
2. **Dependencies Installed**: Install testing dependencies:
   ```bash
   pip install aiohttp requests
   ```
3. **Data Available**: Ensure the search index is built with some articles:
   ```bash
   python scripts/ingest_news.py
   ```

## Test Results

Results are automatically saved to `results/test_results.json` with:
- Overall success rates and performance metrics
- Response time statistics (min, max, mean, median)
- Error breakdown by type
- Detailed results for each test case

## Interpreting Results

### Success Rate
- **≥95%**: Excellent performance
- **90-95%**: Good, minor issues
- **<90%**: Needs improvement

### Response Times
- **<1s**: Excellent
- **1-2s**: Good
- **2-5s**: Acceptable
- **>5s**: Slow

### Error Handling
- **422**: Validation errors (expected for invalid inputs)
- **404**: Not found (expected for invalid endpoints)
- **400**: Content moderation blocks (expected for offensive content)
- **500**: Server errors (unexpected, indicates problems)

## Troubleshooting

### Server Not Responding
```bash
# Check if server is running
curl http://localhost:8000/api/health

# Start server if needed
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### No Search Index
```bash
# Build the search index
python scripts/ingest_news.py
```

### Test Dependencies Missing
```bash
# Install dependencies
pip install aiohttp requests
```

## Performance Benchmarks

Expected performance metrics:
- **Concurrent Users**: 10+ simultaneous requests
- **Response Time**: <2 seconds average
- **Success Rate**: >95%
- **Error Handling**: Proper status codes for all error cases
- **Content Moderation**: Blocks inappropriate content

## Continuous Testing

### Automated Testing
Add to your CI/CD pipeline:
```bash
python performance-test/test_crypto_news_agent.py
```

### Monitoring
Monitor these metrics in production:
- Response time percentiles
- Error rates by type
- Concurrent request capacity
- Content moderation effectiveness

## File Structure

```
performance-test/
├── test_crypto_news_agent.py    # Main test suite
└── results/                     # Test results directory
    └── test_results.json        # Detailed test results
```

The test suite is designed to be comprehensive yet focused, testing the three critical aspects of your crypto news agent: concurrent request handling, error management, and content safety.
