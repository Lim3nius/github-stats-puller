"""
GitHub API Statistics Puller

A Python application that streams GitHub events and provides REST API metrics.
"""

__version__ = "0.1.0"
__author__ = "GitHub Stats Team"

from github_stats.client import GitHubEventsClient
from github_stats.storage import EventStorage
from github_stats.models import ClientState

__all__ = [
    "GitHubEventsClient",
    "EventStorage", 
    "ClientState",
]