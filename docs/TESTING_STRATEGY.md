# Akademia AI — Testing Strategy (`TESTING_STRATEGY.md`)

## 1. Test Pyramid & Verification Layers

Akademia AI enforces automated verification across six distinct test suites in `akademia-ai-backend/tests/` and two suites in `akademia-ai-frontend/`:

1. **Unit Tests (`tests/unit/test_domain_rules_and_ai_guardrails.py`)**:
   - Password hashing & verification, JWT signing/decoding, RBAC permission resolution, prompt injection detection, passage sanitization, citation filtering, deterministic semantic embeddings, and document chunk extraction.
2. **Migration & Schema Integration Tests (`tests/integration/test_migrations_and_schema.py`)**:
   - Verifies that all 52 tenant-owned tables exist in PostgreSQL, have `relrowsecurity = true` and `relforcerowsecurity = true` in `pg_class`, have active RLS policies in `pg_policies`, and that runtime database roles (`akademia_app`, `akademia_worker`) have `rolsuper = false` and `rolbypassrls = false`.
3. **Multi-Tenant RLS & Isolation Tests (`tests/tenancy/test_rls_and_tenant_isolation.py`)**:
   - Verifies fail-closed behavior when `app.tenant_id` is unset (`0` rows returned).
   - Verifies Tenant A cannot read, update, or delete Tenant B courses, documents, chunks, or assessments.
   - Verifies `WITH CHECK` blocks inserting a row with a mismatched `tenant_id`.
   - Verifies composite foreign keys block cross-tenant child-to-parent references even for the schema owner role.
   - Verifies transaction rollback and connection pool reuse never leak `app.tenant_id` across transactions.
4. **API Contract & Security Tests (`tests/api/test_api_contracts_and_security.py`)**:
   - Tests health probes, OpenAPI schema generation, authentication error envelopes, refresh token rotation and reuse detection, cross-tenant IDOR prevention (`403`/`404`), and upload validation.
5. **AI Quality Gate Tests (`tests/ai_evaluation/test_ai_quality_gates.py`)**:
   - Executes `AIEvaluationHarness.run_benchmark_suite()` against real PostgreSQL + `pgvector` tables and asserts `passed_quality_gate is True` and `unauthorized_leak_count == 0`.
6. **End-to-End Learning Journey Tests (`tests/e2e/test_complete_journeys.py`)**:
   - Exercises all 8 product journeys end-to-end against real PostgreSQL persistence:
     - Tenant creation, instructor invitation, acceptance, and role switching.
     - Course authoring, objective creation, lesson mapping, document upload, and course publishing.
     - Learner enrollment, lesson completion, initial low-score assessment attempt (`0%`), automatic `KnowledgeGap` detection, `Recommendation` and `RemediationPlan` creation.
     - Course-grounded AI Tutor question returning verified citations, academic integrity refusal during an active exam attempt, and prompt-injection refusal.
     - Instructor AI practice question generation and draft approval.
     - Learner follow-up assessment attempt (`100%`) verifying `prior_score`, positive `score_delta`, mastery progression, and instructor analytics.
     - Tenant admin subscription upgrade, audit event verification, and platform operator tenant suspension/reactivation.
