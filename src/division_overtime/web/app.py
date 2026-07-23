from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from division_overtime.database import Database
from division_overtime.employee_management import EmployeeManagementService
from division_overtime.kot_employee_sync import KotEmployeeClient, KotEmployeeSyncService
from division_overtime.web.auth import AuthService
from division_overtime.web.config import WebConfig, load_web_config
from division_overtime.web.routes.auth import router as auth_router
from division_overtime.web.routes.employees import router as employees_router
from division_overtime.web.routes.kot_sync import router as kot_sync_router
from division_overtime.web.routes.system import router as system_router


def create_app(config: WebConfig | None = None) -> FastAPI:
    web_config = config or load_web_config()
    app = FastAPI(
        title="division-overtime Web administration",
        version=_read_version(web_config.root),
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )
    app.state.web_config = web_config
    database = Database(web_config.database_path)
    database.initialize()
    app.state.employee_management_service = EmployeeManagementService(
        database, web_config.employee_csv
    )
    if web_config.kot_token:
        app.state.kot_employee_sync_service = KotEmployeeSyncService(
            database,
            web_config.employee_csv,
            KotEmployeeClient(
                base_url=web_config.kot_base_url,
                token=web_config.kot_token,
                connect_timeout=web_config.kot_connect_timeout,
                read_timeout=web_config.kot_read_timeout,
                retry_count=web_config.kot_retry_count,
                retry_backoff=web_config.kot_retry_backoff,
            ),
        )
    app.state.auth_service = AuthService(
        admin_username=web_config.admin_username,
        admin_password_hash=web_config.admin_password_hash,
        session_secret=web_config.session_secret,
        session_max_age_seconds=web_config.session_max_age_seconds,
        login_max_attempts=web_config.login_max_attempts,
        login_window_seconds=web_config.login_window_seconds,
        login_lockout_seconds=web_config.login_lockout_seconds,
    )
    app.include_router(auth_router)
    app.include_router(system_router)
    app.include_router(employees_router)
    app.include_router(kot_sync_router)

    assets_dir = web_config.frontend_dist / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/", include_in_schema=False)
    def frontend_index():
        index_path = web_config.frontend_dist / "index.html"
        if index_path.is_file():
            return FileResponse(index_path)
        return JSONResponse(
            status_code=503,
            content={
                "status": "frontend_not_built",
                "message": "Run npm ci and npm run build in frontend/.",
            },
        )

    @app.get("/{path:path}", include_in_schema=False)
    def frontend_fallback(path: str) -> FileResponse:
        if path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")

        requested = (web_config.frontend_dist / path).resolve()
        dist = web_config.frontend_dist.resolve()
        if requested.is_relative_to(dist) and requested.is_file():
            return FileResponse(requested)

        index_path = web_config.frontend_dist / "index.html"
        if index_path.is_file():
            return FileResponse(index_path)
        raise HTTPException(status_code=404, detail="Frontend is not built")

    return app


def _read_version(root: Path) -> str:
    version_path = root / "VERSION"
    if not version_path.is_file():
        return "unknown"
    return version_path.read_text(encoding="utf-8").strip() or "unknown"
