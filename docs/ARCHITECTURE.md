# Akademia AI — Backend Architecture (`ARCHITECTURE.md`)

## 1. Architectural Pattern: Modular Monolith with Strict Domain Boundaries

Akademia AI is engineered as a **Modular Monolith** (`akademia-ai-backend`) paired with an independently buildable and deployable React/TypeScript SPA (`akademia-ai-frontend`).

### Why Modular Monolith?
1. **Transactional & Multi-Tenant Integrity**: Every request in Akademia AI requires atomic enforcement of PostgreSQL Row-Level Security (`SET LOCAL app.tenant_id`), composite tenant-aware foreign keys, RBAC checks, and audit event recording within a single ACID transaction boundary.
2. **Zero Premature Distributed Complexity**: Avoids distributed saga orchestration, network serialization overhead, and cross-service schema drift while preserving clean internal module boundaries that can be extracted later if throughput dictates.
3. **Shared Worker & API Codebase**: Both the HTTP API process (`uvicorn app.main:app`) and the asynchronous background worker (`python -m app.workers.runner`) run from the same container image and domain service layer.

---

## 2. Module Boundaries & Responsibilities

| Module Path | Responsibility | Owned Tables |
|---|---|---|
| `app/modules/identity` | User registration, Argon2id/PBKDF2 password hashing, JWT issuance, refresh token rotation & reuse detection | `users`, `auth_identities`, `user_sessions`, `refresh_tokens`, `password_reset_tokens`, `email_verification_tokens` |
| `app/modules/tenants` | Institutional tenant provisioning, tenant settings, departments, cohorts, invitation lifecycle | `tenants`, `tenant_domains`, `tenant_settings`, `departments`, `academic_terms`, `cohorts`, `cohort_memberships`, `invitations` |
| `app/modules/memberships` | Tenant-scoped RBAC roles, permissions, and user-to-tenant memberships | `tenant_memberships`, `roles`, `permissions`, `role_permissions`, `membership_roles` |
| `app/modules/courses` | Course authoring, immutable version snapshots, learning objectives, lessons, lesson-to-objective mapping, enrollments, learner lesson progress | `courses`, `course_versions`, `course_instructors`, `course_modules`, `lessons`, `lesson_blocks`, `learning_objectives`, `lesson_objective_links`, `enrollments`, `lesson_progress`, `learning_events` |
| `app/modules/assessments` | Assessment authoring, version snapshots, question bank, options, learner attempts, deterministic grading, objective-level evidence extraction | `assessments`, `assessment_versions`, `questions`, `question_options`, `question_objective_links`, `assessment_attempts`, `attempt_answers`, `grading_results` |
| `app/modules/content` | Approved document upload, MIME/magic-byte validation, SHA-256 deduplication, structured chunking, pgvector indexing | `course_documents`, `document_processing_jobs`, `document_chunks`, `chunk_embeddings` |
| `app/modules/ai_tutor` | Course-grounded RAG tutoring, pre-retrieval authorization, citation verification, academic integrity guardrails, practice question draft generation & instructor review | `tutor_conversations`, `tutor_messages`, `tutor_message_citations`, `practice_question_sets`, `practice_question_drafts`, `ai_jobs`, `ai_usage_ledgers` |
| `app/modules/learning_intelligence` | Explainable objective mastery computation, knowledge gap detection, prioritized recommendations, remediation plans, follow-up `prior_score` & `score_delta` comparison, instructor cohort analytics | `learner_objective_mastery`, `knowledge_gaps`, `recommendations`, `remediation_plans` |
| `app/modules/subscriptions` | SaaS plans (`starter`, `professional`, `enterprise`), feature entitlements, seat limits, storage quotas, real-time AI token metering | `subscription_plans`, `plan_entitlements`, `tenant_subscriptions`, `usage_quotas`, `usage_records`, `billing_events` |
| `app/modules/audit` | Immutable tenant & platform audit event logging, transactional outbox, user notifications | `audit_events`, `notifications`, `outbox_events` |

---

## 3. Request Lifecycle

1. **Correlation & Telemetry Middleware (`app/core/observability.py`)**: Assigns or propagates `X-Request-ID`, records request latency, and binds structured log context.
2. **Authentication & Principal Resolution (`app/api/dependencies.py`)**:
   - Validates Bearer JWT signature and expiration.
   - Verifies active `TenantMembership` in PostgreSQL for the token's `tenant_id`.
   - Rejects requests if the tenant is `suspended` or membership is `revoked`.
3. **Transaction-Local RLS Binding (`app/db/tenant_context.py`)**:
   - Executes `SELECT set_config('app.tenant_id', :tenant_id, true)` on the checked-out SQLAlchemy `AsyncSession`.
4. **Domain Service Execution**: Executes business rules, records `AuditEvent` rows, and commits atomically at request exit.
