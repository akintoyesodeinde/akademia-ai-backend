-- Akademia AI — PostgreSQL Runtime Role & Extension Provisioning
-- Pure SQL (no psql meta-commands) so Windows/Linux bind mounts are 100% line-ending agnostic.

CREATE ROLE akademia_migrator WITH LOGIN PASSWORD 'akademia_migrator_dev_pw' NOSUPERUSER CREATEDB NOCREATEROLE BYPASSRLS;
CREATE ROLE akademia_app WITH LOGIN PASSWORD 'akademia_app_dev_pw' NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
CREATE ROLE akademia_worker WITH LOGIN PASSWORD 'akademia_worker_dev_pw' NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
CREATE ROLE akademia_readonly WITH LOGIN PASSWORD 'akademia_readonly_dev_pw' NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;

CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector";

GRANT CONNECT ON DATABASE akademia_ai TO akademia_migrator, akademia_app, akademia_worker, akademia_readonly;
GRANT USAGE, CREATE ON SCHEMA public TO akademia_migrator;
GRANT USAGE ON SCHEMA public TO akademia_app, akademia_worker, akademia_readonly;

ALTER DEFAULT PRIVILEGES FOR ROLE akademia_migrator IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO akademia_app, akademia_worker;
ALTER DEFAULT PRIVILEGES FOR ROLE akademia_migrator IN SCHEMA public
    GRANT SELECT ON TABLES TO akademia_readonly;
ALTER DEFAULT PRIVILEGES FOR ROLE akademia_migrator IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO akademia_app, akademia_worker, akademia_readonly;

ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO akademia_app, akademia_worker;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
    GRANT SELECT ON TABLES TO akademia_readonly;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO akademia_app, akademia_worker, akademia_readonly;

CREATE DATABASE akademia_ai_test OWNER akademia_migrator;
GRANT CONNECT ON DATABASE akademia_ai_test TO akademia_migrator, akademia_app, akademia_worker, akademia_readonly;
