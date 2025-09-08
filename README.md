# GitHub API Stats Puller

A Python service that streams GitHub events and provides REST API metrics with ClickHouse storage backend.

## Features

- **Real-time GitHub Events Streaming**: Polls GitHub Events API with smart ETag caching and rate limiting
- **Event Filtering**: Focuses on WatchEvent, PullRequestEvent, and IssuesEvent
- **REST API Metrics**: Calculate average PR times and event counts by type
- **ClickHouse Integration**: High-performance async database backend with connection pooling
- **Persistent State**: Maintains client state and respects GitHub API rate limits across restarts
- **Docker Support**: Full containerization with docker-compose orchestration

## Setup

### Using Docker

#### Prerequisites

- Docker and Docker Compose installed
- Optional: GitHub Personal Access Token for higher rate limits

#### Steps

1. **Clone and setup environment**:

   ```bash
   git clone <repository-url>
   cd github-api-stats-puller
   
   # Optional: Set GitHub token for higher rate limits
   export GITHUB_READ_TOKEN=your_token_here
   ```

2. **Build and run services**:

   ```bash
   docker compose build
   docker compose up -d
   ```

   ⚠️ depending on docker/podman version, might need to use directly `docker-compose` ⚠️

3. **Verify services are running**:

   ```bash
   docker compose ps
   docker compose logs github-stats
   ```

### Local script, DB in compose

#### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- Docker and Docker Compose installed
- Optional: GitHub Personal Access Token for higher rate limits

#### Steps

1. **Install dependencies**:

   ```bash
   uv sync
   ```

2. **Start ClickHouse (optional)**:

   ```bash
   docker compose up clickhouse -d
   ```

3. **Run locally**:

   ```bash
   # With ClickHouse backend
   export DATABASE_BACKEND=clickhouse
   uv run -m github_stats
   ```

## API

### API Endpoints

Once running, the API is available at `http://localhost:8000`:

- **API Documentation**: `GET /docs` - Interactive Swagger/OpenAPI documentation
- **Health Check**: `GET /health`
- **Event Metrics**: `GET /metrics/events?offset=60` - Event counts by type for last 60 minutes
- **PR Metrics**: `GET /metrics/pullrequest/{repo}` - Average time between PRs for repository

** Full documentation via OpenAPI specs is available on [http://localhost:8000/docs](http://localhost:8000/docs)

### Debug Endpoints

I created some events which helped me debug peculiarities and bugs.

- `GET /health` - Database connection status with overview
- `GET /debug/agg-repo-events/{repository}` - Returns aggregated events count for specified repository
- `GET /debug/list-repo-events/{repository:path}` - Returns list of known events for given repository
- `GET /debug/repos-by-event-count` - Returns list of N repositories with most events


## Configuration

### Environment Variables

| Variable               | Default             | Description                                |
|------------------------|---------------------|--------------------------------------------|
| `GITHUB_READ_TOKEN`    | -                   | GitHub Personal Access Token (recommended) |
| `SAVE_EVENTS_TO_FILES` | `true`              | Save events to JSON files (`true`/`false`) |
| `EVENTS_DIRECTORY`     | `downloaded-events` | Directory for JSON event files             |
| `DATABASE_BACKEND`     | `memory`            | Backend type: `memory` or `clickhouse`     |
| `CLICKHOUSE_HOST`      | `localhost`         | ClickHouse server host                     |
| `CLICKHOUSE_PORT`      | `9000`              | ClickHouse native protocol port            |
| `CLICKHOUSE_USER`      | `github_user`       | ClickHouse username                        |
| `CLICKHOUSE_PASSWORD`  | `github_pass`       | ClickHouse password                        |
| `CLICKHOUSE_DATABASE`  | `github_stats`      | ClickHouse database name                   |
| `LOG_LEVEL`            | `INFO`              | Logging level                              |

### Docker Volumes

- `github_events_data`: Persists downloaded GitHub events
- `github_client_state`: Maintains API polling state and ETags
- `clickhouse_data`: ClickHouse database storage

## Architecture

The application consists of:

- **GitHub Events Client**: Polls GitHub Events API with intelligent caching
- **FastAPI Server**: Provides async REST API endpoints for metrics
- **ClickHouse Database**: High-performance analytics database with async operations
- **DatabaseService Abstraction**: Pluggable async storage backends with thread-safe connection pooling

Main architecture overview is in [ACHITECTURE.md](/ARCHITECTURE.md)

## Data Persistence

- **Events**: Raw GitHub events stored in ClickHouse and JSON backup files
- **Client State**: ETag, poll intervals, and next poll time persisted across restarts
- **Rate Limiting**: Respects GitHub API X-Poll-Interval headers

## Backfill Tool

The project includes a backfill tool to populate the ClickHouse database from existing JSON event files:

### Prerequisites

The backfill tool requires ClickHouse database backend:

```bash
# Ensure ClickHouse is running
docker-compose up clickhouse -d

# Set ClickHouse backend
export DATABASE_BACKEND=clickhouse
```

### Usage

```bash
# Dry run to see what would be processed
uv run backfill_events.py --dry-run

# Process and insert events into ClickHouse database
uv run backfill_events.py

# Specify custom events directory
uv run backfill_events.py --events-dir /path/to/events

# Use custom .env file (defaults to gh.env)
uv run backfill_events.py --dotenv .env.production
```

### Features

- **ClickHouse Integration**: Designed specifically for ClickHouse database backend
- **Environment Configuration**: Loads settings from `gh.env` file by default
- **Batch Processing**: Processes all JSON files in the events directory
- **Event Filtering**: Only processes WatchEvent, PullRequestEvent, and IssuesEvent
- **Deduplication**: Automatically skips duplicate events (keeps oldest version)
- **Progress Tracking**: Shows detailed processing statistics
- **Error Resilience**: Individual file failures don't stop the entire process

### Use Cases

- **Initial Database Population**: Load historical events from saved JSON files into ClickHouse
- **Data Recovery**: Restore events after ClickHouse database issues
- **Development/Testing**: Populate ClickHouse test databases with real event data
- **Historical Data Import**: Bulk import large amounts of historical GitHub event data

**Note**: The backfill tool only works with ClickHouse backend and will exit with an error if run with in-memory storage.

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
