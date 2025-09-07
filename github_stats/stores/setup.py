"""
Database service configuration and factory functions.
"""

from .base import DatabaseService, ClickHouseConfig
from .memory import InMemoryDatabaseService
from .clickhouse import ClickHouseDatabaseService


def create_database_service(backend: str = "memory", conf: ClickHouseConfig | None = None) -> DatabaseService:
    """Factory function to create database service based on configuration"""
    match backend.lower():
        case "memory":
            return InMemoryDatabaseService()
        case "clickhouse":
            assert conf is not None, "Missing clickhouse config"
            return ClickHouseDatabaseService(
                host=conf["host"],
                port=conf["port"],
                username=conf["username"],
                password=conf["password"],
                database=conf["database"],
            )
        case _:
            raise ValueError(f"Unknown database backend: {backend}")


def configure_database_service(backend: str = "memory", conf: ClickHouseConfig | None = None) -> DatabaseService:
    """Configure and return global database service instance"""
    from . import set_database_service
    service = create_database_service(backend, conf)
    set_database_service(service)
    return service