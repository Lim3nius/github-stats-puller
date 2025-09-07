import threading
import time
import uvicorn
import os
import sys
from datetime import datetime, timezone
from dotenv import load_dotenv
from loguru import logger

from github_stats.client import GitHubEventsClient
from github_stats.server import app


def setup_logging():
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logger.remove()
    logger.add(sys.stdout, level=log_level)


def run_client_polling():
    """Run the GitHub events client polling in a separate thread"""
    logger.info("Starting GitHub events polling client thread")
    client = GitHubEventsClient()

    # Check if we need to wait before first poll
    if client.state.next_poll_time_ts:
        now = datetime.now(timezone.utc)
        if client.state.next_poll_time_ts > now:
            wait_time_sec = (client.state.next_poll_time_ts - now).total_seconds()
            logger.info(f"Waiting {wait_time_sec:.1f} seconds until next poll time")
            time.sleep(wait_time_sec)

    while True:
        try:
            events = client.poll_events()
            if events:
                logger.info(f"Client downloaded {len(events)} events")
            time.sleep(client.state.poll_interval_sec)
        except Exception as e:
            logger.error(f"Error in client polling: {e}")
            time.sleep(60)  # Wait 1 minute before retrying


def run_server():
    """Run the FastAPI server"""
    logger.info("Starting FastAPI server")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_config=None)


def main():
    """Main entry point that runs both client and server"""
    load_dotenv("gh.env")
    setup_logging()

    logger.info("Starting GitHub Events API with polling client")

    # Start client polling in a daemon thread
    client_thread = threading.Thread(target=run_client_polling, daemon=True)
    client_thread.start()

    # Run the server in the main thread
    run_server()


if __name__ == "__main__":
    main()
