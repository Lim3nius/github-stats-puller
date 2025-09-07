# Architecture Overview

## System Architecture

The GitHub Events Statistics Puller is a Python application that monitors GitHub public events and provides REST API metrics. The system follows a layered architecture with clear separation of concerns.

### High-Level Components

```txt
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   GitHub API    │    │  FastAPI Server │    │   Client Apps   │
│                 │    │                 │    │                 │
└─────────┬───────┘    └─────────┬───────┘    └─────────────────┘
          │                      │
          │ HTTP Events          │ REST API
          │                      │
┌─────────▼───────┐    ┌─────────▼───────┐
│ GitHubClient    │    │   Server API    │
│ (Polling)       │    │   Endpoints     │
└─────────┬───────┘    └─────────┬───────┘
          │                      │
          │ Filtered Events      │ Query/Debug
          │                      │
┌─────────▼─────────────────────▼───────┐
│         DatabaseService               │
│      (Abstraction Layer)              │
└─────────┬───────────────────────────────┘
          │
          │ SQL Queries
          │
┌─────────▼───────┐
│   ClickHouse    │
│   Database      │
└─────────────────┘
```

## Data Flow

### 1. Event Ingestion

- **GitHubClient** polls GitHub Events API every 60 seconds
- Downloads all public events (typically ~300 events per poll)
- Saves complete raw events to JSON files (`downloaded-events/YYYY-MM-DDTHH-MM-SS.json`)
- Filters events for relevant types: `WatchEvent`, `PullRequestEvent`, `IssuesEvent`
- Extracts vital data and stores in ClickHouse via **DatabaseService**

### 2. Data Storage Strategy

- **Raw Data**: Complete JSON files for audit trail and debugging
- **Analytics Data**: Only vital fields stored in ClickHouse for performance
  - `repo_name`: Repository identifier
  - `event_type`: WatchEvent, PullRequestEvent, IssuesEvent
  - `created_at`: Event timestamp
  - `action`: Event action (opened, closed, etc.) for PR/Issues events

### 3. API Layer

- **FastAPI Server** provides REST endpoints for metrics
- All database access goes through **DatabaseService** abstraction
- No direct ClickHouse queries in API endpoints

## Component Details

### GitHubClient (github_stats/client.py)

**Responsibilities:**

- GitHub API authentication and rate limiting via PyGitHub
- Time-based polling with intelligent scheduling
- Event polling with configurable intervals
- Raw event persistence to JSON files
- Filtered event forwarding to DatabaseService

**Key Features:**

- PyGitHub-based rate limit monitoring with conservative thresholds
- Time-based state persistence via `client-state.json` for restart resilience
- Intelligent polling scheduling (avoids immediate polling on restart)
- Thread-safe operation

**Rate Limiting Strategy:**

- Uses `github.get_rate_limit()` to check API limits before each poll
- Conservative threshold: sleeps when < 10 requests remaining
- Respects rate limit reset times with buffer

**State Management:**

- Persists `next_poll_time_ts`, `poll_interval_sec`, `last_successful_poll_ts` in `client-state.json`
- On startup: polls immediately if `next_poll_time_ts` has passed, otherwise waits
- After each poll: schedules next poll based on interval
- No ETag functionality (PyGitHub limitation)

### DatabaseService (github_stats/database.py)

**Responsibilities:**

- Abstract interface between application and ClickHouse
- Data insertion with batch processing
- Query methods for metrics calculation
- Debugging and monitoring methods

**Core Methods:**

- `store_events(vital_events)` - Insert filtered event data
- `get_pr_metrics(repo, timeframe)` - Average time between PRs
- `get_event_counts(offset_minutes)` - Event counts by type
- `get_project_count()` - Total unique repositories
- `get_event_count_per_project(project)` - Events per repository
- `get_event_count_per_project_by_type(project, type)` - Specific counts
- `backfill_from_json_files(events_dir)` - Historical data import

### FastAPI Server (github_stats/server.py)

**Responsibilities:**

- REST API endpoint implementation
- Request validation and response formatting
- OpenAPI specification generation

**API Endpoints:**

- `GET /metrics/pr-average/{repository}` - PR timing metrics
- `GET /metrics/events?offset=N` - Event counts with time filtering
- `GET /metrics/visualization` - Data for charts/graphs
- `GET /debug/projects/count` - Repository count
- `GET /debug/projects/{project}/events/count` - Project event count
- `GET /debug/projects/{project}/events/{type}/count` - Specific event counts

### Application Orchestration (github_stats/app.py)

**Responsibilities:**

- Thread management for concurrent client/server operation
- Configuration loading and logging setup
- Graceful startup and shutdown handling

**Execution Model:**

- Client runs in background daemon thread
- Server runs in main thread
- Shared DatabaseService instance for data access

## Deployment Architecture

### Development Environment

```
┌─────────────────────────────────────┐
│           Host Machine              │
│                                     │
│  ┌─────────────────┐               │
│  │ github_stats    │               │
│  │ Application     │               │
│  │ (Python)        │               │
│  └─────────┬───────┘               │
│            │                       │
│            │ TCP:9000              │
│            │                       │
│  ┌─────────▼───────┐               │
│  │   ClickHouse    │               │
│  │  (Docker)       │               │
│  │  Port: 8123     │               │
│  └─────────────────┘               │
└─────────────────────────────────────┘
```

### Production Considerations

- Both application and ClickHouse can be containerized
- Volume mounts for persistent data storage
- Environment-based configuration
- Health checks and monitoring endpoints

## Data Schema

### ClickHouse Table: `github_events`

```sql
CREATE TABLE github_events (
    repo_name String,
    event_type Enum8('WatchEvent'=1, 'PullRequestEvent'=2, 'IssuesEvent'=3),
    created_at DateTime64(3),
    action LowCardinality(String),
    inserted_at DateTime64(3) DEFAULT now64()
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(created_at)
ORDER BY (repo_name, event_type, created_at);
```

**Design Principles:**

- Time-based partitioning for efficient queries
- Enum types for event_type to save space
- LowCardinality for action field optimization
- Insertion timestamp for debugging and monitoring

## Configuration

### Environment Variables

- `GITHUB_TOKEN` - GitHub API authentication (optional but recommended)
- `LOG_LEVEL` - Logging verbosity (DEBUG, INFO, WARN, ERROR)
- `CLICKHOUSE_HOST` - Database host (default: localhost)
- `CLICKHOUSE_PORT` - Database port (default: 9000)
- `CLICKHOUSE_DATABASE` - Database name (default: github_stats)

### Application Entry Points

- `uv run python -m github_stats` - Full application (client + server) - **PRIMARY METHOD**
- Module-based execution following Python best practices
- Absolute imports throughout codebase
- Legacy entry points removed in favor of module execution

## Monitoring and Debugging

### Logging Strategy

- Structured logging with loguru
- Configurable log levels via environment
- Request/response logging for API endpoints
- Database query logging for performance monitoring

### Health Checks

- Database connectivity verification
- GitHub API rate limit monitoring
- Event processing throughput tracking
- Memory usage for in-flight data

### Debugging Endpoints

- Repository statistics for data verification
- Event count validation
- Historical data integrity checks
