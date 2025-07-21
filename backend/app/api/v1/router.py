from fastapi import APIRouter

from app.api.v1.endpoints import repositories, search, ai, files, collaboration

api_router = APIRouter()

# Include all endpoint routers
api_router.include_router(
    repositories.router, prefix="/repositories", tags=["repositories"]
)
api_router.include_router(search.router, prefix="/search", tags=["search"])
api_router.include_router(ai.router, prefix="/ai", tags=["ai"])
api_router.include_router(files.router, prefix="/files", tags=["files"])
api_router.include_router(
    collaboration.router, prefix="/collaboration", tags=["collaboration"]
)
