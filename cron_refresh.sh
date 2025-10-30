#!/bin/bash

# Crypto News Agent - All-in-One Script
# 
# Usage:
#   ./cron_refresh.sh --setup [INTERVAL]    Install cron job with schedule
#   ./cron_refresh.sh                       Run the ingestion manually (or called by cron)
#
# Examples:
#   ./cron_refresh.sh --setup           Use default (every minute)
#   ./cron_refresh.sh --setup 5         Every 5 minutes
#   ./cron_refresh.sh --setup 10        Every 10 minutes
#   ./cron_refresh.sh --setup 30        Every 30 minutes
#   ./cron_refresh.sh --setup hourly    Every hour
#   ./cron_refresh.sh --setup daily     Daily at midnight
#
# This script will:
#   • Fetch new crypto articles
#   • Update the vector database (Qdrant index)
#   • Server will auto-pick up changes (no restart needed!)

# ============================================================================
# DEFAULT CONFIGURATION: Cron Schedule
# ============================================================================
# Default schedule if no argument provided to --setup
# Format: minute hour day month weekday
# ============================================================================
DEFAULT_CRON_SCHEDULE="* * * * *"

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
SCRIPT_PATH="$SCRIPT_DIR/$(basename "$0")"

# Check if --setup flag was passed
if [ "$1" == "--setup" ]; then
    # Parse the interval argument
    INTERVAL="$2"
    
    # Set cron schedule based on interval
    if [ -z "$INTERVAL" ]; then
        # No interval provided, use default
        CRON_SCHEDULE="$DEFAULT_CRON_SCHEDULE"
        DESCRIPTION="every minute (default)"
    elif [ "$INTERVAL" == "hourly" ]; then
        CRON_SCHEDULE="0 * * * *"
        DESCRIPTION="every hour"
    elif [ "$INTERVAL" == "daily" ]; then
        CRON_SCHEDULE="0 0 * * *"
        DESCRIPTION="daily at midnight"
    elif [[ "$INTERVAL" =~ ^[0-9]+$ ]]; then
        # Numeric interval in minutes
        if [ "$INTERVAL" -eq 60 ]; then
            CRON_SCHEDULE="0 * * * *"
            DESCRIPTION="every hour"
        elif [ "$INTERVAL" -ge 60 ]; then
            # Convert to hours
            HOURS=$((INTERVAL / 60))
            if [ $((INTERVAL % 60)) -eq 0 ]; then
                CRON_SCHEDULE="0 */$HOURS * * *"
                DESCRIPTION="every $HOURS hours"
            else
                echo "Error: Intervals >= 60 minutes must be divisible by 60 (or use 'hourly')"
                exit 1
            fi
        else
            CRON_SCHEDULE="*/$INTERVAL * * * *"
            DESCRIPTION="every $INTERVAL minutes"
        fi
    else
        echo "Error: Invalid interval '$INTERVAL'"
        echo ""
        echo "Valid options:"
        echo "  <number>    Minutes (1-59, or multiples of 60 for hours)"
        echo "  hourly      Every hour"
        echo "  daily       Daily at midnight"
        echo ""
        echo "Examples:"
        echo "  ./cron_refresh.sh --setup 5      # Every 5 minutes"
        echo "  ./cron_refresh.sh --setup 30     # Every 30 minutes"
        echo "  ./cron_refresh.sh --setup hourly # Every hour"
        exit 1
    fi
    echo "================================"
    echo "Crypto News Agent - Cron Setup"
    echo "================================"
    echo ""
    echo "Schedule: $DESCRIPTION"
    echo "Cron:     $CRON_SCHEDULE"
    echo ""
    
    # Make sure this script is executable
    chmod +x "$SCRIPT_PATH"
    
    # Check if cron job already exists
    if crontab -l 2>/dev/null | grep -q "$SCRIPT_PATH"; then
        echo "⚠️  Cron job already exists! Updating schedule..."
        # Remove old cron job for this script
        crontab -l 2>/dev/null | grep -v "$SCRIPT_PATH" | crontab -
    fi
    
    echo "Installing cron job..."
    
    # Add cron job (preserving existing crontab)
    (crontab -l 2>/dev/null || true; echo "$CRON_SCHEDULE $SCRIPT_PATH") | crontab -
    
    echo "✓ Cron job installed successfully!"
    echo ""
    echo "Installed cron job:"
    crontab -l | grep "$SCRIPT_PATH"
    
    echo ""
    echo "================================"
    echo "Setup Complete!"
    echo "================================"
    echo ""
    echo "The job will run on schedule and:"
    echo "  • Fetch new crypto articles"
    echo "  • Update the vector database (Qdrant index)"
    echo "  • Log output to: backend/logs/cron.log"
    echo ""
    echo "To change the schedule, run setup again with desired interval:"
    echo "  ./cron_refresh.sh --setup 5      # Every 5 minutes"
    echo "  ./cron_refresh.sh --setup 10     # Every 10 minutes"
    echo "  ./cron_refresh.sh --setup hourly # Every hour"
    echo "  ./cron_refresh.sh --setup daily  # Daily at midnight"
    echo ""
    echo "Useful commands:"
    echo "  Watch logs:      tail -f backend/logs/cron.log"
    echo "  Run manually:    ./cron_refresh.sh"
    echo "  List cron jobs:  crontab -l"
    echo "  Remove cron:     crontab -r"
    echo ""
    exit 0
fi

# Normal execution: Run the ingestion
cd "$SCRIPT_DIR/backend"

# Activate Python virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Create logs directory if it doesn't exist
mkdir -p logs

# Clear the log file at the start of each run (only keep latest run)
> logs/cron.log

# Run the ingestion script
python scripts/ingest_news.py --max-articles-per-source 25 >> logs/cron.log 2>&1

# Log completion
echo "---" >> logs/cron.log
echo "Refresh completed at $(date)" >> logs/cron.log
echo "" >> logs/cron.log
