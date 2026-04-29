-- ============================================================
-- PostgreSQL extensions required by DFIR-IRIS
-- This file is auto-executed by the postgres image entrypoint
-- BEFORE the IRIS init scripts (10-create_user.sh etc.)
-- Mounted as: /docker-entrypoint-initdb.d/00-extensions.sql
-- ============================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- provides gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS "uuid-ossp"; -- provides uuid_generate_v4()
