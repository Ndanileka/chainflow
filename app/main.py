from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.database.session import Base, engine
from app.routes.dashboard import router as dashboard_router


Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="ChainFlow",
    description="Educational simulation software for chain-based financial systems.",
    version="0.1.0",
)

from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
app.include_router(dashboard_router)
