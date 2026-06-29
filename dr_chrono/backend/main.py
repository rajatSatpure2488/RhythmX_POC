# Set up FastAPI
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from backend.router import router as drchrono_router


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


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )