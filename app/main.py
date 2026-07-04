from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from app.api.routes.search import router as search_router
from app.api.routes.capture import router as capture_router
from app.api.routes.auth import router as auth_router
from app.services.database import init_db, user_count

app = FastAPI()

@app.on_event("startup")
def startup():
    # Auto-migrate existing data to per-user structure
    init_db()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(search_router)
app.include_router(capture_router, prefix="/api")
app.include_router(auth_router)

# ─── Auth status template variable ────────────────────────────────
templates = Jinja2Templates(directory="app/templates")


def _auth_context(request: Request) -> dict:
    """Check if user is logged in via cookie."""
    from app.services.auth import get_user_from_cookie
    import asyncio
    try:
        loop = asyncio.get_running_loop()
        user = loop.run_until_complete(get_user_from_cookie(request))
    except RuntimeError:
        user = None
    if user:
        return {"logged_in": True, "username": user["username"]}
    return {"logged_in": False, "username": ""}


# ─── Pages ────────────────────────────────────────────────────────
@app.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html")


@app.get("/register")
def register_page(request: Request):
    no_users = user_count() == 0
    return templates.TemplateResponse(request, "register.html", {"no_users": no_users})


@app.get("/")
def home(request: Request):
    # If no users exist, redirect to register (setup)
    if user_count() == 0:
        return RedirectResponse(url="/register")
    ctx = _auth_context(request)
    return templates.TemplateResponse(request, "index.html", ctx)


# ─── API endpoints ────────────────────────────────────────────────
@app.get("/api/version")
def get_version():
    return {"version": "0.1.0"}


@app.get("/api/update/check")
def check_update():
    import requests
    try:
        resp = requests.get(
            "https://api.github.com/repos/sarox-dev/Recollect/releases/latest",
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            latest = data.get("tag_name", "").lstrip("v")
            current = "0.1.0"
            return {
                "current_version": current,
                "latest_version": latest,
                "has_update": latest > current if latest else False,
                "release_url": data.get("html_url", ""),
                "release_notes": (data.get("body", "")[:500] if data.get("body") else ""),
                "published_at": data.get("published_at", ""),
            }
        return {"current_version": "0.1.0", "error": "Could not reach GitHub"}
    except Exception as e:
        return {"current_version": "0.1.0", "error": str(e)}


@app.get("/api/update/install")
def install_update():
    import subprocess
    try:
        result = subprocess.run(
            ["bash", "-c",
             "curl -fsSL https://github.com/sarox-dev/Recollect/releases/latest/download/install.sh | bash"],
            capture_output=True, text=True, timeout=120,
        )
        return {
            "success": result.returncode == 0,
            "output": result.stdout[:500],
            "error": result.stderr[:500] if result.stderr else "",
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Update timed out"}
    except Exception as e:
        return {"success": False, "error": str(e)}