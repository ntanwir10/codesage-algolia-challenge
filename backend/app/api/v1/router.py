from fastapi import APIRouter

from app.api.v1.endpoints import (
    repositories,
    ai,
    performance,
)

api_router = APIRouter()

# Include only essential endpoint routers for MCP-first architecture
api_router.include_router(
    repositories.router, prefix="/repositories", tags=["repositories"]
)
api_router.include_router(ai.router, prefix="/ai", tags=["ai"])
api_router.include_router(performance.router, prefix="/performance", tags=["performance"])
