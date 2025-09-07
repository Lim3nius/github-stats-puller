import threading
from typing import Dict, List
from datetime import datetime, timezone, timedelta
from github.Event import Event
from loguru import logger


class EventStorage:
    """Thread-safe storage for GitHub events shared between client and server"""
    
    def __init__(self):
        self.events: List[Event] = []
        self.lock = threading.RLock()
        self.filtered_event_types = {'WatchEvent', 'PullRequestEvent', 'IssuesEvent'}
    
    def add_events(self, events: List[Event]) -> None:
        """Add new events to storage, filtering for relevant types"""
        with self.lock:
            filtered_events = [
                event for event in events 
                if event.type in self.filtered_event_types
            ]
            self.events.extend(filtered_events)
            
            if filtered_events:
                logger.debug(f"Added {len(filtered_events)} filtered events, total stored: {len(self.events)}")
    
    def get_events_by_type_and_offset(self, offset_minutes: int) -> Dict[str, int]:
        """Get event counts by type within the specified time offset"""
        cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=offset_minutes)
        
        with self.lock:
            event_counts = {}
            for event in self.events:
                if event.created_at >= cutoff_time:
                    event_counts[event.type] = event_counts.get(event.type, 0) + 1
            
            return event_counts
    
    def get_pull_request_events_for_repo(self, repo_name: str) -> List[Event]:
        """Get all PullRequestEvent events for a specific repository"""
        with self.lock:
            return [
                event for event in self.events 
                if event.type == 'PullRequestEvent' and event.repo and event.repo.name == repo_name
            ]
    
    def calculate_avg_pr_time(self, repo_name: str) -> float:
        """Calculate average time between pull requests for a repository in seconds"""
        pr_events = self.get_pull_request_events_for_repo(repo_name)
        
        if len(pr_events) < 2:
            return 0.0
        
        # Sort by creation time
        pr_events.sort(key=lambda x: x.created_at)
        
        time_diffs = []
        for i in range(1, len(pr_events)):
            diff = (pr_events[i].created_at - pr_events[i-1].created_at).total_seconds()
            time_diffs.append(diff)
        
        return sum(time_diffs) / len(time_diffs) if time_diffs else 0.0


# Global storage instance
event_storage = EventStorage()