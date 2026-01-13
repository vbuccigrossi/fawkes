"""
Fawkes Web UI - Main FastAPI Application

This is the entry point for the Fawkes web dashboard backend.
Provides REST API and WebSocket endpoints for managing fuzzing campaigns.
"""

import logging
import os
import sys
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

# Add parent directory to path to import Fawkes modules
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from api.routes import system, jobs, crashes, workers, config, auth, vms
from api.routes import isos, images, snapshots, architectures, vm_install, paths, vm_configs, vm_runner
from api.websocket import websocket_manager, websocket_endpoint
from api.database import db_manager
from api.executor import initialize_executor, job_executor

logger = logging.getLogger("fawkes.web")
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - startup and shutdown events."""
    # Startup
    logger.info("Starting Fawkes Web UI...")
    db_manager.initialize()

    # Initialize job executor
    executor = initialize_executor(db_manager)
    logger.info("Job executor initialized")

    # Start WebSocket background tasks
    import asyncio
    websocket_task = asyncio.create_task(websocket_manager.broadcast_loop())

    logger.info("Fawkes Web UI started successfully")
    logger.info("Dashboard: http://localhost:8000")
    logger.info("API docs: http://localhost:8000/api/docs")

    yield

    # Shutdown
    logger.info("Shutting down Fawkes Web UI...")

    # Shutdown job executor (stops all running jobs)
    if executor:
        executor.shutdown()

    websocket_task.cancel()
    db_manager.close()
    logger.info("Fawkes Web UI shut down successfully")


# Create FastAPI app
app = FastAPI(
    title="Fawkes Web UI API",
    description="REST API and WebSocket endpoints for Fawkes Fuzzer",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json"
)

# Trailing slash redirect middleware for API routes
class TrailingSlashMiddleware(BaseHTTPMiddleware):
    """Redirect API routes without trailing slash to version with trailing slash."""
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        # Only redirect API routes that don't have trailing slashes
        if path.startswith("/api/") and not path.endswith("/") and "." not in path.split("/")[-1]:
            # Check if it's a dynamic route (contains {param})
            # If the path doesn't have path parameters (like /api/v1/jobs vs /api/v1/jobs/123)
            segments = path.rstrip("/").split("/")
            # Only redirect list endpoints (not specific resource endpoints)
            if segments[-1] in ("jobs", "crashes", "workers", "vms", "config", "isos", "images", "snapshots", "architectures", "vm-install", "vm-runner", "vm-configs"):
                return RedirectResponse(url=path + "/", status_code=307)
        return await call_next(request)

app.add_middleware(TrailingSlashMiddleware)

# CORS middleware (allow all origins in development)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Exception handlers
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "error": True}
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "error": True}
    )

# API routes
app.include_router(system.router, prefix="/api/v1/system", tags=["system"])
app.include_router(jobs.router, prefix="/api/v1/jobs", tags=["jobs"])
app.include_router(crashes.router, prefix="/api/v1/crashes", tags=["crashes"])
app.include_router(workers.router, prefix="/api/v1/workers", tags=["workers"])
app.include_router(config.router, prefix="/api/v1/config", tags=["config"])
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(vms.router, prefix="/api/v1/vms", tags=["vms"])

# VM Setup routes
app.include_router(isos.router, prefix="/api/v1/isos", tags=["vm-setup"])
app.include_router(images.router, prefix="/api/v1/images", tags=["vm-setup"])
app.include_router(snapshots.router, prefix="/api/v1/snapshots", tags=["vm-setup"])
app.include_router(architectures.router, prefix="/api/v1/architectures", tags=["vm-setup"])
app.include_router(vm_install.router, prefix="/api/v1/vm-install", tags=["vm-setup"])

# Paths configuration route
app.include_router(paths.router, prefix="/api/v1/paths", tags=["config"])

# VM Configs management route
app.include_router(vm_configs.router, prefix="/api/v1/vm-configs", tags=["vm-configs"])

# VM Runner route (for agent installation and snapshot creation)
app.include_router(vm_runner.router, prefix="/api/v1/vm-runner", tags=["vm-runner"])

# WebSocket endpoint
app.add_api_websocket_route("/ws", websocket_endpoint)

# Health check endpoint - must be defined before catch-all routes
@app.get("/health")
async def health_check():
    """Simple health check endpoint."""
    return {
        "status": "ok",
        "service": "fawkes-web-ui",
        "version": "1.0.0"
    }

# Serve frontend static files (production mode)
frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="assets")

    @app.get("/", response_class=FileResponse)
    async def serve_frontend():
        """Serve the React frontend."""
        return FileResponse(str(frontend_dist / "index.html"))

    @app.get("/{full_path:path}", response_class=FileResponse)
    async def serve_frontend_routes(full_path: str):
        """Serve frontend for all routes (SPA routing)."""
        # Don't serve frontend for API routes
        if full_path.startswith("api/") or full_path.startswith("ws"):
            return JSONResponse(status_code=404, content={"detail": "Not found"})

        file_path = frontend_dist / full_path
        if file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(frontend_dist / "index.html"))
else:
    logger.warning("Frontend dist/ not found - run 'npm run build' in frontend/")
    logger.info("Running in API-only mode. Frontend available at http://localhost:5173 (dev server)")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
