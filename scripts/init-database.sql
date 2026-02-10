-- =============================================================================
-- Database Initialization Script for Integration Platform
-- =============================================================================
-- This script should be run by a DBA with master/admin access to the RDS instance.
-- It creates the database and application user with appropriate permissions.
--
-- Prerequisites:
--   - PostgreSQL 15+ RDS instance
--   - Master/admin credentials with CREATE DATABASE and CREATE ROLE permissions
--
-- Usage:
--   psql -h <rds-endpoint> -U postgres -f init-database.sql
--
-- After running this script:
--   1. Update the DATABASE_URL secret in AWS Secrets Manager with:
--      postgresql+asyncpg://<db_user>:<db_password>@<rds-endpoint>:5432/<db_name>
--   2. Run Alembic migrations from the application
-- =============================================================================

-- Configuration (modify these values as needed)
\set db_name 'integration_platform'
\set db_user 'integration_platform'
-- Generate a secure password or set your own:
\set db_password 'CHANGE_ME_TO_SECURE_PASSWORD'

-- Create database if it doesn't exist
SELECT 'CREATE DATABASE ' || :'db_name'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = :'db_name')\gexec

-- Connect to the new database
\c :db_name

-- Create application user if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'db_user') THEN
        EXECUTE format('CREATE ROLE %I WITH LOGIN PASSWORD %L', :'db_user', :'db_password');
    END IF;
END
$$;

-- Grant permissions
GRANT CONNECT ON DATABASE :db_name TO :db_user;
GRANT USAGE ON SCHEMA public TO :db_user;
GRANT CREATE ON SCHEMA public TO :db_user;

-- Grant permissions on existing tables (if any)
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO :db_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO :db_user;

-- Set default privileges for future tables
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO :db_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO :db_user;

-- Verify setup
\echo ''
\echo '=== Database Setup Complete ==='
\echo 'Database:' :db_name
\echo 'User:' :db_user
\echo ''
\echo 'Next steps:'
\echo '1. Update DATABASE_URL secret in AWS Secrets Manager'
\echo '2. Run: alembic upgrade head'
\echo ''
