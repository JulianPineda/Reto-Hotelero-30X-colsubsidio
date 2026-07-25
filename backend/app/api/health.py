from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    """No-auth health endpoint. Used by frontend to detect offline mode."""
    return {"status": "ok"}
