from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.core.config import get_settings
from app.core.database import engine
from app.models import Base
from app.services.import_service import ensure_reference_levels

settings = get_settings()

app = FastAPI(title=settings.app_name, version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

AUDIO_DIR = Path(__file__).resolve().parents[2] / "audio"
if AUDIO_DIR.exists():
    app.mount("/audio", StaticFiles(directory=AUDIO_DIR), name="audio")

app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    from sqlalchemy.orm import Session

    db = Session(bind=engine)
    try:
        ensure_reference_levels(db)
    finally:
        db.close()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
