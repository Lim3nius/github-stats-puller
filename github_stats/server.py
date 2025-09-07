from fastapi import FastAPI, Query
from pydantic import BaseModel
from typing import Dict
import uvicorn

from github_stats.database import database_service, DatabaseHealth

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
    avg_time = database_service.calculate_avg_pr_time(repository)
    pr_events = database_service.get_pull_request_events_for_repo(repository)
    
    return PullRequestMetricsResponse(
        repository=repository,
        average_time_seconds=avg_time,
        total_pull_requests=len(pr_events)
    )


@app.get("/metrics/events", response_model=EventCountResponse)
async def get_event_counts(offset: int = Query(..., description="Time offset in minutes")):
    """Get event counts by type for the given time offset"""
    result = database_service.get_events_by_type_and_offset(offset)
    
    return EventCountResponse(
        offset_minutes=result.offset_minutes,
        event_counts=result.event_counts,
        total_events=result.total_events
    )


@app.get("/metrics/visualization")
async def get_visualization(offset: int = Query(60, description="Time offset in minutes")):
    """Bonus endpoint: Return visualization data"""
    result = database_service.get_events_by_type_and_offset(offset)
    
    return {
        "chart_type": "bar",
        "title": f"GitHub Events by Type (Last {offset} minutes)",
        "data": {
            "labels": list(result.event_counts.keys()),
            "values": list(result.event_counts.values())
        },
        "total_events": result.total_events
    }


@app.get("/health", response_model=DatabaseHealth)
async def get_health():
    """Health check and database status"""
    return database_service.get_health_status()


@app.get("/debug/total-events")
async def get_total_events():
    """Debugging: Get total event count"""
    return {"total_events": database_service.get_total_event_count()}


@app.get("/debug/repo-events/{repository}")
async def get_repo_events(repository: str):
    """Debugging: Get event count for a specific repository"""
    count = database_service.get_events_count_by_repo(repository)
    return {"repository": repository, "event_count": count}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)