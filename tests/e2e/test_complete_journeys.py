from uuid import UUID

import pytest
from app.db.session import tenant_scoped_session
from app.modules.content.service import DocumentService
from app.workers.runner import run_worker_iteration
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_complete_end_to_end_multi_tenant_learning_journeys(
    api_client: AsyncClient,
) -> None:
    """Verifies Journeys A, B, C, D, E, F, and G across two independent tenants:
    - Tenant 1: Horizon University (school/university tenant)
    - Tenant 2: Apex FinTech Academy (corporate training tenant)
    """
    # =========================================================================
    # JOURNEY A — Institutional Onboarding (Two Separate Tenants + Multi-Tenant User)
    # =========================================================================
    # 1. Register Horizon University Owner
    u_owner1 = (
        await api_client.post(
            "/api/v1/auth/register",
            json={
                "email": "dean@horizon-uni.edu",
                "password": "Password123!@#",
                "full_name": "Dean Eleanor Vance",
            },
        )
    ).json()
    tok_owner1 = u_owner1["access_token"]

    t1_res = await api_client.post(
        "/api/v1/tenants",
        headers={"Authorization": f"Bearer {tok_owner1}"},
        json={
            "name": "Horizon University",
            "slug": "horizon-uni",
            "institution_type": "university",
            "primary_contact_email": "dean@horizon-uni.edu",
        },
    )
    assert t1_res.status_code == 201
    t1_data = t1_res.json()
    tenant1_id = t1_data["tenant"]["id"]
    tok_owner1 = t1_data["access_token"]

    # Configure Horizon University settings
    patch_t1 = await api_client.patch(
        "/api/v1/tenants/current",
        headers={"Authorization": f"Bearer {tok_owner1}"},
        json={
            "academic_integrity_policy": "strict_during_assessment",
            "ai_tutor_enabled": True,
            "ai_practice_enabled": True,
        },
    )
    assert patch_t1.status_code == 200

    # Invite Instructor & Learner to Horizon University
    inv_inst1 = (
        await api_client.post(
            "/api/v1/tenants/current/invitations",
            headers={"Authorization": f"Bearer {tok_owner1}"},
            json={"email": "prof.chen@horizon-uni.edu", "role_code": "instructor"},
        )
    ).json()
    inv_learn1 = (
        await api_client.post(
            "/api/v1/tenants/current/invitations",
            headers={"Authorization": f"Bearer {tok_owner1}"},
            json={"email": "maya.student@horizon-uni.edu", "role_code": "learner"},
        )
    ).json()

    # Register & accept invitation for Instructor 1
    u_inst1 = (
        await api_client.post(
            "/api/v1/auth/register",
            json={
                "email": "prof.chen@horizon-uni.edu",
                "password": "Password123!@#",
                "full_name": "Prof. Marcus Chen",
            },
        )
    ).json()
    acc_inst1 = await api_client.post(
        "/api/v1/invitations/accept",
        headers={"Authorization": f"Bearer {u_inst1['access_token']}"},
        json={"token": inv_inst1["invitation_token"]},
    )
    assert acc_inst1.status_code == 200
    tok_inst1 = (
        await api_client.post(
            "/api/v1/auth/login",
            json={
                "email": "prof.chen@horizon-uni.edu",
                "password": "Password123!@#",
                "tenant_id": tenant1_id,
            },
        )
    ).json()["access_token"]

    # Register & accept invitation for Learner 1
    u_learn1 = (
        await api_client.post(
            "/api/v1/auth/register",
            json={
                "email": "maya.student@horizon-uni.edu",
                "password": "Password123!@#",
                "full_name": "Maya Lin",
            },
        )
    ).json()
    acc_learn1 = await api_client.post(
        "/api/v1/invitations/accept",
        headers={"Authorization": f"Bearer {u_learn1['access_token']}"},
        json={"token": inv_learn1["invitation_token"]},
    )
    assert acc_learn1.status_code == 200
    learn1_membership_id = acc_learn1.json()["membership_id"]
    tok_learn1 = (
        await api_client.post(
            "/api/v1/auth/login",
            json={
                "email": "maya.student@horizon-uni.edu",
                "password": "Password123!@#",
                "tenant_id": tenant1_id,
            },
        )
    ).json()["access_token"]

    # Create a Cohort in Horizon University and add Learner 1
    cohort1 = (
        await api_client.post(
            "/api/v1/tenants/current/cohorts",
            headers={"Authorization": f"Bearer {tok_owner1}"},
            json={
                "name": "Fall 2026 Computer Science Cohort",
                "code": "CS-2026-FALL",
                "description": "Undergraduate Systems & Security track",
            },
        )
    ).json()
    await api_client.post(
        f"/api/v1/tenants/current/cohorts/{cohort1['id']}/members",
        headers={"Authorization": f"Bearer {tok_owner1}"},
        json={"membership_id": learn1_membership_id, "role_in_cohort": "learner"},
    )

    # 2. Provision Second Tenant: Apex FinTech Academy (Corporate Training Tenant)
    u_owner2 = (
        await api_client.post(
            "/api/v1/auth/register",
            json={
                "email": "director@apex-fintech.com",
                "password": "Password123!@#",
                "full_name": "Director Samuel Okon",
            },
        )
    ).json()
    t2_res = await api_client.post(
        "/api/v1/tenants",
        headers={"Authorization": f"Bearer {u_owner2['access_token']}"},
        json={
            "name": "Apex FinTech Academy",
            "slug": "apex-fintech",
            "institution_type": "corporate",
            "primary_contact_email": "director@apex-fintech.com",
        },
    )
    assert t2_res.status_code == 201
    tenant2_id = t2_res.json()["tenant"]["id"]
    tok_owner2 = t2_res.json()["access_token"]

    # =========================================================================
    # JOURNEY B — Course Authoring, Objectives, Lessons, Materials & Publishing
    # =========================================================================
    course1 = (
        await api_client.post(
            "/api/v1/courses",
            headers={"Authorization": f"Bearer {tok_inst1}"},
            json={
                "code": "DBSEC-301",
                "title": "PostgreSQL Multi-Tenant Security & Architecture",
                "description": "Deep dive into Row-Level Security, composite foreign keys, and RAG isolation.",
                "academic_integrity_policy": "strict_during_assessment",
            },
        )
    ).json()
    course1_id = course1["id"]

    # Define two learning objectives
    obj1 = (
        await api_client.post(
            f"/api/v1/courses/{course1_id}/objectives",
            headers={"Authorization": f"Bearer {tok_inst1}"},
            json={
                "code": "OBJ-RLS-01",
                "title": "Row-Level Security Policy Design",
                "description": "Design fail-closed USING and WITH CHECK RLS policies bound to transaction-local settings.",
                "mastery_threshold": 75,
            },
        )
    ).json()
    obj2 = (
        await api_client.post(
            f"/api/v1/courses/{course1_id}/objectives",
            headers={"Authorization": f"Bearer {tok_inst1}"},
            json={
                "code": "OBJ-FK-02",
                "title": "Composite Tenant-Aware Foreign Keys",
                "description": "Prevent cross-tenant relational references using (tenant_id, id) composite constraints.",
                "mastery_threshold": 75,
            },
        )
    ).json()

    # Add lessons mapped to objectives
    lesson1 = (
        await api_client.post(
            f"/api/v1/courses/{course1_id}/lessons",
            headers={"Authorization": f"Bearer {tok_inst1}"},
            json={
                "title": "Lesson 1: Transaction-Local Tenant Context & RLS",
                "content_markdown": (
                    "# Transaction-Local Tenant Context\n\n"
                    "Use `SELECT set_config('app.tenant_id', :tenant_id, true)` inside every database transaction "
                    "so that Row-Level Security policies fail closed when tenant context is absent."
                ),
                "position": 1,
                "estimated_minutes": 25,
                "objective_ids": [obj1["id"]],
            },
        )
    ).json()

    lesson2 = (
        await api_client.post(
            f"/api/v1/courses/{course1_id}/lessons",
            headers={"Authorization": f"Bearer {tok_inst1}"},
            json={
                "title": "Lesson 2: Composite Foreign Keys for Multi-Tenancy",
                "content_markdown": (
                    "# Composite Foreign Keys\n\n"
                    "Every tenant-owned parent table defines `UNIQUE (tenant_id, id)` and child tables use "
                    "`FOREIGN KEY (tenant_id, parent_id) REFERENCES parent(tenant_id, id)`."
                ),
                "position": 2,
                "estimated_minutes": 20,
                "objective_ids": [obj2["id"]],
            },
        )
    ).json()

    # Upload approved course reference document
    doc_markdown = (
        b"# Chapter 1: PostgreSQL Row-Level Security\n\n"
        b"PostgreSQL Row-Level Security (RLS) enforces tenant isolation at the storage engine layer. "
        b"By combining ENABLE ROW LEVEL SECURITY and FORCE ROW LEVEL SECURITY with a policy checking "
        b"tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid, queries without tenant "
        b"context fail closed and return zero rows.\n\n"
        b"# Chapter 2: Composite Tenant Foreign Keys\n\n"
        b"Composite foreign keys include both tenant_id and the parent primary key id so that a child "
        b"record in Tenant A can never reference a parent record owned by Tenant B."
    )

    doc1_resp = await api_client.post(
        f"/api/v1/courses/{course1_id}/documents",
        headers={"Authorization": f"Bearer {tok_inst1}"},
        data={"title": "Official Multi-Tenant Security Handbook"},
        files={"file": ("security_handbook.md", doc_markdown, "text/markdown")},
    )
    assert doc1_resp.status_code == 201
    doc1 = doc1_resp.json()
    assert doc1["status"] == "ready"
    assert doc1["chunks_count"] >= 1

    # Publish Course Version 1
    pub_v1 = await api_client.post(
        f"/api/v1/courses/{course1_id}/publish",
        headers={"Authorization": f"Bearer {tok_inst1}"},
    )
    assert pub_v1.status_code == 200
    assert pub_v1.json()["version_number"] == 1
    v1_id = pub_v1.json()["id"]

    # Also publish a separate course in Tenant 2 (Apex FinTech Academy)
    course2 = (
        await api_client.post(
            "/api/v1/courses",
            headers={"Authorization": f"Bearer {tok_owner2}"},
            json={
                "code": "AML-101",
                "title": "Corporate Anti-Money Laundering & Treasury Controls",
                "description": "Confidential corporate compliance curriculum.",
            },
        )
    ).json()
    course2_id = course2["id"]
    await api_client.post(
        f"/api/v1/courses/{course2_id}/documents",
        headers={"Authorization": f"Bearer {tok_owner2}"},
        data={"title": "Apex Confidential Treasury Policy"},
        files={
            "file": (
                "treasury.md",
                b"# Apex Treasury Policy\n\nAll wire transfers above 500000 USD require dual hardware token signoff.",
                "text/markdown",
            )
        },
    )
    await api_client.post(
        f"/api/v1/courses/{course2_id}/publish",
        headers={"Authorization": f"Bearer {tok_owner2}"},
    )

    # =========================================================================
    # JOURNEY C — Enrollment, Lesson Study, Assessment Authoring & Attempt
    # =========================================================================
    # Enroll Learner 1 in Course 1
    enr1 = await api_client.post(
        f"/api/v1/courses/{course1_id}/enrollments",
        headers={"Authorization": f"Bearer {tok_learn1}"},
        json={"cohort_id": cohort1["id"]},
    )
    assert enr1.status_code == 201
    assert enr1.json()["course_version_id"] == v1_id

    # Learner studies and completes Lesson 1
    comp_l1 = await api_client.post(
        f"/api/v1/lessons/{lesson1['id']}/complete",
        headers={"Authorization": f"Bearer {tok_learn1}"},
    )
    assert comp_l1.status_code == 200
    assert comp_l1.json()["completion_percentage"] == 50.0

    # Instructor edits Course 1 and publishes Version 2; verify Version 1 snapshot remains immutable
    await api_client.patch(
        f"/api/v1/lessons/{lesson2['id']}",
        headers={"Authorization": f"Bearer {tok_inst1}"},
        json={"title": "Lesson 2 (Updated for v2): Composite Foreign Keys"},
    )
    pub_v2 = await api_client.post(
        f"/api/v1/courses/{course1_id}/publish",
        headers={"Authorization": f"Bearer {tok_inst1}"},
    )
    assert pub_v2.status_code == 200
    assert pub_v2.json()["version_number"] == 2
    versions_list = (
        await api_client.get(
            f"/api/v1/courses/{course1_id}/versions",
            headers={"Authorization": f"Bearer {tok_inst1}"},
        )
    ).json()
    assert len(versions_list) == 2
    v1_snap = next(v for v in versions_list if v["version_number"] == 1)
    assert (
        v1_snap["snapshot_payload"]["lessons"][1]["title"]
        == "Lesson 2: Composite Foreign Keys for Multi-Tenancy"
    )

    # Instructor creates & publishes Diagnostic Assessment 1 testing OBJ-RLS-01 and OBJ-FK-02
    asmt1 = (
        await api_client.post(
            f"/api/v1/courses/{course1_id}/assessments",
            headers={"Authorization": f"Bearer {tok_inst1}"},
            json={
                "title": "Diagnostic Check: Multi-Tenant Database Security",
                "assessment_type": "diagnostic",
                "passing_score_percentage": 75.0,
                "questions": [
                    {
                        "question_type": "multiple_choice",
                        "prompt": "Which PostgreSQL function sets transaction-local tenant context?",
                        "options": [
                            {"key": "A", "text": "set_config('app.tenant_id', tid, true)"},
                            {"key": "B", "text": "ALTER SYSTEM SET tenant_id"},
                        ],
                        "correct_answer": "A",
                        "points": 50.0,
                        "difficulty": "medium",
                        "objective_ids": [obj1["id"]],
                    },
                    {
                        "question_type": "multiple_choice",
                        "prompt": "What prevents a child row in Tenant A from referencing a parent row in Tenant B?",
                        "options": [
                            {"key": "A", "text": "Composite foreign keys on (tenant_id, id)"},
                            {"key": "B", "text": "Frontend JavaScript validation"},
                        ],
                        "correct_answer": "A",
                        "points": 50.0,
                        "difficulty": "medium",
                        "objective_ids": [obj2["id"]],
                    },
                ],
            },
        )
    ).json()
    asmt1_id = asmt1["id"]
    await api_client.post(
        f"/api/v1/assessments/{asmt1_id}/publish",
        headers={"Authorization": f"Bearer {tok_inst1}"},
    )

    # Learner views assessment -> verify correct_answer is stripped from learner response!
    learner_asmt_view = (
        await api_client.get(
            f"/api/v1/assessments/{asmt1_id}",
            headers={"Authorization": f"Bearer {tok_learn1}"},
        )
    ).json()
    assert learner_asmt_view["questions"][0]["correct_answer"] is None

    # Learner starts Attempt 1
    attempt1 = (
        await api_client.post(
            f"/api/v1/assessments/{asmt1_id}/attempts",
            headers={"Authorization": f"Bearer {tok_learn1}"},
        )
    ).json()
    attempt1_id = attempt1["id"]
    q1_id = attempt1["questions"][0]["id"]
    q2_id = attempt1["questions"][1]["id"]

    # While Attempt 1 is IN PROGRESS, test academic-integrity policy on AI Tutor!
    conv = (
        await api_client.post(
            f"/api/v1/courses/{course1_id}/tutor/conversations",
            headers={"Authorization": f"Bearer {tok_learn1}"},
            json={"title": "RLS Study Questions", "complexity_level": "standard"},
        )
    ).json()
    conv_id = conv["id"]

    mid_exam_msg = (
        await api_client.post(
            f"/api/v1/tutor/conversations/{conv_id}/messages",
            headers={"Authorization": f"Bearer {tok_learn1}"},
            json={"content": "How does PostgreSQL Row-Level Security work?"},
        )
    ).json()
    assert mid_exam_msg["grounding_status"] == "integrity_restricted"

    # Learner answers Q1 (OBJ-RLS-01) CORRECTLY ("A"), and Q2 (OBJ-FK-02) INCORRECTLY ("B")
    await api_client.put(
        f"/api/v1/attempts/{attempt1_id}/responses/{q1_id}",
        headers={"Authorization": f"Bearer {tok_learn1}"},
        json={"selected_answer": "A"},
    )
    await api_client.put(
        f"/api/v1/attempts/{attempt1_id}/responses/{q2_id}",
        headers={"Authorization": f"Bearer {tok_learn1}"},
        json={"selected_answer": "B"},
    )

    # Submit Attempt 1 -> Backend deterministically scores 50.0% (OBJ-RLS-01=100%, OBJ-FK-02=0%)
    sub1 = await api_client.post(
        f"/api/v1/attempts/{attempt1_id}/submit",
        headers={"Authorization": f"Bearer {tok_learn1}"},
    )
    assert sub1.status_code == 200
    res1 = sub1.json()
    assert res1["score_percentage"] == 50.0
    assert res1["passed"] is False

    # =========================================================================
    # JOURNEY D — Grounded AI Tutoring with Citations & Unsupported Query Handling
    # =========================================================================
    # Now that Attempt 1 is submitted, learner asks the AI tutor a question grounded in course materials
    tutor_ans = (
        await api_client.post(
            f"/api/v1/tutor/conversations/{conv_id}/messages",
            headers={"Authorization": f"Bearer {tok_learn1}"},
            json={
                "content": "How do composite foreign keys and Row-Level Security enforce tenant_id isolation?"
            },
        )
    ).json()
    assert tutor_ans["grounding_status"] == "grounded"
    assert len(tutor_ans["citations"]) >= 1
    assert tutor_ans["citations"][0]["document_id"] == doc1["id"]
    assert (
        tutor_ans["citations"][0]["document_title"]
        == "Official Multi-Tenant Security Handbook"
    )

    # Learner asks an out-of-scope question not supported by course material
    unsupported_ans = (
        await api_client.post(
            f"/api/v1/tutor/conversations/{conv_id}/messages",
            headers={"Authorization": f"Bearer {tok_learn1}"},
            json={
                "content": "What is the melting point of titanium alloy in jet turbines?"
            },
        )
    ).json()
    assert unsupported_ans["grounding_status"] == "insufficient_course_material"
    assert unsupported_ans["citations"] == []

    # =========================================================================
    # JOURNEY E — Knowledge-Gap Detection, AI Practice Generation, Review & Follow-Up
    # =========================================================================
    # Check learner mastery & knowledge gap detection
    mastery_list = (
        await api_client.get(
            f"/api/v1/learners/me/mastery?course_id={course1_id}",
            headers={"Authorization": f"Bearer {tok_learn1}"},
        )
    ).json()
    by_code = {m["objective_code"]: m for m in mastery_list}
    assert by_code["OBJ-RLS-01"]["mastery_status"] == "mastered"
    assert by_code["OBJ-RLS-01"]["mastery_score"] == 100.0
    assert by_code["OBJ-FK-02"]["mastery_status"] == "gap_detected"
    assert by_code["OBJ-FK-02"]["mastery_score"] == 0.0

    # Check traceable recommendation generated for OBJ-FK-02
    recs = (
        await api_client.get(
            f"/api/v1/learners/me/recommendations?course_id={course1_id}",
            headers={"Authorization": f"Bearer {tok_learn1}"},
        )
    ).json()
    assert len(recs) == 1
    assert recs[0]["objective_code"] == "OBJ-FK-02"
    assert recs[0]["status"] == "active"
    assert len(recs[0]["evidence_refs"]) == 1

    # Learner submits feedback on recommendation
    fb_resp = await api_client.post(
        f"/api/v1/recommendations/{recs[0]['id']}/feedback",
        headers={"Authorization": f"Bearer {tok_learn1}"},
        json={"feedback": "helpful", "comment": "Reviewing Lesson 2 and practice items now."},
    )
    assert fb_resp.status_code == 200

    # Instructor triggers AI practice generation job (202 Accepted) for OBJ-FK-02
    pjob_resp = await api_client.post(
        f"/api/v1/courses/{course1_id}/practice-generation-jobs",
        headers={"Authorization": f"Bearer {tok_inst1}"},
        json={
            "objective_id": obj2["id"],
            "difficulty": "medium",
            "question_count": 2,
        },
    )
    assert pjob_resp.status_code == 202
    pjob = pjob_resp.json()
    assert pjob["status"] == "completed"

    # Instructor reviews generated practice question drafts and approves the first one
    drafts = (
        await api_client.get(
            f"/api/v1/courses/{course1_id}/practice-drafts",
            headers={"Authorization": f"Bearer {tok_inst1}"},
        )
    ).json()
    assert len(drafts) == 2
    assert drafts[0]["question_status"] == "draft"
    assert drafts[0]["review_status"] == "pending_review"

    approved_draft = (
        await api_client.post(
            f"/api/v1/practice-drafts/{drafts[0]['review_id']}/decision",
            headers={"Authorization": f"Bearer {tok_inst1}"},
            json={
                "decision": "approved",
                "reviewer_notes": "Verified against Chapter 2 of the Security Handbook.",
            },
        )
    ).json()
    assert approved_draft["question_status"] == "approved"
    assert approved_draft["review_status"] == "approved"

    # Instructor creates & publishes a Follow-Up Assessment using the approved AI practice question
    followup_asmt = (
        await api_client.post(
            f"/api/v1/courses/{course1_id}/assessments",
            headers={"Authorization": f"Bearer {tok_inst1}"},
            json={
                "title": "Follow-Up Remediation Assessment: Composite Foreign Keys",
                "assessment_type": "follow_up",
                "passing_score_percentage": 75.0,
                "existing_question_ids": [approved_draft["question_id"]],
            },
        )
    ).json()
    await api_client.post(
        f"/api/v1/assessments/{followup_asmt['id']}/publish",
        headers={"Authorization": f"Bearer {tok_inst1}"},
    )

    # Learner completes Follow-Up Assessment and answers "A" (100%)
    att2 = (
        await api_client.post(
            f"/api/v1/assessments/{followup_asmt['id']}/attempts",
            headers={"Authorization": f"Bearer {tok_learn1}"},
        )
    ).json()
    await api_client.put(
        f"/api/v1/attempts/{att2['id']}/responses/{approved_draft['question_id']}",
        headers={"Authorization": f"Bearer {tok_learn1}"},
        json={"selected_answer": "A"},
    )
    sub2 = (
        await api_client.post(
            f"/api/v1/attempts/{att2['id']}/submit",
            headers={"Authorization": f"Bearer {tok_learn1}"},
        )
    ).json()
    assert sub2["score_percentage"] == 100.0
    assert sub2["passed"] is True

    # Verify OBJ-FK-02 mastery improved from 0% -> 100% with prior_score=0.0 and score_delta=+100.0!
    mastery_after = (
        await api_client.get(
            f"/api/v1/learners/me/mastery?course_id={course1_id}",
            headers={"Authorization": f"Bearer {tok_learn1}"},
        )
    ).json()
    fk_after = next(m for m in mastery_after if m["objective_code"] == "OBJ-FK-02")
    assert fk_after["mastery_status"] == "mastered"
    assert fk_after["prior_score"] == 0.0
    assert fk_after["mastery_score"] == 100.0
    assert fk_after["score_delta"] == 100.0

    # Instructor inspects course analytics & cohort progress
    analytics = (
        await api_client.get(
            f"/api/v1/courses/{course1_id}/analytics",
            headers={"Authorization": f"Bearer {tok_inst1}"},
        )
    ).json()
    assert analytics["enrolled_learners_count"] == 1
    assert analytics["submitted_attempts_count"] == 2

    cohort_prog = (
        await api_client.get(
            f"/api/v1/cohorts/{cohort1['id']}/progress",
            headers={"Authorization": f"Bearer {tok_inst1}"},
        )
    ).json()
    assert cohort_prog["learners_count"] == 1
    assert cohort_prog["average_mastery_score"] == 100.0

    # =========================================================================
    # JOURNEY F — Cross-Tenant Isolation Proofs (API, Headers, & AI Retrieval)
    # =========================================================================
    # 1. Tenant 1 Owner/Instructor/Learner attempting to pass X-Tenant-ID: tenant2_id is denied (403)
    cross_header = await api_client.get(
        "/api/v1/courses",
        headers={
            "Authorization": f"Bearer {tok_owner1}",
            "X-Tenant-ID": tenant2_id,
        },
    )
    assert cross_header.status_code == 403

    # 2. Tenant 2 Owner attempting to read Tenant 1's course, document, assessment, or analytics gets 404
    cross_course = await api_client.get(
        f"/api/v1/courses/{course1_id}",
        headers={"Authorization": f"Bearer {tok_owner2}"},
    )
    assert cross_course.status_code == 404

    cross_doc = await api_client.get(
        f"/api/v1/documents/{doc1['id']}",
        headers={"Authorization": f"Bearer {tok_owner2}"},
    )
    assert cross_doc.status_code == 404

    # 3. Tenant 1 Learner asking AI Tutor about Tenant 2's confidential treasury wire transfer limit
    #    never retrieves Tenant 2's chunks!
    cross_rag = (
        await api_client.post(
            f"/api/v1/tutor/conversations/{conv_id}/messages",
            headers={"Authorization": f"Bearer {tok_learn1}"},
            json={
                "content": "What is the Apex Treasury Policy wire transfer hardware token limit?"
            },
        )
    ).json()
    assert cross_rag["grounding_status"] == "insufficient_course_material"
    assert cross_rag["citations"] == []
    assert "500000" not in cross_rag["content"]

    # =========================================================================
    # JOURNEY G — Worker Interruption & Idempotent Job Recovery
    # =========================================================================
    # Upload a document with process_async=true so job starts queued
    async_doc_resp = await api_client.post(
        f"/api/v1/courses/{course1_id}/documents?process_async=true",
        headers={"Authorization": f"Bearer {tok_inst1}"},
        data={"title": "Resilience Test Addendum"},
        files={
            "file": (
                "addendum.md",
                b"# Worker Resilience\n\nIdempotent background jobs recover cleanly from worker restarts without duplicate chunks.",
                "text/markdown",
            )
        },
    )
    assert async_doc_resp.status_code == 201
    async_doc = async_doc_resp.json()
    assert async_doc["status"] == "pending"
    job_id = UUID(async_doc["latest_job"]["id"])

    # Simulate worker crash mid-processing
    with pytest.raises(RuntimeError, match="Simulated worker interruption"):
        async with tenant_scoped_session(UUID(tenant1_id)) as sess:
            svc = DocumentService(sess)
            await svc.process_document_job(
                tenant_id=UUID(tenant1_id),
                job_id=job_id,
                simulate_interruption=True,
            )

    # Restart worker iteration -> picks up queued/interrupted job and completes cleanly
    counts = await run_worker_iteration()
    assert counts["document_jobs"] >= 1

    recovered_doc = (
        await api_client.get(
            f"/api/v1/documents/{async_doc['id']}",
            headers={"Authorization": f"Bearer {tok_inst1}"},
        )
    ).json()
    assert recovered_doc["status"] == "ready"
    assert recovered_doc["chunks_count"] == 1
    assert recovered_doc["latest_job"]["status"] == "completed"
