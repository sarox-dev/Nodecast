from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from app.api.routes.search import router as search_router
from app.api.routes.capture import router as capture_router
from app.services.database import init_db

app = FastAPI()

@app.on_event("startup")
def startup():
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


@app.get("/api/version")
def get_version():
    return {"version": "0.0.3"}

@app.get("/api/update/check")
def check_update():
    import requests
    try:
        resp = requests.get("https://api.github.com/repos/sarox-dev/Recollect/releases/latest", timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            latest = data.get("tag_name", "").lstrip("v")
            current = "0.0.3"
            return {
                "current_version": current,
                "latest_version": latest,
                "has_update": latest > current if latest else False,
                "release_url": data.get("html_url", ""),
                "release_notes": data.get("body", "")[:500] if data.get("body") else "",
                "published_at": data.get("published_at", ""),
            }
        return {"current_version": "0.0.3", "error": "Could not reach GitHub"}
    except Exception as e:
        return {"current_version": "0.0.3", "error": str(e)}

@app.get("/api/update/install")
def install_update():
    import subprocess
    try:
        result = subprocess.run(
            ["bash", "-c", "curl -fsSL https://github.com/sarox-dev/Recollect/releases/latest/download/install.sh | bash"],
            capture_output=True, text=True, timeout=120
        )
        return {"success": result.returncode == 0, "output": result.stdout[:500], "error": result.stderr[:500] if result.stderr else ""}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Update timed out"}
    except Exception as e:
        return {"success": False, "error": str(e)}

templates = Jinja2Templates(directory="app/templates")

@app.get("/")
def home(request: Request):
    return templates.TemplateResponse(request, "index.html")