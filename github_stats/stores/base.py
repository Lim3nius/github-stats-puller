"""
Database service interface and data models.
This file has zero codebase dependencies to maintain clean architecture.
"""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Dict, List, Optional, TypedDict
from pydantic import BaseModel, Field

from github.Event import Event


# Pydantic models for structured data


class EventData(BaseModel):
    """Structured representation of a GitHub event for database storage"""

    event_id: str
    event_type: str
    repo_name: str
    repo_id: int
    created_at_ts: datetime
    action: Optional[str] = None
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class EventCountsByType(BaseModel):
    """Response model for event counts grouped by type"""

    offset_minutes: int
    event_counts: Dict[str, int]
    total_events: int


class PullRequestMetrics(BaseModel):
    """Response model for pull request metrics"""

    repository: str
    average_time_seconds: float
    total_pull_requests: int


class DatabaseHealth(BaseModel):
    """Database connection and health status"""

    is_connected: bool
    backend_type: str
    total_events: int
    last_event_ts: Optional[datetime] = None


# Configuration types


class ClickHouseConfig(TypedDict):
    """TypedDict for ClickHouse configuration parameters"""

    host: str
    port: int
    username: str
    password: str
    database: str


# Abstract base class for database services


class DatabaseService(ABC):
    """Abstract base class for database operations"""

    @abstractmethod
    def insert_events(self, events: list[Event]) -> int:
        """Insert GitHub events and return count of inserted records"""
        pass

    @abstractmethod
    def get_events_by_type_and_offset(self, offset_minutes: int) -> EventCountsByType:
        """Get event counts by type within the specified time offset"""
        pass

    @abstractmethod
    def get_pull_request_events_for_repo(self, repo_name: str) -> List[EventData]:
        """Get all PullRequestEvent events for a specific repository"""
        pass

    @abstractmethod
    def calculate_avg_pr_time(self, repo_name: str) -> float:
        """Calculate average time between pull requests for a repository in seconds"""
        pass

    @abstractmethod
    def get_health_status(self) -> DatabaseHealth:
        """Get database connection and health information"""
        pass

    @abstractmethod
    def get_events_count_by_repo(self, repo_name: str) -> int:
        """Get total event count for a specific repository"""
        pass
