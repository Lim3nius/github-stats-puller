#!/usr/bin/env python3
"""
Standalone script to run the backfill tool.
Usage: uv run backfill_events.py [--dry-run] [--events-dir PATH]
"""

from github_stats.backfill import main

if __name__ == "__main__":
    main()