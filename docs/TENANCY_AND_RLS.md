# Akademia AI — Multi-Tenancy & PostgreSQL Row-Level Security (`TENANCY_AND_RLS.md`)

## 1. Defense-in-Depth Isolation Model

Akademia AI implements a **Shared Database, Shared Schema with Mandatory Row-Level Security (RLS)** isolation model. Every tenant-owned record is protected by three independent layers:

1. **Application Authorization Layer (`app/api/dependencies.py`)**:
   - Resolves `PrincipalContext` from a signed JWT and verifies an active `TenantMembership` row in PostgreSQL.
   - Browser-supplied tenant headers or payload fields are never trusted as proof of membership; switching tenants requires calling `POST /api/v1/auth/switch-tenant`, which verifies membership before issuing a new tenant-scoped JWT.
2. **Composite Relational Integrity Layer (`migrations/versions/001..012`)**:
   - Parent tables expose `UNIQUE (tenant_id, id)` and child tables enforce `FOREIGN KEY (tenant_id, parent_id)`. Cross-tenant relational links are rejected by PostgreSQL foreign-key constraints.
3. **Database Storage Engine Layer (PostgreSQL RLS)**:
   - Every one of the 52 tenant-owned tables listed in `TENANT_OWNED_TABLES` (`app/db/rls.py`) has both `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY` enabled.
   - Policy definition (`app/db/rls.py`):
     ```sql
     ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY;
     ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY;
     CREATE POLICY "{table}_tenant_isolation_policy" ON "{table}"
         AS PERMISSIVE FOR ALL
         USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
         WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
     ```

---

## 2. Least-Privilege Database Roles (`scripts/init-db-roles.sql`)

| Role | Privileges | Purpose |
|---|---|---|
| `akademia_migrator` | Schema DDL owner | Used strictly by `alembic upgrade head` during deployment migrations |
| `akademia_app` | `NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS` | Used by FastAPI runtime (`DATABASE_URL`). Subject to all RLS policies |
| `akademia_worker` | `NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS` | Used by background worker processes (`WORKER_DATABASE_URL`). Subject to all RLS policies |
| `akademia_readonly` | `SELECT` only + `NOBYPASSRLS` | Used for diagnostics/reporting within a verified tenant context |

---

## 3. Transaction-Local Context & Connection Pool Safety

- In `app/db/session.py` and `app/db/tenant_context.py`, every database session begins by clearing `app.tenant_id` (`SELECT set_config('app.tenant_id', '', true)`).
- When a tenant-scoped request or worker job executes, `set_tenant_context(session, tenant_id)` runs `SELECT set_config('app.tenant_id', :tenant_id, true)` where the third argument `is_local = true` guarantees the setting is automatically cleared when the transaction commits or rolls back.
- Even if a pooled connection is reused across consecutive requests for different tenants, no tenant context can bleed across transactions.
- If `app.tenant_id` is unset or empty, `NULLIF(current_setting('app.tenant_id', true), '')::uuid` evaluates to `NULL`, causing `SELECT` queries to return `0` rows (fail-closed) and `INSERT`/`UPDATE` statements to fail the `WITH CHECK` clause.
