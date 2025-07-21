-- CodeSage Database Initialization Script
-- This script runs when the PostgreSQL container is first created

-- Set timezone
SET timezone = 'UTC';

-- Create extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Create full-text search configuration for code
-- This will help with better text search performance
CREATE TEXT SEARCH CONFIGURATION code_search (COPY = english);

-- Create a function to update updated_at timestamps
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Grant necessary permissions
GRANT ALL PRIVILEGES ON DATABASE codesage TO codesage;

-- Create schema for future use
CREATE SCHEMA IF NOT EXISTS analytics;