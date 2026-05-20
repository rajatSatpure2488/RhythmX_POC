"""
MediSync FastAPI Backend — main.py
Entry point: loads config, registers routers, configures CORS.
"""

# config must be imported first — it loads .env at module level
from app.core import config

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes import auth, upload, mapping, dryrun, push, ai_explain, drchrono, fhir_proxy

# ── FHIR Pipeline (independent module — delete this block to remove) ──
try:
    from app.fhir_pipeline.router import router as pipeline_router
    _PIPELINE_AVAILABLE = True
except ImportError:
    _PIPELINE_AVAILABLE = False

# ── FHIR R5 Integration (independent module — delete this block to remove) ──
try:
    from app.fhir_r5.router import router as fhir_r5_router
    _FHIR_R5_AVAILABLE = True
except ImportError:
    _FHIR_R5_AVAILABLE = False

# ── Rule-Based Mapper (FHIR R5 → DrChrono — delete this block to remove) ──
try:
    from app.mappers.router import router as mapper_router
    _MAPPER_AVAILABLE = True
except ImportError:
    _MAPPER_AVAILABLE = False

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
        "http://localhost:8888",
        "http://127.0.0.1:8888",
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
app.include_router(push.router,       prefix="/push",    tags=["Push"])
app.include_router(ai_explain.router, prefix="/ai",      tags=["AI Assistant"])
app.include_router(drchrono.router,   prefix="/drchrono", tags=["DrChrono Resources"])
app.include_router(fhir_proxy.router, prefix="/fhir-proxy", tags=["FHIR Proxy"])

# ── FHIR Pipeline (independent — remove this line to disconnect) ──
if _PIPELINE_AVAILABLE:
    app.include_router(pipeline_router, prefix="/pipeline", tags=["FHIR Pipeline"])

# ── FHIR R5 (independent — remove this line to disconnect) ──
if _FHIR_R5_AVAILABLE:
    app.include_router(fhir_r5_router, prefix="/fhir-r5", tags=["FHIR R5"])

# ── Rule-Based Mapper (independent — remove this line to disconnect) ──
if _MAPPER_AVAILABLE:
    app.include_router(mapper_router, prefix="/mapper", tags=["Mapper"])

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
