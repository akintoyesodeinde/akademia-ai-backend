from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine


@pytest.mark.asyncio
async def test_rls_fails_closed_when_tenant_context_absent(
    app_role_engine: AsyncEngine,
) -> None:
    """Release-blocking test (Part 7.5):
    1. Missing tenant context returns no tenant-owned data.
    2. Missing tenant context blocks INSERT on tenant-owned tables.
    3. Tenant A cannot read, update, or delete Tenant B's records.
    4. Tenant A cannot reference Tenant B's parent records through composite foreign keys.
    5. Connection pooling does not leak transaction-local tenant context.
    """
    tenant_a = uuid4()
    tenant_b = uuid4()
    user_a = uuid4()
    user_b = uuid4()
    mem_a = uuid4()
    mem_b = uuid4()
    course_a = uuid4()
    course_b = uuid4()

    # 1. Seed Tenant A and Tenant B in their respective transaction-local contexts
    async with app_role_engine.begin() as conn:
        await conn.execute(
            text(
                """
                INSERT INTO tenants (id, name, slug, institution_type, status)
                VALUES (:ta, 'Alpha University', 'alpha-uni', 'university', 'active'),
                       (:tb, 'Beta Corp', 'beta-corp', 'corporate', 'active')
                """
            ),
            {"ta": tenant_a, "tb": tenant_b},
        )
        await conn.execute(
            text(
                """
                INSERT INTO users (id, email, full_name, password_hash, status)
                VALUES (:ua, 'owner@alpha.edu', 'Alpha Owner', 'hash1', 'active'),
                       (:ub, 'owner@beta.com', 'Beta Owner', 'hash2', 'active')
                """
            ),
            {"ua": user_a, "ub": user_b},
        )

        # Tenant A context
        await conn.execute(
            text("SELECT set_config('app.tenant_id', :tid, true)"),
            {"tid": str(tenant_a)},
        )
        await conn.execute(
            text(
                """
                INSERT INTO tenant_memberships (id, tenant_id, user_id, status)
                VALUES (:ma, :ta, :ua, 'active')
                """
            ),
            {"ma": mem_a, "ta": tenant_a, "ua": user_a},
        )
        await conn.execute(
            text(
                """
                INSERT INTO courses (id, tenant_id, code, title, status, created_by_membership_id)
                VALUES (:ca, :ta, 'CS101', 'Alpha Algorithms', 'draft', :ma)
                """
            ),
            {"ca": course_a, "ta": tenant_a, "ma": mem_a},
        )

        # Switch to Tenant B context
        await conn.execute(
            text("SELECT set_config('app.tenant_id', :tid, true)"),
            {"tid": str(tenant_b)},
        )
        await conn.execute(
            text(
                """
                INSERT INTO tenant_memberships (id, tenant_id, user_id, status)
                VALUES (:mb, :tb, :ub, 'active')
                """
            ),
            {"mb": mem_b, "tb": tenant_b, "ub": user_b},
        )
        await conn.execute(
            text(
                """
                INSERT INTO courses (id, tenant_id, code, title, status, created_by_membership_id)
                VALUES (:cb, :tb, 'SEC200', 'Beta Security', 'draft', :mb)
                """
            ),
            {"cb": course_b, "tb": tenant_b, "mb": mem_b},
        )

    # 2. New pooled connection with NO tenant context must return 0 rows (fail closed)
    async with app_role_engine.begin() as conn:
        current_ctx = (
            await conn.execute(text("SELECT NULLIF(current_setting('app.tenant_id', true), '')"))
        ).scalar_one_or_none()
        assert current_ctx is None

        courses_without_ctx = (
            await conn.execute(text("SELECT count(*) FROM courses"))
        ).scalar_one()
        memberships_without_ctx = (
            await conn.execute(text("SELECT count(*) FROM tenant_memberships"))
        ).scalar_one()
        assert int(courses_without_ctx) == 0
        assert int(memberships_without_ctx) == 0

    # 3. Attempting to INSERT into a tenant-owned table without tenant context is rejected by RLS
    with pytest.raises(DBAPIError):
        async with app_role_engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    INSERT INTO courses (id, tenant_id, code, title, status, created_by_membership_id)
                    VALUES (:cid, :ta, 'HACK1', 'Unauthorized Insert', 'draft', :ma)
                    """
                ),
                {"cid": uuid4(), "ta": tenant_a, "ma": mem_a},
            )

    # 4. In Tenant A context, Tenant B rows are completely invisible and immutable
    async with app_role_engine.begin() as conn:
        await conn.execute(
            text("SELECT set_config('app.tenant_id', :tid, true)"),
            {"tid": str(tenant_a)},
        )
        visible_courses = (
            await conn.execute(text("SELECT id, code FROM courses"))
        ).mappings().all()
        assert len(visible_courses) == 1
        assert visible_courses[0]["id"] == course_a

        # Attempt to UPDATE or DELETE Tenant B's course affects 0 rows
        upd = await conn.execute(
            text("UPDATE courses SET title = 'Pwned' WHERE id = :cb"),
            {"cb": course_b},
        )
        assert upd.rowcount == 0

        dele = await conn.execute(
            text("DELETE FROM courses WHERE id = :cb"),
            {"cb": course_b},
        )
        assert dele.rowcount == 0

    # 5. Tenant A cannot insert a row with tenant_id = Tenant B (RLS WITH CHECK failure)
    with pytest.raises(DBAPIError):
        async with app_role_engine.begin() as conn:
            await conn.execute(
                text("SELECT set_config('app.tenant_id', :tid, true)"),
                {"tid": str(tenant_a)},
            )
            await conn.execute(
                text(
                    """
                    INSERT INTO courses (id, tenant_id, code, title, status, created_by_membership_id)
                    VALUES (:cid, :tb, 'SPOOF', 'Spoofed Tenant Course', 'draft', :mb)
                    """
                ),
                {"cid": uuid4(), "tb": tenant_b, "mb": mem_b},
            )

    # 6. Tenant A cannot reference Tenant B's parent course_id via composite foreign key
    with pytest.raises((IntegrityError, DBAPIError)):
        async with app_role_engine.begin() as conn:
            await conn.execute(
                text("SELECT set_config('app.tenant_id', :tid, true)"),
                {"tid": str(tenant_a)},
            )
            await conn.execute(
                text(
                    """
                    INSERT INTO lessons (id, tenant_id, course_id, title, content_markdown, position, estimated_minutes)
                    VALUES (:lid, :ta, :cb, 'Cross-Tenant FK Attack', 'Content', 1, 10)
                    """
                ),
                {"lid": uuid4(), "ta": tenant_a, "cb": course_b},
            )
