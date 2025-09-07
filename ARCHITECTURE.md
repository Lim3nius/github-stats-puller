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
- **Optionally** saves complete raw events to JSON files (`downloaded-events/YYYY-MM-DDTHH-MM-SS.json`)
- Filters events for relevant types: `WatchEvent`, `PullRequestEvent`, `IssuesEvent`
- Extracts vital data and stores in ClickHouse via **DatabaseService**

### 2. Data Storage Strategy

- **Raw Data**: Optional JSON files for audit trail and debugging (configurable via `SAVE_EVENTS_TO_FILES`)
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
- Event forwarding to DatabaseService (deduplication handled by database layer)

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

### DatabaseService (github_stats/stores/)

**Responsibilities:**

- Abstract interface between application and storage backends
- Pluggable architecture supporting multiple backends (in-memory, ClickHouse)
- Optimized queries using pre-aggregated data
- Minimal data fetching for better performance

**Implementation Details:**

- **ClickHouseDatabaseService**: Production backend using ClickHouse
  - Uses pre-aggregated `pr_metrics_agg` table for PR calculations
  - Fetches only required fields (e.g., timestamps) to minimize data transfer
  - **Two-Level Deduplication**: 
    1. Batch-level: Removes duplicates within incoming event batches
    2. Database-level: Checks existing event_ids before insert to keep oldest version
  - **Performance**: ~1-3% overhead per batch, ~1-5ms duplicate lookups
  - Fallback to raw events table if aggregated data unavailable
- **InMemoryDatabaseService**: Development/testing backend with thread-safe operations

**Core Methods:**

- `insert_events(events)` - Insert filtered event data
- `calculate_avg_pr_time(repo)` - Uses pre-aggregated data for fast PR metrics
- `get_events_by_type_and_offset(minutes)` - Optimized event counts by type
- `get_health_status()` - Database connection and health monitoring
- `get_pull_request_events_for_repo(repo)` - Minimal data fetch (timestamps only)

### FastAPI Server (github_stats/server.py)

**Responsibilities:**

- REST API endpoint implementation
- Request validation and response formatting
- OpenAPI specification generation
- HTTP access logging via middleware

**Middleware Architecture:**

- Transparent middleware chain configuration
- Access logging middleware for all HTTP requests
- Extensible design for adding authentication, rate limiting, etc.

**API Endpoints:**

- `GET /metrics/pr-average/{repository:path}` - PR timing metrics (supports owner/repo format)
- `GET /metrics/events?offset=N` - Event counts with time filtering
- `GET /metrics/visualization` - Data for charts/graphs
- `GET /health` - Database health and connection status
- `GET /debug/total-events` - Total event count
- `GET /debug/repo-events/{repository:path}` - Repository event count

### Backfill Tool (github_stats/backfill.py)

**Responsibilities:**

- Historical data migration from JSON files to ClickHouse database
- Batch processing of saved event files with progress tracking
- Environment configuration via dotenv support (defaults to `gh.env`)
- ClickHouse-specific data population and validation

**Key Features:**

- **ClickHouse-Only Operation**: Validates database backend and rejects in-memory storage
- **Batch Processing**: Processes all JSON files in chronological order
- **Two-Level Deduplication**: Same strategy as real-time processing
- **Environment Integration**: Loads ClickHouse credentials from `.env` files
- **Progress Tracking**: Detailed logging and statistics reporting
- **Error Resilience**: Individual file failures don't stop the entire process

**Usage Scenarios:**

- Initial database population from historical JSON files
- Data recovery after database issues or corruption
- Development environment setup with realistic test data
- Historical data import for analytics and reporting

**Command Interface:**

- `uv run backfill_events.py` - Process all JSON files
- `uv run backfill_events.py --dry-run` - Preview processing without insertion
- `uv run backfill_events.py --dotenv custom.env` - Use custom environment file

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

### ClickHouse Tables

#### Main Events Table: `events`

```sql
CREATE TABLE events (
    event_id String,
    event_type Enum8('WatchEvent'=1, 'PullRequestEvent'=2, 'IssuesEvent'=3),
    repo_name String,
    repo_id UInt64,
    created_at_ts DateTime64(3, 'UTC'),
    action LowCardinality(String),
    ingested_at DateTime DEFAULT now()
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(created_at_ts)
ORDER BY (repo_name, event_type, created_at_ts);
```

#### Pre-Aggregated PR Metrics: `pr_metrics_agg`

```sql
CREATE TABLE pr_metrics_agg (
    repo_name String,
    hour_bucket DateTime,
    pr_count UInt32,
    first_pr_ts DateTime64(3, 'UTC'),
    last_pr_ts DateTime64(3, 'UTC')
) ENGINE = SummingMergeTree()
PARTITION BY toYYYYMM(hour_bucket)
ORDER BY (repo_name, hour_bucket);
```

#### Materialized View: `pr_metrics_mv`

Automatically populates `pr_metrics_agg` from new events:
- Filters for `PullRequestEvent` with `action = 'opened'`
- Aggregates into hourly buckets for efficient queries
- Maintains running totals and time boundaries

**Design Principles:**

- Time-based partitioning for efficient queries
- Pre-aggregated data for faster PR metrics calculation
- Materialized views for automatic aggregation
- Enum types for event_type to save space
- LowCardinality for action field optimization
- **Deduplication-optimized primary key**: `event_id` first in ORDER BY for fast duplicate lookups (~1-5ms)
- **Application-level deduplication**: Keeps oldest version of duplicate events

## Data Quality & Deduplication

### Duplicate Prevention Strategy

**Problem**: GitHub API may return duplicate events in overlapping polls, leading to inflated metrics.

**Solution**: Centralized two-layer deduplication in ClickHouse database service:

1. **Batch-Level Deduplication**:
   - Removes duplicates within each incoming event batch using `event_id_map`
   - Keeps oldest event when multiple events share the same ID
   - Reduces database queries by eliminating obvious duplicates first

2. **Database-Level Deduplication**:
   - Schema optimization: `ORDER BY (event_id, repo_name, event_type, created_at_ts)`
   - Places `event_id` first for optimal duplicate lookup performance (~1-5ms)
   - Before each insert: `SELECT DISTINCT event_id FROM events WHERE event_id IN (...)`
   - Filters out existing events to keep oldest version only
   - ~1-3% performance overhead per 300-event batch
   - Graceful fallback if duplicate check fails

**Architecture Benefits**:
- **Centralized Logic**: All deduplication handled in ClickHouse service layer
- **Consistent Strategy**: Same approach for real-time polling and historical backfill
- **Performance Optimized**: Batch-level deduplication reduces database load
- **Maintainable**: Single location for deduplication logic and policies

**Benefits**:
- Guaranteed data accuracy for metrics calculations
- Predictable "oldest wins" deduplication policy  
- Fast duplicate detection using primary key optimization
- Minimal performance impact on polling cycle
- Consistent behavior across all data ingestion paths

## Configuration

### Environment Variables

- `GITHUB_TOKEN` - GitHub API authentication (optional but recommended)
- `LOG_LEVEL` - Logging verbosity (DEBUG, INFO, WARN, ERROR)
- `CLICKHOUSE_HOST` - Database host (default: localhost)
- `CLICKHOUSE_PORT` - Database port (default: 9000)
- `CLICKHOUSE_DATABASE` - Database name (default: github_stats)

### Application Entry Points

- `uv run python -m github_stats` - Full application (client + server) - **PRIMARY METHOD**
- `uv run backfill_events.py` - Historical data backfill tool - **ClickHouse ONLY**
- Module-based execution following Python best practices
- Absolute imports throughout codebase
- Legacy entry points removed in favor of module execution

### Backfill Tool Configuration

- `--dotenv PATH` - Environment file path (default: `gh.env`)
- `--events-dir PATH` - JSON files directory (default: `downloaded-events`)  
- `--dry-run` - Preview processing without database changes
- Requires `DATABASE_BACKEND=clickhouse` environment variable
- Uses same ClickHouse configuration as main application

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
