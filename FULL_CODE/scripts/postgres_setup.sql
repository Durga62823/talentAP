-- SentinelMask PostgreSQL demo setup (run as a superuser / database owner).
--   psql -h localhost -U postgres -v app_password="'choose-a-password'" -f scripts/postgres_setup.sql
-- Creates the demo database and a least-privilege application role:
--   * SELECT on the official dataset tables (protected queries also run inside READ ONLY transactions)
--   * CREATE on schema public, only so reviewed CSV imports can create new tables
-- No superuser, no access to other databases.

SELECT 'CREATE DATABASE saffron_bank' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'saffron_bank')\gexec

DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'sentinel_app') THEN
    CREATE ROLE sentinel_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
  END IF;
END$$;
ALTER ROLE sentinel_app PASSWORD :app_password;

\connect saffron_bank
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT CONNECT ON DATABASE saffron_bank TO sentinel_app;
GRANT USAGE, CREATE ON SCHEMA public TO sentinel_app;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO sentinel_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO sentinel_app;
