import json
import os
import re

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from app.api.routes.search import router as search_router
from app.api.routes.capture import router as capture_router
from app.api.routes.auth import router as auth_router
from app.api.routes.layouts import router as layouts_router
from app.api.routes.knowledge import router as knowledge_router
from app.api.routes.renderers import router as renderers_router
from app.api.routes.ai_providers import router as ai_providers_router
from app.api.routes.library import router as library_router
from app.api.routes.entities import router as entities_router
from app.api.routes.atomics import router as atomics_router
from app.api.routes.extension import router as extension_router
from app.api.routes.memory import router as memory_router
from app.api.routes.admin import router as admin_router
from app.services.database import get_user_by_id, init_db, user_count
from app.services.auth import get_current_user
from app.services.auto_processor import start_auto_processor
from app.middleware.security import RequestSecurityMiddleware

app = FastAPI()

@app.on_event("startup")
def startup():
    # Auto-migrate existing data to per-user structure
    init_db()
    from app.services.database import get_global_setting, set_global_setting
    if get_global_setting("auto_update", "") == "":
        enabled = os.getenv("AUTO_UPDATE_DEFAULT", "false").lower() == "true"
        set_global_setting("auto_update", "true" if enabled else "false")
    # Start background AI auto-processor
    start_auto_processor()

configured_origins = [
    origin.strip()
    for origin in os.getenv("NODECAST_CORS_ORIGINS", "").split(",")
    if origin.strip()
]
app.add_middleware(RequestSecurityMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=configured_origins,
    allow_origin_regex=r"^(chrome-extension|moz-extension)://[a-zA-Z0-9_-]+$",
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(search_router)
app.include_router(capture_router, prefix="/api")
app.include_router(auth_router)
app.include_router(layouts_router)
app.include_router(knowledge_router)
app.include_router(renderers_router)
app.include_router(ai_providers_router)
app.include_router(library_router)
app.include_router(entities_router)
app.include_router(atomics_router)
app.include_router(extension_router)
app.include_router(memory_router)
app.include_router(admin_router)

# ─── Auth status template variable ────────────────────────────────
templates = Jinja2Templates(directory="app/templates")


async def _auth_context(request: Request) -> dict:
    """Check if user is logged in via cookie."""
    from app.services.auth import get_user_from_cookie
    user = await get_user_from_cookie(request)
    if user:
        stored = get_user_by_id(user["user_id"])
        return {"logged_in": True, "username": user["username"], "user": stored}
    return {"logged_in": False, "username": ""}


# ─── Pages ────────────────────────────────────────────────────────
@app.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html")


@app.get("/register")
def register_page(request: Request):
    no_users = user_count() == 0
    from app.services.database import get_registration_setting
    if not no_users and not get_registration_setting():
        return RedirectResponse(url="/login")
    return templates.TemplateResponse(request, "register.html", {"no_users": no_users})


@app.get("/forgot-password")
def forgot_password_page(request: Request):
    return templates.TemplateResponse(request, "forgot_password.html")


@app.get("/recovery/setup")
async def recovery_setup_page(request: Request):
    ctx = await _auth_context(request)
    user = ctx.get("user")
    if not user: return RedirectResponse(url="/login")
    if user.get("role") != "owner": return RedirectResponse(url="/")
    if user.get("recovery_setup_complete"): return RedirectResponse(url="/admin")
    return templates.TemplateResponse(request, "recovery_setup.html", ctx)


@app.get("/admin")
async def admin_page(request: Request):
    ctx = await _auth_context(request)
    user = ctx.get("user")
    if not user: return RedirectResponse(url="/login")
    if user.get("role") not in {"owner", "moderator"}: return RedirectResponse(url="/")
    if user.get("role") == "owner" and not user.get("recovery_setup_complete"): return RedirectResponse(url="/recovery/setup")
    from app.services.account_security import has_permission
    ctx["can_manage_members"] = has_permission(user, "manage_members")
    ctx["can_manage_resets"] = has_permission(user, "manage_member_resets")
    ctx["can_ai_policy"] = has_permission(user, "manage_ai_policy")
    return templates.TemplateResponse(request, "admin.html", ctx)


@app.get("/")
async def home(request: Request):
    # If no users exist, redirect to register (setup)
    if user_count() == 0:
        return RedirectResponse(url="/register")
    ctx = await _auth_context(request)
    user = ctx.get("user")
    if not user:
        return RedirectResponse(url="/login")
    if user.get("role") in {"owner", "moderator"}:
        return RedirectResponse(url="/recovery/setup" if user.get("role") == "owner" and not user.get("recovery_setup_complete") else "/admin")
    return templates.TemplateResponse(request, "index.html", ctx)


# ─── Version helpers ──────────────────────────────────────────────
def _load_version() -> dict:
    try:
        vp = os.path.join(os.path.dirname(__file__), "version.json")
        with open(vp) as f:
            return json.load(f)
    except Exception:
        return {"version": "0.0.0", "build": "unknown"}


VERSION_INFO = _load_version()
CURRENT_VERSION = VERSION_INFO["version"]
BUILD_DATE = VERSION_INFO["build"]


def _version_tuple(value: str) -> tuple[int, ...]:
    parts = [int(part) for part in re.findall(r"\d+", value)[:3]]
    return tuple((parts + [0, 0, 0])[:3])

# ─── API endpoints ────────────────────────────────────────────────
@app.get("/api/version")
def get_version():
    return {"version": CURRENT_VERSION, "build_date": BUILD_DATE}


def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    user = get_user_by_id(current_user["user_id"])
    if not user or user.get("role") != "owner":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


@app.get("/api/update/check")
def check_update(_admin: dict = Depends(require_admin)):
    import requests
    try:
        resp = requests.get(
            "https://api.github.com/repos/sarox-dev/Nodecast/releases/latest",
            timeout=10,
            headers={"Accept": "application/vnd.github+json"},
        )
        if resp.status_code == 200:
            data = resp.json()
            latest = data.get("tag_name", "").lstrip("v")
            return {
                "current_version": CURRENT_VERSION,
                "build_date": BUILD_DATE,
                "latest_version": latest,
                "has_update": bool(latest and _version_tuple(latest) > _version_tuple(CURRENT_VERSION)),
                "release_url": data.get("html_url", ""),
                "release_notes": (data.get("body", "")[:1000] if data.get("body") else ""),
                "published_at": data.get("published_at", ""),
            }
        return {"current_version": CURRENT_VERSION, "error": f"GitHub API returned {resp.status_code}"}
    except Exception as e:
        return {"current_version": CURRENT_VERSION, "error": str(e)}


@app.get("/api/update/install")
def install_update(_admin: dict = Depends(require_admin)):
    return {
        "release_url": "https://github.com/sarox-dev/Nodecast/releases/latest",
        "message": "Download the installer and SHA256SUMS from the release, verify the checksum, then run it.",
    }


@app.get("/api/server/health")
def server_health():
    from app.services.ai_batch import get_batch_status
    from app.services.database import get_global_setting, count_active_sessions, user_count, get_users_db

    auto_update = get_global_setting("auto_update", "false") == "true"
    active_sessions = count_active_sessions()
    ai_running = False
    if user_count() > 0:
        try:
            conn = get_users_db()
            try:
                user_ids = [r["id"] for r in conn.execute("SELECT id FROM users").fetchall()]
            finally:
                conn.close()
            for uid in user_ids:
                status = get_batch_status(uid)
                if status.get("running"):
                    ai_running = True
                    break
        except Exception:
            pass

    return {
        "version": CURRENT_VERSION,
        "build_date": BUILD_DATE,
        "active_sessions": active_sessions,
        "ai_running": ai_running,
        "auto_update_enabled": auto_update,
        "can_update": not ai_running and active_sessions == 0 and auto_update,
    }


@app.get("/api/server/settings")
def get_server_settings(_admin: dict = Depends(require_admin)):
    from app.services.database import get_global_setting
    return {
        "auto_update": get_global_setting("auto_update", "false") == "true",
        "installation_mode": os.getenv("NODECAST_INSTALL_MODE", "docker"),
    }


@app.put("/api/server/settings")
def set_server_settings(body: dict, _admin: dict = Depends(require_admin)):
    from app.services.database import set_global_setting
    if "auto_update" in body:
        set_global_setting("auto_update", "true" if body["auto_update"] else "false")
    return {"status": "ok"}
