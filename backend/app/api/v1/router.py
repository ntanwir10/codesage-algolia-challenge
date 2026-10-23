from fastapi import APIRouter, Depends

from app.api.v1.endpoints import (
    ai,
    performance,
    repositories,
)
from app.core.security import require_api_key

api_router = APIRouter()

# Include only essential endpoint routers for MCP-first architecture
api_router.include_router(
    repositories.router, prefix="/repositories", tags=["repositories"]
)
api_router.include_router(ai.router, prefix="/ai", tags=["ai"])
api_router.include_router(
    performance.router,
    prefix="/performance",
    tags=["performance"],
    dependencies=[Depends(require_api_key)],
)
