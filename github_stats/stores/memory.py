"""
In-memory implementation of DatabaseService for backwards compatibility
"""

from datetime import datetime, timezone, timedelta
from typing import List
from github.Event import Event
from loguru import logger

from .base import DatabaseService, EventData, EventCountsByType, DatabaseHealth, EventInfo, RepoEventCount


class InMemoryDatabaseService(DatabaseService):
    """In-memory implementation of DatabaseService for backwards compatibility"""

    def __init__(self):
        self.filtered_event_types = {"WatchEvent", "PullRequestEvent", "IssuesEvent"}

        import threading

        self._lock = threading.RLock()
        self.events: List[EventData] = []

    def _event_to_data(self, event: Event) -> EventData:
        """Convert GitHub Event to EventData"""
        return EventData(
            event_id=event.id,
            event_type=event.type,
            repo_name=event.repo.name if event.repo else "unknown",
            repo_id=event.repo.id if event.repo else 0,
            created_at_ts=event.created_at,
            action=getattr(event.payload, "action", None),
        )

    async def insert_events(self, events: List[Event]) -> int:
        """Insert GitHub events and return count of inserted records"""
        with self._lock:
            filtered_events = [event for event in events if event.type in self.filtered_event_types]

            event_data_list = [self._event_to_data(event) for event in filtered_events]
            self.events.extend(event_data_list)

            if event_data_list:
                logger.debug(f"Added {len(event_data_list)} filtered events, total stored: {len(self.events)}")

            return len(event_data_list)

    async def get_events_by_type_and_offset(self, offset_minutes: int) -> EventCountsByType:
        """Get event counts by type within the specified time offset"""
        cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=offset_minutes)

        with self._lock:
            event_counts: dict[str, int] = {}
            for event in self.events:
                if event.created_at_ts >= cutoff_time:
                    event_counts[event.event_type] = event_counts.get(event.event_type, 0) + 1

            total_events = sum(event_counts.values())

            return EventCountsByType(offset_minutes=offset_minutes, event_counts=event_counts, total_events=total_events)

    async def get_pull_request_events_for_repo(self, repo_name: str) -> List[EventData]:
        """Get all PullRequestEvent events for a specific repository"""
        with self._lock:
            return [event for event in self.events if event.event_type == "PullRequestEvent" and event.repo_name == repo_name]

    async def calculate_avg_pr_time(self, repo_name: str) -> float:
        """Calculate average time between pull requests for a repository in seconds"""
        pr_events = await self.get_pull_request_events_for_repo(repo_name)

        if len(pr_events) < 2:
            return 0.0

        # Sort by creation time
        pr_events.sort(key=lambda x: x.created_at_ts)

        time_diffs: list[float] = []
        for i in range(1, len(pr_events)):
            diff = (pr_events[i].created_at_ts - pr_events[i - 1].created_at_ts).total_seconds()
            time_diffs.append(diff)

        return sum(time_diffs) / len(time_diffs) if time_diffs else 0.0

    async def get_health_status(self) -> DatabaseHealth:
        """Get database connection and health information"""
        with self._lock:
            last_event_ts = None
            if self.events:
                last_event_ts = max(event.created_at_ts for event in self.events)

            return DatabaseHealth(
                is_connected=True, backend_type="in-memory", total_events=len(self.events), last_event_ts=last_event_ts
            )

    async def get_events_count_by_repo(self, repo_name: str) -> int:
        """Get total event count for a specific repository"""
        with self._lock:
            return len([event for event in self.events if event.repo_name == repo_name])

    async def get_events_for_repo(self, repo_name: str) -> List[EventInfo]:
        """Get all events for a repository - not implemented for in-memory backend"""
        raise NotImplementedError("get_events_for_repo not implemented for in-memory backend")

    async def get_repos_by_event_count(self, limit: int = 10) -> List[RepoEventCount]:
        """Get repositories sorted by event count - not implemented for in-memory backend"""
        raise NotImplementedError("get_repos_by_event_count not implemented for in-memory backend")
