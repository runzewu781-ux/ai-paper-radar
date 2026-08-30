from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

from app.core.config import get_settings
from app.api.routes import router as api_router
from app.services.scheduler import start_scheduler

settings = get_settings()

app = FastAPI(title="AI Paper Radar", version="0.1.0")


@app.on_event("startup")
def _setup_app_logging() -> None:
    lg = logging.getLogger("app")
    lg.disabled = False
    lg.setLevel(logging.INFO)
    if not lg.handlers:
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        lg.addHandler(h)
    lg.propagate = False


@app.on_event("startup")
def _init_database() -> None:
    from app.db.session import init_db

    init_db()


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
start_scheduler(app)
