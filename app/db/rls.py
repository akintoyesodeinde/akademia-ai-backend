"""SQL builders for enabling and enforcing PostgreSQL Row-Level Security (RLS)."""

TENANT_OWNED_TABLES: tuple[str, ...] = (
    "tenant_memberships",
    "membership_roles",
    "invitations",
    "tenant_settings",
    "tenant_domains",
    "cohorts",
    "cohort_memberships",
    "instructor_assignments",
    "courses",
    "course_versions",
    "course_modules",
    "lessons",
    "learning_objectives",
    "lesson_objectives",
    "course_instructor_assignments",
    "enrollments",
    "learning_events",
    "progress_snapshots",
    "assessments",
    "assessment_versions",
    "questions",
    "assessment_items",
    "assessment_item_objectives",
    "assessment_attempts",
    "responses",
    "grading_results",
    "rubrics",
    "rubric_criteria",
    "rubric_scores",
    "grading_reviews",
    "documents",
    "document_versions",
    "document_processing_jobs",
    "document_chunks",
    "ai_conversations",
    "ai_messages",
    "ai_jobs",
    "ai_usage_records",
    "ai_generation_reviews",
    "chunk_embeddings",
    "learner_objective_mastery",
    "recommendations",
    "remediation_plans",
    "remediation_plan_items",
    "tenant_subscriptions",
    "tenant_usage_records",
    "billing_events",
    "idempotency_records",
    "audit_events",
    "notifications",
    "outbox_events",
)


def build_enable_rls_sql(table_name: str) -> list[str]:
    """Generate DDL statements to enable and force fail-closed RLS on a tenant-owned table."""
    policy_name = f"{table_name}_tenant_isolation"
    return [
        f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY;",
        f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY;",
        f"DROP POLICY IF EXISTS {policy_name} ON {table_name};",
        f"""
        CREATE POLICY {policy_name}
        ON {table_name}
        USING (
            tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        )
        WITH CHECK (
            tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        );
        """.strip(),
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {table_name} TO akademia_app, akademia_worker;",
        f"GRANT SELECT ON TABLE {table_name} TO akademia_readonly;",
    ]


def build_disable_rls_sql(table_name: str) -> list[str]:
    policy_name = f"{table_name}_tenant_isolation"
    return [
        f"DROP POLICY IF EXISTS {policy_name} ON {table_name};",
        f"ALTER TABLE {table_name} NO FORCE ROW LEVEL SECURITY;",
        f"ALTER TABLE {table_name} DISABLE ROW LEVEL SECURITY;",
    ]
