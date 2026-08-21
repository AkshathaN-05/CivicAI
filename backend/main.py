from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from routers.health import router as health_router
from routers.reports import router as reports_router

app = FastAPI(
    title="CivicAI Backend",
    version="0.1.0",
    description="Civic issue reporting API — Mangaluru, Karnataka",
)

# CORS — restricted to ALLOWED_ORIGINS (Part A §13)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.ALLOWED_ORIGINS.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix="/api/v1")
app.include_router(reports_router, prefix="/api/v1")
