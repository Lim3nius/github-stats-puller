# GitHub API Stats Puller

A Python service that streams GitHub events and provides REST API metrics with ClickHouse storage backend.

## Features

- **Real-time GitHub Events Streaming**: Polls GitHub Events API with smart ETag caching and rate limiting
- **Event Filtering**: Focuses on WatchEvent, PullRequestEvent, and IssuesEvent
- **REST API Metrics**: Calculate average PR times, event counts by type, and visualizations  
- **ClickHouse Integration**: High-performance database backend for event storage
- **Persistent State**: Maintains client state and respects GitHub API rate limits across restarts
- **Docker Support**: Full containerization with docker-compose orchestration

## Quick Start with Docker Compose

### Prerequisites

- Docker and Docker Compose installed
- Optional: GitHub Personal Access Token for higher rate limits

### Setup

1. **Clone and setup environment**:

   ```bash
   git clone <repository-url>
   cd github-api-stats-puller
   
   # Optional: Set GitHub token for higher rate limits
   export GITHUB_READ_TOKEN=your_token_here
   ```

2. **Build and run services**:

   ```bash
   docker-compose build
   docker-compose up -d
   ```

3. **Verify services are running**:

   ```bash
   docker-compose ps
   docker-compose logs github-stats
   ```

### API Endpoints

Once running, the API is available at `http://localhost:8000`:

- **API Documentation**: `GET /docs` - Interactive Swagger/OpenAPI documentation
- **Health Check**: `GET /health`
- **Event Metrics**: `GET /metrics/events?offset=60` - Event counts by type for last 60 minutes
- **PR Metrics**: `GET /metrics/pullrequest/{repo}` - Average time between PRs for repository
- **Visualization**: `GET /visualization` - Interactive charts and data insights

### Debug Endpoints

- `GET /debug/health` - Database connection status
- `GET /debug/events` - Total events count 
- `GET /debug/events/{repo}` - Events count for specific repository

## Local Development

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager

### Setup

1. **Install dependencies**:
   ```bash
   uv sync
   ```

2. **Start ClickHouse (optional)**:
   ```bash
   docker-compose up clickhouse -d
   ```

3. **Run locally**:
   ```bash
   # With in-memory storage
   uv run -m github_stats
   
   # With ClickHouse backend
   export DATABASE_BACKEND=clickhouse
   uv run -m github_stats
   ```

## Configuration

### Environment Variables

| Variable              | Default           | Description                                |
|-----------------------|-------------------|--------------------------------------------|
| `GITHUB_READ_TOKEN`   | -                 | GitHub Personal Access Token (recommended) |
| `DATABASE_BACKEND`    | `memory`          | Backend type: `memory` or `clickhouse`     |
| `CLICKHOUSE_HOST`     | `localhost`       | ClickHouse server host                     |
| `CLICKHOUSE_PORT`     | `9000`            | ClickHouse native protocol port            |
| `CLICKHOUSE_USER`     | `github_user`     | ClickHouse username                        |
| `CLICKHOUSE_PASSWORD` | `github_pass`     | ClickHouse password                        |
| `CLICKHOUSE_DATABASE` | `github_stats`    | ClickHouse database name                   |
| `LOG_LEVEL`           | `INFO`            | Logging level                              |

### Docker Volumes

- `github_events_data`: Persists downloaded GitHub events
- `github_client_state`: Maintains API polling state and ETags
- `clickhouse_data`: ClickHouse database storage

## Architecture

The application consists of:

- **GitHub Events Client**: Polls GitHub Events API with intelligent caching
- **FastAPI Server**: Provides REST API endpoints for metrics
- **ClickHouse Database**: High-performance analytics database
- **DatabaseService Abstraction**: Pluggable storage backends

Main architecture overview is in [ACHITECTURE.md](/ARCHITECTURE.md)

## Data Persistence

- **Events**: Raw GitHub events stored in ClickHouse and JSON backup files
- **Client State**: ETag, poll intervals, and next poll time persisted across restarts
- **Rate Limiting**: Respects GitHub API X-Poll-Interval headers

## Stopping Services

```bash
# Stop services but keep data
docker-compose down

# Stop and remove all data (destructive)
docker-compose down -v
```

## Troubleshooting

- **Database connection issues**: Check ClickHouse logs with `docker-compose logs clickhouse`
- **API rate limits**: Add `GITHUB_READ_TOKEN` environment variable
- **Service health**: Visit `http://localhost:8000/health` for status


## Github API links

- [Events REST API](https://docs.github.com/en/rest/activity/events?apiVersion=2022-11-28)
- [Event Types](https://docs.github.com/en/rest/using-the-rest-api/github-event-types?apiVersion=2022-11-28)
