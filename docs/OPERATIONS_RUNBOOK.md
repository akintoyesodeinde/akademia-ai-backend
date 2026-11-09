# Akademia AI — Operations Runbook (`OPERATIONS_RUNBOOK.md`)

## 1. Health & Readiness Probes

- **Liveness (`GET /health/live`)**:
  - Returns `200 OK` with `{"status": "alive", "service": "akademia-ai-backend"}` if the ASGI event loop is responsive.
- **Readiness (`GET /health/ready`)**:
  - Executes a live `SELECT 1` against PostgreSQL and verifies database connectivity before reporting `{"status": "ready", "database": "connected"}`.

---

## 2. Inspecting Stuck Document or AI Jobs

Background jobs are tracked in `document_processing_jobs` and `ai_jobs` with `status` (`queued`, `running`, `completed`, `failed`), `attempt_count`, `max_retries`, and `error_message`.

- **Re-trigger Document Processing**:
  - Instructors or Tenant Admins can call `POST /api/v1/documents/{document_id}/reprocess` (or click **Re-Chunk & Re-Embed** in the Instructor Studio).
- **Worker Recovery**:
  - `python -m app.workers.runner` uses `list_pending_document_jobs_bootstrap` and `list_pending_ai_jobs_bootstrap` to poll and process queued jobs inside each job's verified `tenant_scoped_session(tenant_id)`.

---

## 3. Tenant Suspension & Incident Response

If a tenant exhibits anomalous activity or billing delinquency:
1. Authenticate as a Platform Operator (`is_platform_admin = true`).
2. Call `PATCH /api/v1/platform/tenants/{tenant_id}/status` with:
   ```json
   {
     "status": "suspended",
     "reason": "Security incident investigation #INC-2026-1029"
   }
   ```
3. Effect is immediate: `get_current_principal()` checks `Tenant.status` on every authenticated API request and rejects requests for suspended tenants with `403 TENANT_SUSPENDED`, while recording an immutable `platform.tenant.status_updated` event in `audit_events`.

---

## 4. Running On-Demand AI Quality Gate Audits

Platform operators can trigger the multi-tenant RAG & safety evaluation suite at any time via `POST /api/v1/platform/ai-evaluations/run` or the **Platform Ops** workspace in the UI to verify `retrieval_recall_at_5`, `citation_authorization_rate == 1.0`, and `unauthorized_leak_count == 0`.
