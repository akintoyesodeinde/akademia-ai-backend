from fastapi import APIRouter

from app.api.v1.endpoints import (
    ai_tutor,
    assessments,
    auth,
    courses,
    documents,
    learning_intelligence,
    operations,
    tenants,
)

api_v1_router = APIRouter()
api_v1_router.include_router(auth.router)
api_v1_router.include_router(tenants.router)
api_v1_router.include_router(courses.router)
api_v1_router.include_router(assessments.router)
api_v1_router.include_router(documents.router)
api_v1_router.include_router(ai_tutor.router)
api_v1_router.include_router(learning_intelligence.router)
api_v1_router.include_router(operations.router)
