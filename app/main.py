from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.database import get_db
from app.api.routes.query import router as query_router
from app.api.routes.screenshots import router as screenshots_router
from app.api.routes.analytics import router as analytics_router
from app.api.routes.admin_static import router as admin_static_router


app = FastAPI(title=settings.APP_NAME, version="0.1.0", description="CostChecker API")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    return JSONResponse(status_code=404, content={"status": "error", "error_type": "not_found", "message": "Not Found"})


@app.exception_handler(500)
async def server_error_handler(request: Request, exc):
    return JSONResponse(status_code=500, content={"status": "error", "error_type": "internal_error", "message": "Internal Server Error"})


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"status": "error", "error_type": "validation_error", "message": str(exc)})


@app.get("/api/health")
def health():
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# Routers
app.include_router(query_router)
app.include_router(screenshots_router)
app.include_router(analytics_router)
app.include_router(admin_static_router)

# Simple frontend playground (no auth) for quick manual testing
app.mount("/playground", StaticFiles(directory="playground", html=True), name="playground")
