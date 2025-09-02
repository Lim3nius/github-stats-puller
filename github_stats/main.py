import asyncio
from .client import GitHubEventsClient


async def async_main():
    client = GitHubEventsClient()

    while True:
        events = await client.poll_events()
        if events:
            print(f"Downloaded {len(events)} events")

        await asyncio.sleep(client.state.poll_interval_sec)


def main():
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
