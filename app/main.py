from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from app.api.routes.search import router as search_router

app = FastAPI()
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(search_router)

templates = Jinja2Templates(directory="app/templates")

@app.get("/")
def home(request: Request):
    return templates.TemplateResponse(request, "index.html")
