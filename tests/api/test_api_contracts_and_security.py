import pytest
from app.main import app
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_openapi_contract_and_required_paths(api_client: AsyncClient) -> None:
    """Verify Part 8: OpenAPI specification is generated and includes all required endpoints."""
    schema = app.openapi()
    paths = set(schema.get("paths", {}).keys())

    required_paths = {
        "/api/v1/auth/register",
        "/api/v1/auth/login",
        "/api/v1/auth/refresh",
        "/api/v1/auth/logout",
        "/api/v1/auth/forgot-password",
        "/api/v1/auth/reset-password",
        "/api/v1/auth/verify-email",
        "/api/v1/auth/me",
        "/api/v1/tenants",
        "/api/v1/tenants/current",
        "/api/v1/tenants/current/members",
        "/api/v1/tenants/current/invitations",
        "/api/v1/invitations/accept",
        "/api/v1/tenants/current/members/{membership_id}",
        "/api/v1/tenants/current/roles",
        "/api/v1/courses",
        "/api/v1/courses/{course_id}",
        "/api/v1/courses/{course_id}/publish",
        "/api/v1/courses/{course_id}/versions",
        "/api/v1/courses/{course_id}/lessons",
        "/api/v1/lessons/{lesson_id}",
        "/api/v1/courses/{course_id}/enrollments",
        "/api/v1/learners/me/courses",
        "/api/v1/courses/{course_id}/assessments",
        "/api/v1/assessments/{assessment_id}/publish",
        "/api/v1/assessments/{assessment_id}",
        "/api/v1/assessments/{assessment_id}/attempts",
        "/api/v1/attempts/{attempt_id}/responses/{question_id}",
        "/api/v1/attempts/{attempt_id}/submit",
        "/api/v1/attempts/{attempt_id}/results",
        "/api/v1/grading-results/{result_id}/review",
        "/api/v1/courses/{course_id}/documents",
        "/api/v1/documents/{document_id}",
        "/api/v1/documents/{document_id}/reprocess",
        "/api/v1/courses/{course_id}/tutor/conversations",
        "/api/v1/tutor/conversations/{conversation_id}/messages",
        "/api/v1/tutor/conversations/{conversation_id}",
        "/api/v1/courses/{course_id}/practice-generation-jobs",
        "/api/v1/ai/jobs/{job_id}",
        "/api/v1/ai/jobs/{job_id}/cancel",
        "/api/v1/learners/me/progress",
        "/api/v1/learners/me/mastery",
        "/api/v1/learners/me/recommendations",
        "/api/v1/courses/{course_id}/analytics",
        "/api/v1/cohorts/{cohort_id}/progress",
        "/api/v1/recommendations/{recommendation_id}/feedback",
        "/api/v1/billing/plan",
        "/api/v1/billing/usage",
        "/api/v1/tenant-admin/audit-events",
        "/api/v1/platform/health",
    }
    missing = required_paths - paths
    assert not missing, f"Missing required OpenAPI paths: {missing}"

    health_resp = await api_client.get("/api/v1/platform/health")
    assert health_resp.status_code == 200
    assert health_resp.json()["status"] == "healthy"
    assert "X-Request-ID" in health_resp.headers


@pytest.mark.asyncio
async def test_auth_lifecycle_and_error_envelopes(api_client: AsyncClient) -> None:
    """Verify registration, email verification, refresh rotation, password reset, and error envelopes."""
    # 1. Unauthenticated request returns 401 with consistent error envelope
    unauth = await api_client.get("/api/v1/auth/me")
    assert unauth.status_code == 401
    assert "error" in unauth.json()
    assert unauth.json()["error"]["code"] == "AUTHENTICATION_FAILED"

    # 2. Invalid registration payload returns 422 with consistent error envelope
    bad_reg = await api_client.post(
        "/api/v1/auth/register",
        json={"email": "not-an-email", "password": "123", "full_name": "X"},
    )
    assert bad_reg.status_code == 422
    assert bad_reg.json()["error"]["code"] == "REQUEST_VALIDATION_FAILED"

    # 3. Valid registration
    reg = await api_client.post(
        "/api/v1/auth/register",
        json={
            "email": "Dr.Ada@University.edu",
            "password": "StrongPassword!123",
            "full_name": "Dr. Ada Lovelace",
        },
    )
    assert reg.status_code == 201
    reg_data = reg.json()
    assert reg_data["user"]["email"] == "dr.ada@university.edu"
    assert reg_data["user"]["email_verified"] is False
    verify_token = reg_data["verification_token_dev_hint"]
    assert verify_token

    # 4. Email verification
    ver = await api_client.post("/api/v1/auth/verify-email", json={"token": verify_token})
    assert ver.status_code == 200

    me_resp = await api_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {reg_data['access_token']}"},
    )
    assert me_resp.status_code == 200
    assert me_resp.json()["email_verified"] is True

    # 5. Refresh token rotation
    old_refresh = reg_data["refresh_token"]
    ref_resp = await api_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": old_refresh},
    )
    assert ref_resp.status_code == 200
    new_refresh = ref_resp.json()["refresh_token"]
    assert new_refresh != old_refresh

    # Reusing rotated refresh token fails with 401
    replay_resp = await api_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": old_refresh},
    )
    assert replay_resp.status_code == 401

    # 6. Forgot password & reset password
    forgot_resp = await api_client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "dr.ada@university.edu"},
    )
    assert forgot_resp.status_code == 200
    reset_tok = forgot_resp.json()["token_dev_hint"]
    assert reset_tok

    reset_resp = await api_client.post(
        "/api/v1/auth/reset-password",
        json={"token": reset_tok, "new_password": "NewSecurePassword!456"},
    )
    assert reset_resp.status_code == 200

    # Login with new password succeeds
    login_resp = await api_client.post(
        "/api/v1/auth/login",
        json={"email": "dr.ada@university.edu", "password": "NewSecurePassword!456"},
    )
    assert login_resp.status_code == 200
