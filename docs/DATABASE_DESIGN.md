# Akademia AI — Database Design (`DATABASE_DESIGN.md`)

## 1. Core Relational Principles

- **Engine**: PostgreSQL 16+ with `pgcrypto` and `pgvector` (`vector(64)` embeddings with HNSW cosine similarity index).
- **Primary Keys**: UUIDv4 across all tables.
- **Timestamps**: Timezone-aware UTC (`TIMESTAMPTZ`) on all tables (`created_at`, `updated_at`).
- **Composite Tenant Foreign Keys**:
  Every parent tenant-owned table defines `UNIQUE (tenant_id, id)`. Every child table references `(tenant_id, parent_id)` via a composite foreign key (`FOREIGN KEY (tenant_id, course_id) REFERENCES courses (tenant_id, id)`). This makes cross-tenant foreign-key references impossible at the storage engine level even before RLS evaluation.

---

## 2. Ordered 12-Step Alembic Migration Sequence

| Revision ID | File | Tables & Objects Created |
|---|---|---|
| `001_tenants_users_memberships` | `migrations/versions/001_tenants_users_memberships.py` | Extensions (`pgcrypto`, `vector`), `tenants`, `tenant_domains`, `users`, `auth_identities`, `tenant_memberships`, RLS policies |
| `002_roles_sessions_invitations` | `migrations/versions/002_roles_sessions_invitations.py` | `roles`, `permissions`, `role_permissions`, `membership_roles`, `user_sessions`, `refresh_tokens`, `password_reset_tokens`, `email_verification_tokens`, `invitations`, seeded permissions, bootstrap functions |
| `003_tenant_settings_structure` | `migrations/versions/003_tenant_settings_structure.py` | `tenant_settings`, `departments`, `academic_terms`, `cohorts`, `cohort_memberships` |
| `004_courses_versions` | `migrations/versions/004_courses_versions.py` | `courses`, `course_versions`, `course_instructors`, `course_modules`, `lessons`, `lesson_blocks`, `learning_objectives`, `lesson_objective_links` |
| `005_enrollments_events` | `migrations/versions/005_enrollments_events.py` | `enrollments`, `lesson_progress`, `learning_events` |
| `006_assessments_grading` | `migrations/versions/006_assessments_grading.py` | `assessments`, `assessment_versions`, `questions`, `question_options`, `question_objective_links`, `assessment_attempts`, `attempt_answers`, `grading_results` |
| `007_documents_processing` | `migrations/versions/007_documents_processing.py` | `course_documents`, `document_processing_jobs`, `document_chunks`, worker bootstrap function |
| `008_ai_conversations_jobs_usage` | `migrations/versions/008_ai_conversations_jobs_usage.py` | `tutor_conversations`, `tutor_messages`, `tutor_message_citations`, `practice_question_sets`, `practice_question_drafts`, `ai_jobs`, `ai_usage_ledgers`, `ai_evaluation_runs` |
| `009_embeddings_pgvector` | `migrations/versions/009_embeddings_pgvector.py` | `chunk_embeddings` (`vector(64)` column + `ix_chunk_embeddings_vector_hnsw` HNSW cosine index) |
| `010_learning_intelligence` | `migrations/versions/010_learning_intelligence.py` | `learner_objective_mastery`, `knowledge_gaps`, `recommendations`, `remediation_plans` |
| `011_saas_subscriptions` | `migrations/versions/011_saas_subscriptions.py` | `subscription_plans`, `plan_entitlements`, `tenant_subscriptions`, `usage_quotas`, `usage_records`, `billing_events`, seeded plans (`starter`, `professional`, `enterprise`) |
| `012_audit_notifications_outbox` | `migrations/versions/012_audit_notifications_outbox.py` | `audit_events`, `notifications`, `outbox_events` and runtime grants to `akademia_app`, `akademia_worker`, `akademia_readonly` |
