import os
import sys
import time
from loguru import logger
from github_stats.client import GitHubEventsClient
from dotenv import load_dotenv


def setup_logging():
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logger.remove()
    logger.add(sys.stdout, level=log_level)


def main_loop():
    load_dotenv("gh.env")

    setup_logging()
    logger.info("Starting GitHub Events polling client")

    client = GitHubEventsClient()

    while True:
        events = client.poll_events()
        if events:
            logger.info(f"Downloaded {len(events)} events")

        time.sleep(client.state.poll_interval_sec)


def main():
    main_loop()


if __name__ == "__main__":
    main()
