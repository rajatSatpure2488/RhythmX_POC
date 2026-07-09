"""
MediSync FastAPI Backend — main.py
Entry point: loads config, registers routers, configures CORS.
"""

# logger first — initializes the rotating file handler before anything else logs.
from      app.core.logging import logger as _logger  # noqa: F401
# config must be imported next — it loads .env at module level
from app.core import config

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.http_client import HTTPClientManager
from app.routes import upload
from      app.push_data.emr_auth_client import emr_auth_client
from      app.routes import ai_explain_router, auth_router, dryrun_router, execute_mapping_router, logs_router, push_data_router

app = FastAPI(
    title="MediSync API",
    description="Clinical Notes Integration Platform",
    version="1.0.0",
)

# CORS — allow all Vite dev ports
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8501",
        "http://127.0.0.1:8501",
        "http://localhost:8502",
        "http://127.0.0.1:8502",
        "http://localhost:8503",
        "http://127.0.0.1:8503",
        "http://localhost:8888",
        "http://127.0.0.1:8888",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth_router.router,    prefix="/auth",    tags=["Authentication"])
app.include_router(upload.router,  prefix="/upload",  tags=["Upload"])
app.include_router(execute_mapping_router.router, prefix="/mapping", tags=["Mapping"])
app.include_router(dryrun_router.router,  prefix="/dryrun",  tags=["DryRun"])
app.include_router(push_data_router.router,       prefix="/push",    tags=["Push"])
app.include_router(ai_explain_router.router, prefix="/ai",      tags=["AI Assistant"])
app.include_router(logs_router.router,       prefix="/logs",     tags=["Logs"])


@app.on_event("startup")
async def startup_event():
    """Validate credentials — warn but don't crash (dev mode works without them)."""
    try:
        config.validate()
    except Exception as e:
        import logging
        logging.getLogger("medisync").warning(
            f"[startup] Missing {emr_auth_client.emr_name} credentials — running in dev/demo mode. {e}"
        )


@app.on_event("shutdown")
async def shutdown_event():
    """Close shared outbound HTTP connections."""
    await HTTPClientManager.close_all()


@app.get("/", tags=["Health"])
async def health_check():
    return {
        "status":        "ok",
        "service":       "MediSync API",
        "version":       "1.0.0",
        "ehr_connected": bool(emr_auth_client.value("client_id")),
        "emr_name":      emr_auth_client.emr_name,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
