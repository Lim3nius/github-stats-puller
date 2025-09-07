"""
ClickHouse implementation of DatabaseService
"""

# from datetime import datetime, timezone, timedelta
from typing import List, Any
from github.Event import Event
from loguru import logger

from .base import DatabaseService, EventData, EventCountsByType, DatabaseHealth


class ClickHouseDatabaseService(DatabaseService):
    """ClickHouse implementation of DatabaseService"""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8123,
        username: str = "github_app_user",
        password: str = "github_app_pass",
        database: str = "github_stats",
    ):
        import clickhouse_connect
        from clickhouse_connect.driver.client import Client

        self.filtered_event_types = {"WatchEvent", "PullRequestEvent", "IssuesEvent"}

        try:
            self.client: Client = clickhouse_connect.get_client(
                host=host, port=port, username=username, password=password, database=database
            )
            # Test connection
            self.client.query("SELECT 1")
            logger.info(f"Connected to ClickHouse at {host}:{port}")
        except Exception as e:
            logger.error(f"Failed to connect to ClickHouse: {e}")
            raise

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

    def insert_events(self, events: List[Event]) -> int:
        """Insert GitHub events and return count of inserted records"""
        if not events:
            return 0

        filtered_events = [event for event in events if event.type in self.filtered_event_types]

        if not filtered_events:
            return 0

        event_data_list = [self._event_to_data(event) for event in filtered_events]

        # Prepare data for ClickHouse insertion with explicit column order
        rows: list[Any] = []
        for event_data in event_data_list:
            rows.append(
                [
                    event_data.event_id,
                    event_data.event_type,
                    event_data.repo_name,
                    event_data.repo_id,
                    event_data.created_at_ts,
                    event_data.action or "",
                    event_data.ingested_at,
                ]
            )

        try:
            self.client.insert(
                table="events",
                data=rows,
                column_names=["event_id", "event_type", "repo_name", "repo_id", "created_at_ts", "action", "ingested_at"],
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
        WHERE created_at_ts >= now() - INTERVAL ? MINUTE
        GROUP BY event_type
        """

        try:
            result: dict[str, Any] = self.client.query(query, parameters=[offset_minutes])

            event_counts = {}
            for row in result.result_rows:
                event_type, count = row
                event_counts[event_type] = count

            total_events = sum(event_counts.values())

            return EventCountsByType(offset_minutes=offset_minutes, event_counts=event_counts, total_events=total_events)

        except Exception as e:
            logger.error(f"Failed to get event counts from ClickHouse: {e}")
            raise

    def get_pull_request_events_for_repo(self, repo_name: str) -> List[EventData]:
        """Get all PullRequestEvent events for a specific repository"""
        query = """
        SELECT 
            event_id, event_type, repo_name, repo_id, 
            created_at_ts, action, ingested_at
        FROM events 
        WHERE event_type = 'PullRequestEvent' AND repo_name = ?
        ORDER BY created_at_ts
        """

        try:
            result = self.client.query(query, parameters=[repo_name])

            events = []
            for row in result.result_rows:
                event_id, event_type, repo_name, repo_id, created_at_ts, action, ingested_at = row
                events.append(
                    EventData(
                        event_id=event_id,
                        event_type=event_type,
                        repo_name=repo_name,
                        repo_id=repo_id,
                        created_at_ts=created_at_ts,
                        action=action,
                        ingested_at=ingested_at,
                    )
                )

            return events

        except Exception as e:
            logger.error(f"Failed to get PR events from ClickHouse: {e}")
            raise

    def calculate_avg_pr_time(self, repo_name: str) -> float:
        """Calculate average time between pull requests for a repository in seconds"""
        pr_events = self.get_pull_request_events_for_repo(repo_name)

        if len(pr_events) < 2:
            return 0.0

        # Events are already sorted by created_at_ts from query
        time_diffs: list[float] = []
        for i in range(1, len(pr_events)):
            diff = (pr_events[i].created_at_ts - pr_events[i - 1].created_at_ts).total_seconds()
            time_diffs.append(diff)

        return sum(time_diffs) / len(time_diffs) if time_diffs else 0.0

    def get_health_status(self) -> DatabaseHealth:
        """Get database connection and health information"""
        try:
            # Test connection
            self.client.query("SELECT 1")

            # Get total events
            total_result = self.client.query("SELECT count(*) FROM events")
            total_events = total_result.result_rows[0][0] if total_result.result_rows else 0

            # Get latest event timestamp
            latest_result = self.client.query("SELECT max(created_at_ts) FROM events")
            last_event_ts = latest_result.result_rows[0][0] if latest_result.result_rows else None

            return DatabaseHealth(
                is_connected=True, backend_type="clickhouse", total_events=total_events, last_event_ts=last_event_ts
            )

        except Exception as e:
            logger.error(f"ClickHouse health check failed: {e}")
            return DatabaseHealth(is_connected=False, backend_type="clickhouse", total_events=0, last_event_ts=None)

    def get_total_event_count(self) -> int:
        """Get total number of events stored"""
        try:
            result = self.client.query("SELECT count(*) FROM events")
            return result.result_rows[0][0] if result.result_rows else 0
        except Exception as e:
            logger.error(f"Failed to get total event count from ClickHouse: {e}")
            return 0

    def get_events_count_by_repo(self, repo_name: str) -> int:
        """Get total event count for a specific repository"""
        try:
            result = self.client.query("SELECT count(*) FROM events WHERE repo_name = ?", parameters=[repo_name])
            return result.result_rows[0][0] if result.result_rows else 0
        except Exception as e:
            logger.error(f"Failed to get repo event count from ClickHouse: {e}")
            return 0
