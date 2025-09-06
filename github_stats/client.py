import json
import httpx
from pathlib import Path
from datetime import datetime, timezone
from typing import Any
from loguru import logger

from .models import ClientState


class GitHubEventsClient:
    def __init__(self, state_file: str = "client-state.json"):
        self.url = "https://api.github.com/events"
        self.state_file = Path(state_file)
        self.events_dir = Path("downloaded-events")

        self.events_dir.mkdir(exist_ok=True)

        self.state = self._load_state()
        logger.debug(f"Initialized client with state file: {state_file}, poll interval: {self.state.poll_interval_sec}s")

    def _load_state(self) -> ClientState:
        if self.state_file.exists():
            logger.debug(f"Loading state from {self.state_file}")
            return ClientState.model_validate_json(self.state_file.read_text())
        logger.debug("No existing state file found, creating new state")
        return ClientState()

    def _save_state(self):
        self.state_file.write_text(self.state.model_dump_json())
        logger.debug(f"State saved to {self.state_file}")

    async def check_for_updates(self) -> bool:
        headers: dict[str, str] = {}
        if self.state.etag:
            headers["If-None-Match"] = self.state.etag

        logger.debug("Checking for updates with HEAD request")
        async with httpx.AsyncClient() as client:
            response = await client.head(self.url, headers=headers)

            if response.status_code == 304:
                logger.debug("No updates available (HTTP 304)")
                return False

            if "x-poll-interval" in response.headers:
                new_interval = int(response.headers["x-poll-interval"])
                if new_interval != self.state.poll_interval_sec:
                    logger.info(f"Poll interval updated from {self.state.poll_interval_sec}s to {new_interval}s")
                    self.state.poll_interval_sec = new_interval

            logger.debug("Updates available")
            return True

    async def fetch_events(self) -> Any:
        headers: dict[str, str] = {}

        if self.state.etag:
            headers["If-None-Match"] = self.state.etag

        if self.state.last_modified:
            headers["If-Modified-Since"] = self.state.last_modified

        logger.debug("Fetching events with GET request")
        async with httpx.AsyncClient() as client:
            response = await client.get(self.url, headers=headers)

            if response.status_code == 304:
                logger.debug("No new events (HTTP 304)")
                return None

            response.raise_for_status()

            if "etag" in response.headers:
                self.state.etag = response.headers["etag"]

            if "last-modified" in response.headers:
                self.state.last_modified = response.headers["last-modified"]

            if "x-poll-interval" in response.headers:
                self.state.poll_interval_sec = int(response.headers["x-poll-interval"])

            poll_ts = datetime.now(timezone.utc)
            self.state.last_poll = poll_ts

            timestamp = poll_ts.strftime("%Y-%m-%dT%H-%M-%S")
            filename = self.events_dir.joinpath(f"{timestamp}.json")

            events_data = response.json()
            filename.write_text(json.dumps(events_data))
            
            logger.info(f"Saved {len(events_data)} events to {filename}")

            self._save_state()

            return events_data

    async def poll_events(self) -> Any:
        if await self.check_for_updates():
            return await self.fetch_events()
        return None
