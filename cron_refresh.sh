#!/bin/bash

# Crypto News Agent - Cron Refresh Script
# This script should be run periodically (e.g., every 6 hours) to refresh the article database
# Usage: Add to crontab with: 0 */6 * * * /path/to/cron_refresh.sh

# Set script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR/backend"

# Activate Python virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Create logs directory if it doesn't exist
mkdir -p logs

# Run the ingestion script
python scripts/ingest_news.py --max-articles-per-source 25 >> logs/cron.log 2>&1

# Log completion
echo "---" >> logs/cron.log
echo "Refresh completed at $(date)" >> logs/cron.log
echo "" >> logs/cron.log
