import asyncio
import os

import asyncpg

ROLE_PROVISION_SQL = """
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'akademia_migrator') THEN
        CREATE ROLE akademia_migrator WITH LOGIN PASSWORD 'akademia_migrator_dev_pw' NOSUPERUSER NOCREATEDB NOCREATEROLE BYPASSRLS;
    ELSE
        ALTER ROLE akademia_migrator WITH BYPASSRLS;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'akademia_app') THEN
        CREATE ROLE akademia_app WITH LOGIN PASSWORD 'akademia_app_dev_pw' NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'akademia_worker') THEN
        CREATE ROLE akademia_worker WITH LOGIN PASSWORD 'akademia_worker_dev_pw' NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'akademia_readonly') THEN
        CREATE ROLE akademia_readonly WITH LOGIN PASSWORD 'akademia_readonly_dev_pw' NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
    END IF;
END
$$;
"""

DB_PRIVILEGES_SQL = """
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector";

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
"""


async def provision_databases(
    host: str = "127.0.0.1",
    port: int = 5436,
    superuser: str = "postgres",
    password: str = "postgres_dev_pw",
) -> None:
    conn = await asyncpg.connect(
        host=host,
        port=port,
        user=superuser,
        password=password,
        database="akademia_ai",
        ssl=False,
    )
    try:
        await conn.execute(ROLE_PROVISION_SQL)
        await conn.execute(
            "GRANT CONNECT ON DATABASE akademia_ai TO akademia_migrator, akademia_app, akademia_worker, akademia_readonly;"
        )
        await conn.execute(DB_PRIVILEGES_SQL)

        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = 'akademia_ai_test'"
        )
        if not exists:
            await conn.execute("CREATE DATABASE akademia_ai_test OWNER akademia_migrator")
    finally:
        await conn.close()

    test_conn = await asyncpg.connect(
        host=host,
        port=port,
        user=superuser,
        password=password,
        database="akademia_ai_test",
        ssl=False,
    )
    try:
        await test_conn.execute(
            "GRANT CONNECT ON DATABASE akademia_ai_test TO akademia_migrator, akademia_app, akademia_worker, akademia_readonly;"
        )
        await test_conn.execute(DB_PRIVILEGES_SQL)
    finally:
        await test_conn.close()


if __name__ == "__main__":
    pg_port = int(os.environ.get("POSTGRES_PORT", "5436"))
    asyncio.run(provision_databases(port=pg_port))
    print(f"Successfully provisioned roles, extensions, and databases on port {pg_port}.")
