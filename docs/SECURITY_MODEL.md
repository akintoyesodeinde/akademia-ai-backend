# Akademia AI — Security Model (`SECURITY_MODEL.md`)

## 1. Authentication & Session Security

- **Password Hashing (`app/core/security.py`)**: Passwords are hashed using `argon2-cffi` (`Argon2id`) with constant-time verification.
- **Short-Lived Access Tokens & Single-Use Refresh Tokens (`app/modules/identity/service.py`)**:
  - Access tokens (JWT) embed `sub` (`user_id`), `tid` (`tenant_id`), `roles`, `is_platform_admin`, and `jti`.
  - Refresh tokens are high-entropy random secrets stored only as SHA-256 hashes (`token_hash`) in `refresh_tokens` linked to a `user_sessions` record.
  - **Refresh Token Reuse Detection**: If a previously rotated (`replaced_by_token_id IS NOT NULL`) or revoked refresh token is presented again, `IdentityService.refresh_session()` immediately revokes the entire `UserSession` family to stop token theft replay.

---

## 2. Multi-Tenant Authorization & IDOR Prevention

- **Zero Trust in Client Tenant Headers**: A client cannot access another tenant simply by passing a different `tenant_id` in a request body or query parameter.
- **Dual Enforcement**:
  1. `get_current_principal()` verifies an active `TenantMembership` in PostgreSQL and checks `PrincipalContext.require_permission(PermissionCode.*)`.
  2. PostgreSQL RLS (`ENABLE ROW LEVEL SECURITY` + `FORCE ROW LEVEL SECURITY`) restricts all queries to `current_setting('app.tenant_id', true)::uuid`.

---

## 3. Upload & Prompt-Injection Hardening

- **File Upload Validation (`app/shared/storage.py`)**:
  - Enforces maximum file size (`MAX_UPLOAD_SIZE_BYTES`).
  - Validates extension and MIME type allowlist (`.txt`, `.md`, `.pdf`, `.docx`).
  - Checks file magic signatures (e.g., `%PDF-` header for PDFs, `PK\x03\x04` for DOCX, null-byte rejection for plain text) and sanitizes filenames to prevent path traversal.
- **Prompt Injection Defense (`app/ai/safety/guardrails.py`)**:
  - `detect_prompt_injection()` screens user questions for system-prompt override, role hijack, and cross-tenant exfiltration patterns.
  - `sanitize_passage_text()` strips embedded instruction-override markers from uploaded documents before inserting chunks into the LLM prompt.
