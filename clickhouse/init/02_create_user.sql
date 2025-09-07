-- Create application user and grant permissions
-- Separate from admin user for security

-- Create application user for the GitHub stats service
CREATE USER IF NOT EXISTS 'github_app_user' 
IDENTIFIED WITH plaintext_password BY 'github_app_pass';

-- Grant necessary permissions for the application
GRANT SELECT, INSERT ON github_stats.* TO 'github_app_user';

-- Grant specific permissions for materialized views
GRANT SELECT ON github_stats.pr_metrics_agg TO 'github_app_user';

-- Allow user to see system information for connection health checks
GRANT SELECT ON system.processes TO 'github_app_user';
GRANT SELECT ON system.query_log TO 'github_app_user';