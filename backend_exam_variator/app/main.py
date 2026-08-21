"""FastAPI application factory."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import FRONTEND_DIR, settings
from .routers import health, jobs


def _shell(subpath: str) -> FileResponse:
    return FileResponse(FRONTEND_DIR / "jobs" / "shell" / subpath / "index.html")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Exam Variator API",
        description="Indonesian exam question variation generator",
        version="1.0.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(jobs.router)

    if FRONTEND_DIR.is_dir():
        @app.get("/jobs/{job_id}", include_in_schema=False)
        def job_shell(job_id: str) -> FileResponse:
            return _shell("")

        @app.get("/jobs/{job_id}/export", include_in_schema=False)
        def job_export_shell(job_id: str) -> FileResponse:
            return _shell("export")

        @app.get("/jobs/{job_id}/variations", include_in_schema=False)
        def job_variations_shell(job_id: str) -> FileResponse:
            return _shell("variations")

        app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

    return app


app = create_app()
