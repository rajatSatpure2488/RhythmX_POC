# Set up FastAPI
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from dr_chrono.backend.core.logging_config import setup_logging

setup_logging()

from backend.router import router as drchrono_router


BASE_DIR = Path(__file__).resolve().parents[1]
FRONTEND_DIST = BASE_DIR / "frontend" / "dist"
FRONTEND_INDEX = FRONTEND_DIST / "index.html"


app = FastAPI(
    title="Dynamic EHR API Service",
    description="API service for uploading CSV/JSON/ZIP files and calling DrChrono APIs dynamically.",
    version="1.0.0",
    docs_url="/ehr_docs",
    redoc_url="/ehr_redoc",
    openapi_url="/ehr_openapi.json",
)

# Set up CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Router for upload APIs
app.include_router(drchrono_router, tags=["EHR"])

if (FRONTEND_DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="frontend-assets")


@app.get("/", include_in_schema=False)
async def frontend_app():
    if FRONTEND_INDEX.exists():
        return FileResponse(FRONTEND_INDEX)

    return HTMLResponse(
        """
        <html>
          <body style="font-family: sans-serif; padding: 32px;">
            <h1>DrChrono frontend is not built yet.</h1>
            <p>Run <code>cd dr_chrono/frontend && npm run build</code>, then restart the backend.</p>
          </body>
        </html>
        """,
        status_code=200,
    )


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
