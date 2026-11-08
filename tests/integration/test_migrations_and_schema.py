import pytest
from app.db.rls import TENANT_OWNED_TABLES
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


@pytest.mark.asyncio
async def test_runtime_database_role_is_least_privilege(
    app_role_engine: AsyncEngine,
) -> None:
    """Verify Part 3.5 & Part 7.1: Runtime application role is neither superuser nor BYPASSRLS."""
    async with app_role_engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    """
                    SELECT rolname, rolsuper, rolbypassrls, rolcreatedb, rolcreaterole
                    FROM pg_roles
                    WHERE rolname = current_user
                    """
                )
            )
        ).mappings().one()
        assert row["rolname"] == "akademia_app"
        assert row["rolsuper"] is False
        assert row["rolbypassrls"] is False
        assert row["rolcreatedb"] is False
        assert row["rolcreaterole"] is False


@pytest.mark.asyncio
async def test_all_tenant_owned_tables_enforce_rls(
    app_role_engine: AsyncEngine,
) -> None:
    """Verify Part 7.3: Every tenant-owned table has ENABLE and FORCE ROW LEVEL SECURITY."""
    async with app_role_engine.connect() as conn:
        for table_name in TENANT_OWNED_TABLES:
            row = (
                await conn.execute(
                    text(
                        """
                        SELECT relname, relrowsecurity, relforcerowsecurity
                        FROM pg_class
                        WHERE relname = :tname AND relkind = 'r'
                        """
                    ),
                    {"tname": table_name},
                )
            ).mappings().one_or_none()
            assert row is not None, f"Table '{table_name}' is missing from database schema"
            assert row["relrowsecurity"] is True, f"RLS not enabled on '{table_name}'"
            assert row["relforcerowsecurity"] is True, f"FORCE RLS not enabled on '{table_name}'"

            pol_count = (
                await conn.execute(
                    text(
                        "SELECT count(*) FROM pg_policies WHERE tablename = :tname"
                    ),
                    {"tname": table_name},
                )
            ).scalar_one()
            assert int(pol_count) >= 1, f"No RLS policy defined on '{table_name}'"
