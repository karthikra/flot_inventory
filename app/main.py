from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader

from app.database import engine
from app.models import Base
from app.routers import capture, dashboard, export, items, rooms, search


@asynccontextmanager
async def lifespan(app: FastAPI):
    # create tables on startup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # ensure data directories exist
    Path("data/images/originals").mkdir(parents=True, exist_ok=True)
    Path("data/images/thumbnails").mkdir(parents=True, exist_ok=True)
    Path("data/videos").mkdir(parents=True, exist_ok=True)
    Path("data/frames").mkdir(parents=True, exist_ok=True)
    Path("data/audio").mkdir(parents=True, exist_ok=True)

    yield

    await engine.dispose()


app = FastAPI(title="Home Inventory", lifespan=lifespan)

# templates
templates_dir = Path(__file__).parent / "templates"
app.state.templates = Environment(loader=FileSystemLoader(str(templates_dir)), autoescape=True)

# patch TemplateResponse onto jinja2 Environment for convenience
from starlette.responses import HTMLResponse


def _template_response(self, name, context):
    template = self.get_template(name)
    html = template.render(**context)
    return HTMLResponse(html)


app.state.templates.TemplateResponse = lambda name, ctx: _template_response(app.state.templates, name, ctx)

# static files
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# also serve data/images as static for thumbnails/originals
data_images_dir = Path("data/images")
data_images_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static/images", StaticFiles(directory=str(data_images_dir)), name="images")

# routers
app.include_router(dashboard.router)
app.include_router(rooms.router)
app.include_router(items.router)
app.include_router(capture.router)
app.include_router(search.router)
app.include_router(export.router)
