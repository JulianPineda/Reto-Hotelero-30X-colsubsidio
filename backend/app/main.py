from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.database import init_db_pool, close_db_pool


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db_pool()
    # Embedding model loaded here (once at startup, not per request) —
    # uncomment once T-009 (EPIC-3) adds app/agents/catalog/embedder.py:
    # from app.agents.catalog.embedder import load_model
    # load_model()
    yield
    await close_db_pool()


app = FastAPI(
    title="Inventory Loss Reduction API",
    version="0.1.0",
    docs_url="/api/docs" if settings.app_env == "development" else None,
    redoc_url=None,
    lifespan=lifespan,
)

# CORS — no wildcards (security rule CWE-942)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)


# Global error handler — never expose stack traces (CWE-209)
@app.exception_handler(Exception)
async def generic_exception_handler(request, exc):
    import uuid
    import logging
    correlation_id = str(uuid.uuid4())
    logging.getLogger(__name__).error(
        "Unhandled exception",
        extra={"correlation_id": correlation_id, "exc": str(exc)},
        exc_info=True,
    )
    return JSONResponse(
        status_code=500,
        content={"error": "Error interno del servidor.", "correlation_id": correlation_id},
    )


# Routers — registered here once implemented
from app.api.health import router as health_router
app.include_router(health_router, prefix="/api/v1")

# WS /ws/voice/{session_id} — no /api/v1 prefix, matches nginx's /ws/ location
# and the literal path in docs/architecture/api-contracts.md.
from app.agents.voice.router import router as voice_router
app.include_router(voice_router)

from app.agents.parser.router import router as parser_router
app.include_router(parser_router, prefix="/api/v1")

# Uncomment as each Epic is implemented:
# from app.agents.catalog.router import router as catalog_router
# from app.agents.auditor.router import router as auditor_router
# from app.agents.exporter.router import router as exporter_router
# from app.api.supervisor import router as supervisor_router
# from app.api.warehouses import router as warehouses_router
