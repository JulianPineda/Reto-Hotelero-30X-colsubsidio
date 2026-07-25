-- PostgreSQL initialization script
-- Run once at container creation

CREATE EXTENSION IF NOT EXISTS "pgcrypto";    -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS "pg_trgm";     -- full-text fuzzy search fallback
CREATE EXTENSION IF NOT EXISTS "unaccent";    -- handle accented chars in Spanish
