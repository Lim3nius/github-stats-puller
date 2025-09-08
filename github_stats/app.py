import threading
import time
import uvicorn
import os
import sys
from dotenv import load_dotenv
from loguru import logger

from github_stats.client import GitHubEventsClient
from github_stats.server import app
from github_stats.stores import ClickHouseConfig, configure_database_service


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
        client.sleep_till_poll_time()

    while True:
        try:
            events = client.poll_events()
            if events:
                logger.info(f"Client downloaded {len(events)} events")
            client.sleep_till_poll_time()
        except Exception as e:
            logger.error(f"Error in client polling: {e}")
            time.sleep(60)  # Wait 1 minute before retrying


def run_server():
    """Run the FastAPI server"""
    logger.info("Starting FastAPI server on http://0.0.0.0:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_config=None, access_log=False)


def main():
    """Main entry point that runs both client and server"""
    load_dotenv("gh.env")
    setup_logging()

    # Configure database backend
    db_backend = os.getenv("DATABASE_BACKEND", "memory").lower()
    logger.info(f"Configuring database backend: {db_backend}")

    if db_backend == "clickhouse":
        clickhouse_config: ClickHouseConfig = {
            "host": os.getenv("CLICKHOUSE_HOST", "localhost"),
            "port": int(os.getenv("CLICKHOUSE_PORT", "9000")),
            "username": os.getenv("CLICKHOUSE_USER", "github_user"),
            "password": os.getenv("CLICKHOUSE_PASSWORD", "github_pass"),
            "database": os.getenv("CLICKHOUSE_DATABASE", "github_stats"),
        }
        configure_database_service("clickhouse", clickhouse_config)
    else:
        configure_database_service("memory")

    logger.info("Starting GitHub Events API with polling client")

    # Start client polling in a daemon thread
    client_thread = threading.Thread(target=run_client_polling, daemon=True)
    client_thread.start()

    # Run the server in the main thread
    run_server()


if __name__ == "__main__":
    main()
