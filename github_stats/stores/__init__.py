"""
Database stores package - clean re-exports and global instance management.
"""

# Re-export all base classes and models
from .base import (
    EventData,
    EventCountsByType,
    EventInfo,
    RepoEventCount,
    PullRequestMetrics,
    DatabaseHealth,
    DatabaseService,
    ClickHouseConfig,
)

# Re-export configuration functions
from .setup import create_database_service, configure_database_service

# Re-export implementations for convenience
from .memory import InMemoryDatabaseService
from .clickhouse import ClickHouseDatabaseService

# Global database service instance (initialized lazily)
_database_service: DatabaseService | None = None


def get_database_service() -> DatabaseService:
    """Get the global database service instance, creating default if needed"""
    global _database_service
    if _database_service is None:
        _database_service = InMemoryDatabaseService()
    return _database_service


def set_database_service(service: DatabaseService) -> None:
    """Set the global database service instance"""
    global _database_service
    _database_service = service


# Dynamic module attribute access
# def __getattr__(name: str):
#     if name == "database_service":
#         return get_database_service()
#     raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


# Export all public classes and functions
__all__ = [
    # Base classes and models
    "EventData",
    "EventCountsByType",
    "EventInfo",
    "RepoEventCount",
    "PullRequestMetrics",
    "DatabaseHealth",
    "DatabaseService",
    "ClickHouseConfig",
    # Implementations
    "InMemoryDatabaseService",
    "ClickHouseDatabaseService",
    # Configuration
    "create_database_service",
    "configure_database_service",
    "get_database_service",
]
