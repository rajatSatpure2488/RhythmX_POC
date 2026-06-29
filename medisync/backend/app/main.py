"""
MediSync FastAPI Backend — main.py
Entry point: loads config, registers routers, configures CORS.
"""

# logger first — initializes the rotating file handler before anything else logs.
from app.core import logger as _logger  # noqa: F401
# config must be imported next — it loads .env at module level
from app.core import config

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.mappers.router import router as frontend_api_router

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

# Frontend API routes live in app/mappers now.
app.include_router(frontend_api_router, tags=["Frontend API"])

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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3000)
