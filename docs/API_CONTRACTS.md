# Akademia AI — REST API Contracts (`API_CONTRACTS.md`)

## 1. Base Path, Versioning & Content Type

- All REST API endpoints are versioned under `/api/v1`.
- Health and readiness probes are exposed at `/health/live` and `/health/ready`.
- OpenAPI 3.1 schema is exported deterministically via `scripts/export_openapi.py` to `openapi/openapi.json` and synchronized to the frontend's `src/api/generated/schema.ts`.

---

## 2. Standard Error Envelope

All application, validation, authentication, authorization, and rate-limit errors return a consistent JSON structure (`app/api/exception_handlers.py`):

```json
{
  "error": {
    "code": "AUTHORIZATION_ERROR",
    "message": "Principal lacks required permission: course:publish",
    "request_id": "req-9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
    "details": null
  }
}
```

---

## 3. Endpoint Summary (`/api/v1`)

### Authentication & Session (`app/api/v1/endpoints/auth.py`)
- `POST /api/v1/auth/register` — Register user and optionally provision an initial institutional tenant.
- `POST /api/v1/auth/login` — Authenticate credentials, return JWT + refresh token + active tenant memberships.
- `POST /api/v1/auth/refresh` — Rotate single-use refresh token (with reuse detection revoking compromised sessions).
- `POST /api/v1/auth/switch-tenant` — Verify membership in target `tenant_id` and issue a new tenant-scoped JWT.
- `POST /api/v1/auth/logout` — Revoke current session.
- `GET /api/v1/auth/me` — Inspect current authenticated user, memberships, and active tenant role.

### Tenants, Memberships & Invitations (`app/api/v1/endpoints/tenants.py`)
- `POST /api/v1/tenants` — Provision a new institutional tenant.
- `GET /api/v1/tenants/current` — Get current tenant profile and settings.
- `GET /api/v1/tenants/members` — List members in current tenant.
- `PATCH /api/v1/tenants/members/{membership_id}/role` — Update member RBAC role.
- `POST /api/v1/tenants/invitations` — Issue a cryptographic tenant invitation token.
- `POST /api/v1/tenants/invitations/accept` — Accept an invitation token and join the tenant.
- `POST /api/v1/tenants/cohorts` & `GET /api/v1/tenants/cohorts` — Create and list learner cohorts.

### Courses, Objectives, Lessons & Enrollments (`app/api/v1/endpoints/courses.py`)
- `POST /api/v1/courses` & `GET /api/v1/courses` — Create and list tenant courses.
- `POST /api/v1/courses/{course_id}/objectives` & `GET /api/v1/courses/{course_id}/objectives` — Manage learning objectives.
- `POST /api/v1/courses/{course_id}/lessons` & `GET /api/v1/courses/{course_id}/lessons` — Manage lessons mapped to objectives.
- `POST /api/v1/courses/{course_id}/publish` — Snapshot and publish an immutable `CourseVersion`.
- `POST /api/v1/courses/{course_id}/enroll` — Enroll learner in a published course.
- `POST /api/v1/courses/{course_id}/lessons/{lesson_id}/complete` — Record lesson completion and learning event.

### Approved Documents & Vector Ingestion (`app/api/v1/endpoints/documents.py`)
- `POST /api/v1/courses/{course_id}/documents` — Upload `.txt`, `.md`, `.pdf`, or `.docx`, extract chunks, and index embeddings in `pgvector`.
- `GET /api/v1/courses/{course_id}/documents` — List course documents and chunk counts.
- `POST /api/v1/documents/{document_id}/reprocess` — Re-chunk and re-embed document.

### Assessments, Attempts & Deterministic Grading (`app/api/v1/endpoints/assessments.py`)
- `POST /api/v1/assessments` & `GET /api/v1/courses/{course_id}/assessments` — Author and list assessments.
- `POST /api/v1/assessments/{assessment_id}/publish` — Publish immutable `AssessmentVersion`.
- `POST /api/v1/assessments/{assessment_id}/attempts` — Start learner assessment attempt.
- `POST /api/v1/assessments/attempts/{attempt_id}/submit` — Deterministically grade answers, update `LearnerObjectiveMastery`, detect `KnowledgeGap`s, generate `Recommendation`s & `RemediationPlan`s, and compute `prior_score` / `score_delta`.

### Course-Grounded AI Tutor & Practice Generation (`app/api/v1/endpoints/ai_tutor.py`)
- `POST /api/v1/ai/tutor/ask` — Ask course-grounded AI Tutor question with pre-retrieval authorization, academic integrity guardrails, and verified source chunk citations.
- `GET /api/v1/ai/tutor/conversations` — List learner's AI Tutor conversations.
- `POST /api/v1/ai/practice/generate` — Generate grounded practice question drafts for a course objective.
- `GET /api/v1/ai/practice/courses/{course_id}/drafts` — List practice drafts.
- `POST /api/v1/ai/practice/drafts/{draft_id}/review` — Instructor approve or reject practice draft.

### Learning Intelligence & Analytics (`app/api/v1/endpoints/learning_intelligence.py`)
- `GET /api/v1/learning-intelligence/courses/{course_id}/my-summary` — Learner mastery, knowledge gaps, recommendations, remediation plans, and follow-up score delta.
- `POST /api/v1/learning-intelligence/recommendations/{recommendation_id}/complete` — Mark recommendation completed.
- `GET /api/v1/learning-intelligence/courses/{course_id}/instructor-analytics` — Instructor cohort mastery and attempt analytics.

### SaaS Subscriptions, Audit & Platform Operations (`app/api/v1/endpoints/operations.py`)
- `GET /api/v1/operations/subscription` & `POST /api/v1/operations/subscription/change-plan` — Inspect and upgrade tenant subscription tier & AI token quotas.
- `GET /api/v1/operations/audit-events` — Paginated tenant security audit log.
- `GET /api/v1/operations/platform/tenants` & `PATCH /api/v1/operations/platform/tenants/{tenant_id}/status` — Platform operator tenant lifecycle control.
- `POST /api/v1/operations/platform/ai-evaluations/run` — Execute AI RAG Quality Gate evaluation suite.
