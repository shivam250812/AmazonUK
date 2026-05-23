#!/bin/bash

# This script runs the pipeline in a "fast test" mode.
# It requests 5 keywords from the AI, scrapes only the first page for each,
# and limits the scraping to exactly 4 products per keyword.

export MAX_PRODUCTS=4
export SEARCH_PAGES=1

echo "========================================================="
echo "   RUNNING FAST TEST (5 Keywords, 4 Products Each)"
echo "========================================================="

# Activate the virtual environment so Playwright is found
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Run the pipeline asking for exactly 5 keywords
python3 run_pipeline.py --count 5 --pages 1
