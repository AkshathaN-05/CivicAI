from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from config import settings
from dependencies import limiter
from routers.health import router as health_router
from routers.reports import router as reports_router

app = FastAPI(
    title="CivicAI Backend",
    version="0.1.0",
    description="Civic issue reporting API — Mangaluru, Karnataka",
)

# Rate limiter — attach to app state so slowapi middleware can find it (Part A §13, T3-1)
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def _rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Return 429 with a consistent JSON body when the rate limit is exceeded."""
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded. Please slow down."},
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
