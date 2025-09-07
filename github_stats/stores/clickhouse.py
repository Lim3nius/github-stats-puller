"""
ClickHouse implementation of DatabaseService
"""

# from datetime import datetime, timezone, timedelta
from typing import List, Any
from github.Event import Event
from loguru import logger

from .base import DatabaseService, EventData, EventCountsByType, DatabaseHealth

from clickhouse_driver import Client


class ClickHouseDatabaseService(DatabaseService):
    """ClickHouse implementation of DatabaseService"""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 9000,
        username: str = "github_app_user",
        password: str = "github_app_pass",
        database: str = "github_stats",
    ):
        self.filtered_event_types = {"WatchEvent", "PullRequestEvent", "IssuesEvent"}

        try:
            self.client = Client(host=host, port=port, user=username, password=password, database=database)
            # Test connection
            self.client.execute("SELECT 1")
            logger.info(f"Connected to ClickHouse at {host}:{port}")
        except Exception as e:
            logger.error(f"Failed to connect to ClickHouse: {e}")
            raise

    def _event_to_data(self, event: Event) -> EventData:
        """Convert GitHub Event to EventData"""
        return EventData(
            event_id=event.id,
            event_type=event.type,
            repo_name=event.repo.name if event.repo.name else "unknown",
            repo_id=event.repo.id if event.repo.id else 0,
            created_at_ts=event.created_at,
            action=getattr(event.payload, "action", None),
        )

    def _filter_duplicate_events(self, events: List[Event]) -> List[Event]:
        """Filter out events that already exist in database (keep oldest)"""
        if not events:
            return []

        event_ids = [event.id for event in events]
        existing_query = """
        SELECT DISTINCT event_id 
        FROM events 
        WHERE event_id IN %(event_ids)s
        """

        try:
            existing_result = self.client.execute(existing_query, {"event_ids": event_ids})
            existing_event_ids = {row[0] for row in existing_result}

            logger.debug(f"Found {len(existing_result)} existing events in database")

            # Filter out events that already exist (keep oldest = skip duplicates)
            new_events = [event for event in events if event.id not in existing_event_ids]

            if len(new_events) < len(events):
                logger.debug(f"Filtered out {len(events) - len(new_events)} duplicate events")

            return new_events

        except Exception as e:
            logger.warning(f"Failed to check for duplicate events: {e}")
            # Fallback to returning all events if deduplication check fails
            return events

    def insert_events(self, events: List[Event]) -> int:
        """Insert GitHub events and return count of inserted records (deduplicates to keep oldest)"""
        if not events:
            return 0

        filtered_events = [event for event in events if event.type in self.filtered_event_types]

        if not filtered_events:
            return 0

        # Remove duplicates (keep oldest)
        new_events = self._filter_duplicate_events(filtered_events)

        if not new_events:
            logger.debug("All events already exist, skipping duplicates")
            return 0

        event_data_list = [self._event_to_data(event) for event in new_events]

        # Prepare data for ClickHouse insertion using parameter substitution
        rows: list[dict[str, Any]] = []
        for event_data in event_data_list:
            rows.append(
                {
                    "event_id": event_data.event_id,
                    "event_type": event_data.event_type,
                    "repo_name": event_data.repo_name,
                    "repo_id": event_data.repo_id,
                    "created_at_ts": event_data.created_at_ts,
                    "action": event_data.action or "",
                    "ingested_at": event_data.ingested_at,
                }
            )

        try:
            self.client.execute(
                "INSERT INTO events (event_id, event_type, repo_name, repo_id, created_at_ts, action, ingested_at) VALUES",
                rows,
            )

            logger.debug(f"Inserted {len(event_data_list)} events into ClickHouse")
            return len(event_data_list)

        except Exception as e:
            logger.error(f"Failed to insert events into ClickHouse: {e}")
            raise

    def get_events_by_type_and_offset(self, offset_minutes: int) -> EventCountsByType:
        """Get event counts by type within the specified time offset"""
        query = """
        SELECT 
            event_type,
            count(*) as count
        FROM events 
        WHERE created_at_ts >= now() - INTERVAL %(offset_minutes)s MINUTE
        GROUP BY event_type
        """

        try:
            result = self.client.execute(query, {"offset_minutes": offset_minutes})

            event_counts = {}
            for row in result:
                event_type, count = row
                event_counts[event_type] = count

            total_events = sum(event_counts.values())

            return EventCountsByType(offset_minutes=offset_minutes, event_counts=event_counts, total_events=total_events)

        except Exception as e:
            logger.error(f"Failed to get event counts from ClickHouse: {e}")
            raise

    def get_pull_request_events_for_repo(self, repo_name: str) -> List[EventData]:
        """Get minimal PR event data - only timestamps needed for calculations"""
        # First try to get from aggregated table for count
        count_query = """
        SELECT sum(pr_count) 
        FROM pr_metrics_agg 
        WHERE repo_name = %(repo_name)s
        """

        # Get only timestamps from events table (minimal data)
        events_query = """
        SELECT created_at_ts
        FROM events 
        WHERE event_type = 'PullRequestEvent' 
          AND repo_name = %(repo_name)s
          AND action = 'opened'
        ORDER BY created_at_ts
        """

        try:
            result = self.client.execute(events_query, {"repo_name": repo_name})
            logger.debug(f"received {len(result)} PR timestamps")

            # Return minimal EventData - only timestamps are actually used
            events = []
            for row in result:
                events.append(
                    EventData(
                        event_id="",
                        event_type="PullRequestEvent",
                        repo_name=repo_name,
                        repo_id=0,
                        created_at_ts=row[0],
                        action="opened",
                        ingested_at=row[0],
                    )
                )

            return events

        except Exception as e:
            logger.error(f"Failed to get PR events from ClickHouse: {e}")
            raise

    def calculate_avg_pr_time(self, repo_name: str) -> float:
        """Calculate average time between pull requests using pre-aggregated data"""
        # Use the pre-aggregated pr_metrics_agg table for faster calculation
        query = """
        SELECT 
            sum(pr_count) as total_prs,
            min(first_pr_ts) as earliest_pr,
            max(last_pr_ts) as latest_pr
        FROM pr_metrics_agg
        WHERE repo_name = %(repo_name)s
        """

        try:
            result = self.client.execute(query, {"repo_name": repo_name})

            if result and result[0][0] and result[0][0] > 1:
                total_prs = result[0][0]
                earliest_pr = result[0][1]
                latest_pr = result[0][2]

                # Calculate average seconds between PRs
                total_duration_sec = (latest_pr - earliest_pr).total_seconds()
                avg_seconds = total_duration_sec / (total_prs - 1)
                return avg_seconds

            return 0.0

        except Exception as e:
            logger.error(f"Failed to calculate avg PR time from aggregated data: {e}")
            # Fallback to raw events table if aggregated data fails
            pr_events = self.get_pull_request_events_for_repo(repo_name)

            if len(pr_events) < 2:
                return 0.0

            time_diffs: list[float] = []
            for i in range(1, len(pr_events)):
                diff = (pr_events[i].created_at_ts - pr_events[i - 1].created_at_ts).total_seconds()
                time_diffs.append(diff)

            return sum(time_diffs) / len(time_diffs) if time_diffs else 0.0

    def get_health_status(self) -> DatabaseHealth:
        """Get database connection and health information"""
        try:
            # Test connection
            self.client.execute("SELECT 1")

            # Get total events
            total_result = self.client.execute("SELECT count(*) FROM events")
            total_events = total_result[0][0] if total_result else 0

            # Get latest event timestamp
            latest_result = self.client.execute("SELECT max(created_at_ts) FROM events")
            last_event_ts = latest_result[0][0] if latest_result else None

            return DatabaseHealth(
                is_connected=True, backend_type="clickhouse", total_events=total_events, last_event_ts=last_event_ts
            )

        except Exception as e:
            logger.error(f"ClickHouse health check failed: {e}")
            return DatabaseHealth(is_connected=False, backend_type="clickhouse", total_events=0, last_event_ts=None)

    def get_events_count_by_repo(self, repo_name: str) -> int:
        """Get total event count for a specific repository"""
        try:
            result = self.client.execute(
                "SELECT count(*) FROM events WHERE repo_name = %(repo_name)s", {"repo_name": repo_name}
            )
            return result[0][0] if result else 0
        except Exception as e:
            logger.error(f"Failed to get repo event count from ClickHouse: {e}")
            return 0
