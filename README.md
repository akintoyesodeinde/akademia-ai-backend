# Akademia AI — Backend (`akademia-ai-backend`)

Production-Grade Multi-Tenant SaaS Learning Management & Intelligence Platform backend built with **Python 3.13**, **FastAPI**, **Pydantic v2**, **SQLAlchemy 2.x (Async)**, **Alembic**, and **PostgreSQL 16 + pgvector + Row-Level Security (RLS)**.

## Architecture Highlights
- **Multi-Tenant Isolation**: Shared PostgreSQL database and shared tables with strict `tenant_id` columns, composite tenant-aware foreign keys, and `ENABLE` + `FORCE ROW LEVEL SECURITY` policies using transaction-local `app.tenant_id` context.
- **Least-Privilege Database Roles**: Separate `akademia_migrator`, `akademia_app` (`NOSUPERUSER NOBYPASSRLS`), `akademia_worker` (`NOSUPERUSER NOBYPASSRLS`), and `akademia_readonly` roles.
- **Provider-Neutral Generative AI**: Decoupled interfaces (`LanguageModel`, `EmbeddingModel`, `CourseRetriever`, `ContentExtractor`, `AIUsageRecorder`, `AIJobService`, `AIEvaluator`) with pre-retrieval tenant/course authorization, citation verification, groundedness checks, and per-tenant quota enforcement.
- **Explainable Learning Intelligence**: Deterministic objective-level mastery aggregation from assessment evidence, knowledge-gap detection, traceable practice recommendations, and follow-up comparison.

## Quickstart (Local Docker Development)

```bash
docker compose up --build -d
docker compose exec api alembic upgrade head
docker compose exec api pytest
docker compose exec api ruff check .
```

See `docs/LOCAL_DEVELOPMENT.md` and `docs/IMPLEMENTATION_STATUS.md` for comprehensive documentation.
