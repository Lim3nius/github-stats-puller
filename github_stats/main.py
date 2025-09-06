import asyncio
import os
import sys
from loguru import logger
from .client import GitHubEventsClient


def setup_logging():
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logger.remove()
    logger.add(sys.stdout, level=log_level)


async def async_main():
    setup_logging()
    logger.info("Starting GitHub Events polling client")

    client = GitHubEventsClient()

    while True:
        events = await client.poll_events()
        _ = events

        await asyncio.sleep(client.state.poll_interval_sec)


def main():
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
