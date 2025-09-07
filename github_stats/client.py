import json
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, List
from loguru import logger
from github import Github
from github.Event import Event
import time

from github_stats.models import ClientState
from github_stats.storage import event_storage


class GitHubEventsClient:
    def __init__(self, state_file: str = "client-state.json"):
        self.state_file = Path(state_file)
        self.events_dir = Path("downloaded-events")

        self.events_dir.mkdir(exist_ok=True)

        token = os.getenv("GITHUB_TOKEN")
        if not token:
            logger.warning("GITHUB_TOKEN not found, using unauthenticated requests (rate limited)")
            self.github = Github()
        else:
            self.github = Github(token)

        self.state = self._load_state()

        logger.debug(
            f"Initialized PyGitHub client with state file: {state_file}, poll interval: {self.state.poll_interval_sec}s"
        )

    def _load_state(self) -> ClientState:
        if self.state_file.exists():
            logger.debug(f"Loading state from {self.state_file}")
            return ClientState.model_validate_json(self.state_file.read_text())
        logger.debug("No existing state file found, creating new state")
        return ClientState()

    def _save_state(self):
        self.state_file.write_text(self.state.model_dump_json())
        logger.debug(f"State saved to {self.state_file}")

    def _check_rate_limit(self):
        """Check and respect GitHub API rate limits"""
        try:
            rate_limit = self.github.get_rate_limit()
            logger.info(rate_limit)

            if rate_limit.rate.remaining < 10:  # Conservative threshold
                sleep_time = (rate_limit.rate.reset - datetime.now(timezone.utc)).total_seconds()
                if sleep_time > 0:
                    logger.warning(f"Rate limit low, sleeping for {sleep_time} seconds")
                    time.sleep(sleep_time)

        except Exception as e:
            logger.warning(f"Could not check rate limit: {e}")

    def _get_public_events(self) -> List[Event]:
        """Get public events using PyGitHub"""
        try:
            # PyGitHub doesn't support conditional requests directly,
            # but we can still fetch events and compare timestamps
            events = list(self.github.get_events())

            return events

        except Exception as e:
            logger.error(f"Error getting public events: {e}")
            raise

    def poll_events(self) -> List[Any]:
        """Poll GitHub events using PyGitHub"""
        logger.debug("Polling GitHub events using PyGitHub")

        self._check_rate_limit()

        try:
            events = self._get_public_events()

            if not events:
                logger.debug("No events available")
                self.state.last_poll = datetime.now(timezone.utc)
                self._save_state()
                return []

            # Filter new events based on last poll time if available
            # if self.state.last_poll:
            #     new_events: list[Event] = []
            #     for event in events:
            #         event_time = event.created_at
            #         if event_time > self.state.last_poll:
            #             new_events.append(event)
            #     events = new_events

            poll_ts = datetime.now(timezone.utc)
            self.state.last_poll = poll_ts

            timestamp = poll_ts.strftime("%Y-%m-%dT%H-%M-%S")
            filename = self.events_dir.joinpath(f"{timestamp}.json")

            raw_events = [event.raw_data for event in events]
            filename.write_text(json.dumps(raw_events))
            logger.info(f"Saved {len(events)} events to {filename}")

            # Store events in shared storage for server access
            event_storage.add_events(events)

            self._save_state()

            return events

        except Exception as e:
            logger.error(f"Error polling events: {e}")
            return []
