# Backend Implementation Status (`akademia-ai-backend`)

## 1. Repository & Stack Overview

- **Repository Root**: `c:\Users\LENOVO\AkademiaAI\akademia-ai-backend`
- **Architecture**: Modular Monolith with strict module boundaries (`app/modules/*`), provider-neutral Generative AI (`app/ai/*`), transaction-local PostgreSQL Row-Level Security (`app/db/rls.py`), and durable outbox/background workers (`app/workers/*`).
- **Runtime Baseline**: Python 3.13 (`3.13.18`), FastAPI (`0.136.0`), Pydantic v2 (`2.13.3`), SQLAlchemy 2.x async (`2.0.49`) with `asyncpg`, Alembic (`1.18.4`), PostgreSQL 16 + `pgvector`.
- **Quality & Static Analysis**: `uv` with committed `uv.lock`, `ruff` (`0.15.11`), `mypy` (`1.20.1` strict), `pytest` (`9.2.0`) + `pytest-asyncio` + `httpx`.

---

## 2. Requirement & Capability Status Matrix

| Phase / Requirement | Status | Primary Implementation Files | Database Migrations | Verification Evidence |
| :--- | :--- | :--- | :--- | :--- |
| **Phase 0 — Repository Governance, CI, Docker & Tooling** | **VERIFIED** | `pyproject.toml`, `uv.lock`, `compose.yaml`, `Dockerfile`, `.github/workflows/ci.yml` | N/A | `ruff check .` (0 errors), `mypy app` (0 errors across 92 files) |
| **Phase 1 — Least-Privilege DB Roles & RLS Infrastructure** | **VERIFIED** | `scripts/init-db-roles.sql`, `scripts/provision_db.py`, `app/db/rls.py`, `app/db/session.py`, `app/db/tenant_context.py` | `001` – `012` (52 tenant-owned tables with `ENABLE` + `FORCE ROW LEVEL SECURITY`) | `test_runtime_database_role_is_least_privilege`, `test_all_tenant_owned_tables_enforce_rls`, `test_rls_fails_closed_when_tenant_context_absent` (all **PASSED**) |
| **Phase 2 — Multi-Tenant Onboarding, Auth, RBAC & Invitations** | **VERIFIED** | `app/modules/identity/*`, `app/modules/tenants/*`, `app/modules/memberships/*`, `app/core/security.py`, `app/core/authorization.py`, `app/api/dependencies.py` | `001_tenants_users_memberships`, `002_roles_sessions_invitations`, `003_tenant_settings_structure` | `test_auth_lifecycle_and_error_envelopes`, `test_password_and_token_security`, `test_jwt_access_token_roundtrip`, `test_principal_context_rbac_enforcement` (all **PASSED**); E2E Journey A |
| **Phase 3 — Course Authoring, Objectives, Versioning, Cohorts & Enrollments** | **VERIFIED** | `app/modules/courses/*`, `app/modules/enrollments/*`, `app/modules/tenants/*` (cohorts) | `004_courses_versions`, `005_enrollments_events` | E2E Journeys B & C |
| **Phase 4 — Assessments, Attempts & Deterministic Objective Scoring** | **VERIFIED** | `app/modules/assessments/*` | `006_assessments_grading` | E2E Journey C (50.0% scoring with per-objective breakdown; `correct_answer` hidden from learners) |
| **Phase 5 — Document Ingestion, Storage, Chunking & Vector Indexing** | **VERIFIED** | `app/modules/content/*`, `app/ai/embeddings/*`, `app/ai/providers/adapters.py` (`DefaultContentExtractor`), `app/workers/runner.py` | `007_documents_processing`, `009_embeddings_pgvector` | `test_deterministic_semantic_embeddings_unit_norm`, `test_practice_question_validation_and_content_chunking` (**PASSED**); E2E Journeys B & G (worker interruption + idempotent recovery) |
| **Phase 6 — Provider-Neutral AI Tutor, Grounded RAG, Citations & Integrity Guardrails** | **VERIFIED** | `app/ai/contracts.py`, `app/ai/providers/*`, `app/ai/retrieval/service.py`, `app/ai/safety/guardrails.py`, `app/ai/evaluation/service.py`, `app/modules/ai_tutor/*`, `app/modules/ai_practice/*` | `008_ai_conversations_jobs_usage` | `test_ai_evaluation_quality_gates_meet_release_targets`, `test_prompt_injection_and_citation_guardrails` (**PASSED**); E2E Journeys C (`integrity_restricted`), D (grounded + citations, out-of-scope refusal), E (practice drafts + instructor approval), F (cross-tenant RAG isolation) |
| **Phase 7 — Explainable Learning Intelligence, Gap Detection, Remediation & Analytics** | **VERIFIED** | `app/modules/learning_intelligence/*` | `010_learning_intelligence` | E2E Journey E (`gap_detected` → `mastered`, `prior_score = 0.0`, `score_delta = +100.0`, course analytics, cohort progress) |
| **Phase 8 — Subscriptions, Quotas, Audit Logs, Notifications & Outbox** | **VERIFIED** | `app/modules/subscriptions/*`, `app/modules/audit/*`, `app/modules/notifications/*`, `app/workers/runner.py` | `011_saas_subscriptions`, `012_audit_notifications_outbox` | `test_openapi_contract_and_required_paths` (**PASSED**); E2E Journey A (starter plan provisioning, audit events) |

> [!NOTE]
> "E2E Journey X" refers to sections of the single test `tests/e2e/test_complete_journeys.py::test_complete_end_to_end_multi_tenant_learning_journeys`, which runs Journeys A–G across two tenants (Horizon University and Apex FinTech Academy) and **PASSED** in full.

---

## 3. Executed Verification Commands & Results

1. **Ruff Linter**:
   - Command: `python -m uv run ruff check .`
   - Result: `All checks passed!` (Exit code `0`)
2. **Mypy Static Type Checker**:
   - Command: `python -m uv run mypy app`
   - Result: `Success: no issues found in 92 source files` (Exit code `0`)
3. **OpenAPI Specification Export**:
   - Command: `python -m uv run python scripts/export_openapi.py`
   - Result: `Exported OpenAPI specification (61 paths) to openapi.json` (Exit code `0`)
4. **Alembic Reproducible Schema Migrations**:
   - Command: `python -m uv run alembic upgrade head`
   - Result: All 12 revisions (`001_tenants_users_memberships` -> `012_audit_notifications_outbox`) applied on both `akademia_ai` and `akademia_ai_test`; `alembic current` reports `012_audit_notifications_outbox (head)`.
5. **Automated Test Suite (`pytest`)** — `14 passed`:
   - `tests/unit/test_domain_rules_and_ai_guardrails.py` (7/7 passed)
   - `tests/ai_evaluation/test_ai_quality_gates.py` (1/1 passed)
   - `tests/integration/test_migrations_and_schema.py` (2/2 passed)
   - `tests/tenancy/test_rls_and_tenant_isolation.py` (1/1 passed)
   - `tests/api/test_api_contracts_and_security.py` (2/2 passed)
   - `tests/e2e/test_complete_journeys.py` (1/1 passed — Journeys A–G)

---

## 4. Known Gaps & Environment Notes

- **Not yet implemented**: a platform-administration module and a dedicated object-storage abstraction (`app/core/storage.py`); uploads are written to `LOCAL_STORAGE_PATH`.
- **Test coverage is concentrated in one long E2E test.** Scoring, mastery thresholds and the integrity guardrail are verified there rather than by focused unit tests; adding those is recommended.
- **Local Docker resources**: with ~1.9 GiB allocated to the Docker Desktop VM, PostgreSQL backends were observed exiting (code 2) under CPU starvation, forcing crash recovery mid-run. Allocate at least 4 GiB RAM / 4 CPUs to Docker Desktop (or WSL via `.wslconfig`) for reliable local test runs.
- **Test isolation**: `tests/conftest.py` resets data with ordered `DELETE`s under a PostgreSQL advisory lock, so overlapping `pytest` processes serialize instead of deleting each other's rows.
