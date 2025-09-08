#!/usr/bin/env python3
"""
Backfill tool to process existing JSON event files and populate the database.
This tool reads JSON files from the downloaded-events directory and processes them
through the database service to populate the database with historical data.
"""

import json
import os
from pathlib import Path
from typing import List, Any, Dict
from loguru import logger
from dateutil import parser
from dotenv import load_dotenv
import asyncio

from github_stats.stores import configure_database_service
from github_stats.stores.base import EventData, ClickHouseConfig
from github_stats.stores.clickhouse import ClickHouseDatabaseService


class EventBackfiller:
    """Processes JSON event files and populates database"""

    def __init__(self, events_dir: str | None = None, dotenv_path: str | None = None):
        # Load environment variables from dotenv file
        env_file = dotenv_path or "gh.env"
        if Path(env_file).exists():
            load_dotenv(env_file)
            logger.info(f"Loaded environment variables from {env_file}")
        else:
            logger.debug(f"Environment file {env_file} not found, using system environment")

        self.events_dir = Path(events_dir or os.getenv("EVENTS_DIRECTORY", "downloaded-events"))
        self.filtered_event_types = {"WatchEvent", "PullRequestEvent", "IssuesEvent"}

        # Configure database service based on environment
        backend = os.getenv("DATABASE_BACKEND", "memory").lower()

        if backend != "clickhouse":
            logger.error("Backfill tool requires ClickHouse database backend")
            logger.error("Set DATABASE_BACKEND=clickhouse environment variable")
            raise ValueError("Backfill tool only works with ClickHouse database backend")

        # Configure ClickHouse connection
        clickhouse_config: ClickHouseConfig = {
            "host": os.getenv("CLICKHOUSE_HOST", "localhost"),
            "port": int(os.getenv("CLICKHOUSE_PORT", "9000")),
            "username": os.getenv("CLICKHOUSE_USER", "github_user"),
            "password": os.getenv("CLICKHOUSE_PASSWORD", "github_pass"),
            "database": os.getenv("CLICKHOUSE_DATABASE", "github_stats"),
        }

        # Configure the database service - we know it's ClickHouse at this point
        self.clickhouse_service = configure_database_service(backend, clickhouse_config)
        assert isinstance(self.clickhouse_service, ClickHouseDatabaseService), "Expected ClickHouse service"

        logger.info(f"Backfill tool initialized with ClickHouse backend and events directory: {self.events_dir}")

    def _create_event_data_from_dict(self, event_dict: Dict[str, Any]) -> EventData:
        """Create EventData object from dictionary - let it crash on missing mandatory fields"""
        # Parse the created_at timestamp
        created_at_ts = parser.isoparse(event_dict["created_at"])

        # Extract action (optional, may be None or empty)
        action = event_dict.get("payload", {}).get("action")

        return EventData(
            event_id=str(event_dict["id"]),
            event_type=event_dict["type"],
            repo_name=event_dict["repo"]["name"],
            repo_id=int(event_dict["repo"]["id"]),
            created_at_ts=created_at_ts,
            action=action,
        )

    def _process_json_file(self, file_path: Path) -> List[EventData]:
        """Process a single JSON file and return list of EventData objects"""
        try:
            with open(file_path, "r") as f:
                events_data = json.load(f)

            if not isinstance(events_data, list):
                logger.warning(f"File {file_path} does not contain a list of events, skipping")
                return []

            events = []
            for event_dict in events_data:
                if not isinstance(event_dict, dict):
                    continue

                event_type = event_dict.get("type", "")
                if event_type not in self.filtered_event_types:
                    continue

                try:
                    event_data = self._create_event_data_from_dict(event_dict)
                    events.append(event_data)
                except Exception as e:
                    logger.warning(f"Failed to create event from data in {file_path}: {e}")
                    continue

            logger.debug(f"Processed {file_path}: {len(events)} relevant events out of {len(events_data)} total")
            return events

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from {file_path}: {e}")
            return []
        except Exception as e:
            logger.error(f"Error processing file {file_path}: {e}")
            return []

    def get_json_files(self) -> List[Path]:
        """Get all JSON files from the events directory, sorted by filename"""
        if not self.events_dir.exists():
            logger.error(f"Events directory {self.events_dir} does not exist")
            return []

        json_files = list(self.events_dir.glob("*.json"))
        json_files.sort()  # Sort by filename (which includes timestamp)

        logger.info(f"Found {len(json_files)} JSON files to process")
        return json_files

    async def backfill_from_files(self, dry_run: bool = False) -> Dict[str, int]:
        """
        Process all JSON files and populate database

        Args:
            dry_run: If True, process files but don't insert into database

        Returns:
            Dictionary with processing statistics
        """
        json_files = self.get_json_files()

        if not json_files:
            logger.warning("No JSON files found to process")
            return {"files_processed": 0, "events_inserted": 0, "errors": 0}

        stats = {"files_processed": 0, "events_found": 0, "events_inserted": 0, "errors": 0}

        logger.info(f"Starting backfill of {len(json_files)} files (dry_run={dry_run})")

        for file_path in json_files:
            logger.info(f"Processing {file_path.name}...")

            try:
                event_data_list = self._process_json_file(file_path)
                stats["events_found"] += len(event_data_list)

                if event_data_list and not dry_run:
                    # Use ClickHouse-specific insert_event_data method (async)
                    inserted_count = await self.clickhouse_service.insert_event_data(event_data_list)
                    stats["events_inserted"] += inserted_count
                    logger.info(f"Inserted {inserted_count} events from {file_path.name}")

                elif event_data_list and dry_run:
                    logger.info(f"Would insert {len(event_data_list)} events from {file_path.name} (dry run)")

                stats["files_processed"] += 1

            except Exception as e:
                logger.error(f"Error processing {file_path.name}: {e}")
                stats["errors"] += 1

        # Log final statistics
        logger.info("Backfill completed!")
        logger.info(f"Files processed: {stats['files_processed']}")
        logger.info(f"Events found: {stats['events_found']}")
        logger.info(f"Events inserted: {stats['events_inserted']}")
        logger.info(f"Errors: {stats['errors']}")

        return stats


async def async_main():
    """Async main function for backfill tool"""
    import argparse

    parser = argparse.ArgumentParser(description="Backfill database from JSON event files")
    parser.add_argument("--events-dir", type=str, help="Directory containing JSON event files (default: downloaded-events)")
    parser.add_argument("--dry-run", action="store_true", help="Process files but don't insert into database")
    parser.add_argument("--dotenv", type=str, default="gh.env", help="Path to .env file (default: gh.env)")

    args = parser.parse_args()

    backfiller = EventBackfiller(events_dir=args.events_dir, dotenv_path=args.dotenv)
    stats = await backfiller.backfill_from_files(dry_run=args.dry_run)

    if stats["errors"] > 0:
        exit(1)
    else:
        exit(0)


def main():
    """Main entry point for backfill tool"""
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
