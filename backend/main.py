import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from config import settings
from dependencies import limiter
from routers.health import router as health_router
from routers.reports import router as reports_router
from routers.admin import router as admin_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — pre-warm JWKS cache at startup so first-request
    JWT verification does not fail due to an empty cache when the network
    is briefly unavailable, and so any misconfiguration is surfaced immediately
    in the startup logs rather than as a cryptic 401 on the first request.
    """
    from security.jwt_verify import _fetch_jwks
    import security.jwt_verify as _jv

    cache = _fetch_jwks()
    if cache:
        _jv._jwks_cache = cache
        logger.info("Startup JWKS pre-warm succeeded — %d key(s) loaded.", len(cache))
    else:
        logger.warning(
            "Startup JWKS pre-warm returned no keys. "
            "JWT verification will attempt a live fetch on the first request. "
            "Check SUPABASE_URL and outbound HTTPS connectivity."
        )

    # Validate that migration 007 has been applied (reports.status column).
    # Logs a clear WARNING if not — does not block startup.
    from db.schema_validator import validate_reports_schema
    validate_reports_schema()

    yield
    # No teardown required.


app = FastAPI(
    title="CivicAI Backend",
    version="0.1.0",
    description="Civic issue reporting API — Mangaluru, Karnataka",
    lifespan=lifespan,
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
app.include_router(admin_router, prefix="/api/v1")
