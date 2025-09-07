from fastapi import FastAPI, Query
from pydantic import BaseModel
from typing import Dict, Any
import uvicorn

from .storage import event_storage

app = FastAPI(
    title="GitHub Events API",
    description="REST API for GitHub events metrics",
    version="1.0.0"
)


class PullRequestMetricsResponse(BaseModel):
    repository: str
    average_time_seconds: float
    total_pull_requests: int


class EventCountResponse(BaseModel):
    offset_minutes: int
    event_counts: Dict[str, int]
    total_events: int


@app.get("/")
async def root():
    return {"message": "GitHub Events API"}


@app.get("/metrics/pr-average/{repository}", response_model=PullRequestMetricsResponse)
async def get_pr_average_time(repository: str):
    """Get average time between pull requests for a repository"""
    avg_time = event_storage.calculate_avg_pr_time(repository)
    pr_events = event_storage.get_pull_request_events_for_repo(repository)
    
    return PullRequestMetricsResponse(
        repository=repository,
        average_time_seconds=avg_time,
        total_pull_requests=len(pr_events)
    )


@app.get("/metrics/events", response_model=EventCountResponse)
async def get_event_counts(offset: int = Query(..., description="Time offset in minutes")):
    """Get event counts by type for the given time offset"""
    event_counts = event_storage.get_events_by_type_and_offset(offset)
    total_events = sum(event_counts.values())
    
    return EventCountResponse(
        offset_minutes=offset,
        event_counts=event_counts,
        total_events=total_events
    )


@app.get("/metrics/visualization")
async def get_visualization(offset: int = Query(60, description="Time offset in minutes")):
    """Bonus endpoint: Return visualization data"""
    event_counts = event_storage.get_events_by_type_and_offset(offset)
    
    return {
        "chart_type": "bar",
        "title": f"GitHub Events by Type (Last {offset} minutes)",
        "data": {
            "labels": list(event_counts.keys()),
            "values": list(event_counts.values())
        },
        "total_events": sum(event_counts.values())
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)