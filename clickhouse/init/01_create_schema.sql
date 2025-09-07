-- GitHub Events Database Schema
-- Minimal design focused on assignment requirements and performance

CREATE DATABASE IF NOT EXISTS github_stats;

USE github_stats;

-- Core events table for GitHub API events
-- Stores only vital data required for assignment metrics
CREATE TABLE IF NOT EXISTS events (
    -- Event identification
    event_id String,                    -- GitHub event ID (unique identifier)
    event_type Enum8(                   -- Limited to assignment-required event types
        'WatchEvent' = 1,
        'PullRequestEvent' = 2, 
        'IssuesEvent' = 3
    ),
    
    -- Repository information
    repo_name String,                   -- Full repository name (owner/repo)
    repo_id UInt64,                     -- GitHub repository ID for joins
    
    -- Temporal data for metrics calculation
    created_at_ts DateTime64(3, 'UTC'), -- Event creation timestamp (microsecond precision)
    
    -- Event-specific data
    action LowCardinality(String),      -- Event action (opened, closed, etc.)
                                        -- NOTE: Kept for PR metrics - may need to filter 'opened' vs 'closed' events
    
    -- Insertion metadata
    ingested_at DateTime DEFAULT now()  -- When we stored this event
)
ENGINE = MergeTree()
-- Partition by date for time-based queries and efficient cleanup
PARTITION BY toYYYYMM(created_at_ts)
-- Primary key optimized for deduplication AND assignment queries:
-- 1. event_id first for fast deduplication lookups
-- 2. Repository-based queries (average PR times per repo)  
-- 3. Time-based queries (events by offset)
-- 4. Event type filtering
ORDER BY (event_id, repo_name, event_type, created_at_ts)
-- TTL for data cleanup (keep 1 year of data)
TTL created_at_ts + INTERVAL 1 YEAR;

-- Aggregated table for materialized view
CREATE TABLE IF NOT EXISTS pr_metrics_agg (
    repo_name String,
    hour_bucket DateTime,
    pr_count UInt32,
    first_pr_ts DateTime64(3, 'UTC'),
    last_pr_ts DateTime64(3, 'UTC')
)
ENGINE = SummingMergeTree()
PARTITION BY toYYYYMM(hour_bucket)
ORDER BY (repo_name, hour_bucket);

-- Materialized view for pull request metrics
-- Pre-aggregated data for faster "average time between PRs" calculation
CREATE MATERIALIZED VIEW IF NOT EXISTS pr_metrics_mv
TO pr_metrics_agg
AS SELECT 
    repo_name,
    toStartOfHour(created_at_ts) as hour_bucket,
    count() as pr_count,
    min(created_at_ts) as first_pr_ts,
    max(created_at_ts) as last_pr_ts
FROM events 
WHERE event_type = 'PullRequestEvent' 
  AND action = 'opened'
GROUP BY repo_name, hour_bucket;

-- Index for faster event type + time range queries
-- Optimizes the "events by offset" assignment requirement
ALTER TABLE events ADD INDEX idx_event_time_type (event_type, created_at_ts) TYPE minmax GRANULARITY 4;

-- Comments explaining design decisions:
--
-- 1. MergeTree Engine: Best for time-series data, supports efficient inserts and range queries
-- 2. Partition by month: Enables efficient data lifecycle management and query pruning  
-- 3. Primary key design: Optimized for both assignment requirements (repo queries, time queries)
-- 4. Enum for event_type: Memory efficient, only allows valid assignment events
-- 5. DateTime64 with UTC: Precise timestamps needed for time calculations
-- 6. LowCardinality for action: Memory optimization for repeated values
-- 7. Materialized view: Pre-calculates PR metrics for faster API responses
-- 8. TTL policy: Automatic data cleanup to prevent unbounded growth
-- 9. MinMax index: Accelerates time-range queries for offset-based metrics
