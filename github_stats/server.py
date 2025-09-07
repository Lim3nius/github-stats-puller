from fastapi import FastAPI, Query, Request
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response
from pydantic import BaseModel
from typing import Dict, TypedDict, List, Callable, Awaitable
import uvicorn
import time
from loguru import logger

from github_stats.stores import get_database_service, DatabaseHealth

# Type alias for middleware functions
MiddlewareFunc = Callable[[Request, RequestResponseEndpoint], Awaitable[Response]]


def create_access_log_middleware() -> MiddlewareFunc:
    """Factory function for access log middleware"""

    async def access_log_middleware(request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Log all HTTP requests with timing information"""
        start_time = time.time()

        # Process the request
        response = await call_next(request)

        # Calculate request duration
        duration_ms = (time.time() - start_time) * 1000

        # Log the access information
        logger.info(f"{request.method} {request.url.path} - {response.status_code} - {duration_ms:.2f}ms")

        return response

    return access_log_middleware


def setup_middlewares(app: FastAPI, middlewares: List[MiddlewareFunc]) -> None:
    """
    Setup middlewares in explicit order.
    Middlewares are executed in reverse order of registration for requests,
    and in forward order for responses.
    """
    for middleware in middlewares:
        app.middleware("http")(middleware)


# Create FastAPI app
app = FastAPI(title="GitHub Events API", description="REST API for GitHub events metrics", version="1.0.0")

# Define middleware chain explicitly
middleware_chain: List[MiddlewareFunc] = [
    create_access_log_middleware(),
]

# Setup all middlewares
setup_middlewares(app, middleware_chain)


# TypedDict definitions for return values
class RootResponse(TypedDict):
    message: str


class VisualizationData(TypedDict):
    labels: list[str]
    values: list[int]


class VisualizationResponse(TypedDict):
    chart_type: str
    title: str
    data: VisualizationData
    total_events: int


class RepoEventsResponse(TypedDict):
    repository: str
    event_count: int


class PullRequestMetricsResponse(BaseModel):
    repository: str
    average_time_seconds: float
    total_pull_requests: int


class EventCountResponse(BaseModel):
    offset_minutes: int
    event_counts: Dict[str, int]
    total_events: int


@app.get("/")
async def root() -> RootResponse:
    return {"message": "GitHub Events API"}


@app.get("/metrics/pr-average/{repository:path}", response_model=PullRequestMetricsResponse)
async def get_pr_average_time(repository: str) -> PullRequestMetricsResponse:
    """
    Get average time between pull requests for a repository.

    Args:
        repository: Repository name in format 'owner/repo' (e.g., 'facebook/react')
    """
    db_service = get_database_service()
    avg_time = db_service.calculate_avg_pr_time(repository)
    pr_events = db_service.get_pull_request_events_for_repo(repository)

    return PullRequestMetricsResponse(repository=repository, average_time_seconds=avg_time, total_pull_requests=len(pr_events))


@app.get("/metrics/events", response_model=EventCountResponse)
async def get_event_counts(offset: int = Query(..., description="Time offset in minutes")) -> EventCountResponse:
    """Get event counts by type for the given time offset"""
    result = get_database_service().get_events_by_type_and_offset(offset)

    return EventCountResponse(
        offset_minutes=result.offset_minutes, event_counts=result.event_counts, total_events=result.total_events
    )


@app.get("/metrics/visualization")
async def get_visualization(offset: int = Query(60, description="Time offset in minutes")) -> VisualizationResponse:
    """Bonus endpoint: Return visualization data"""
    result = get_database_service().get_events_by_type_and_offset(offset)

    return {
        "chart_type": "bar",
        "title": f"GitHub Events by Type (Last {offset} minutes)",
        "data": {"labels": list(result.event_counts.keys()), "values": list(result.event_counts.values())},
        "total_events": result.total_events,
    }


@app.get("/health", response_model=DatabaseHealth)
async def get_health() -> DatabaseHealth:
    """Health check and database status"""
    return get_database_service().get_health_status()


@app.get("/debug/repo-events/{repository:path}")
async def get_repo_events(repository: str) -> RepoEventsResponse:
    """
    Debugging: Get event count for a specific repository.

    Args:
        repository: Repository name in format 'owner/repo' (e.g., 'facebook/react')
    """
    count = get_database_service().get_events_count_by_repo(repository)
    return {"repository": repository, "event_count": count}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
