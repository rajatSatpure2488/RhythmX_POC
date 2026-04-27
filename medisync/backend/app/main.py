"""
MediSync FastAPI Backend — main.py
Entry point: loads config, registers routers, configures CORS.
"""

# config must be imported first — it loads .env at module level
from app.core import config

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes import auth, upload, mapping, dryrun, push

app = FastAPI(
    title="MediSync API",
    description="Clinical Notes Integration Platform — DrChrono EHR",
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
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth.router,    prefix="/auth",    tags=["Authentication"])
app.include_router(upload.router,  prefix="/upload",  tags=["Upload"])
app.include_router(mapping.router, prefix="/mapping", tags=["Mapping"])
app.include_router(dryrun.router,  prefix="/dryrun",  tags=["DryRun"])
app.include_router(push.router,    prefix="/push",    tags=["Push"])


@app.on_event("startup")
async def startup_event():
    """Validate credentials — warn but don't crash (dev mode works without them)."""
    try:
        config.validate()
    except Exception as e:
        import logging
        logging.getLogger("medisync").warning(
            f"[startup] Missing DrChrono credentials — running in dev/demo mode. {e}"
        )


@app.get("/", tags=["Health"])
async def health_check():
    return {
        "status":        "ok",
        "service":       "MediSync API",
        "version":       "1.0.0",
        "ehr_connected": bool(config.DRCHRONO_CLIENT_ID),
    }
