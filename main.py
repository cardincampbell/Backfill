from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.db.database import init_db
from app.routes import router as api_router
from app.webhooks.retell_hooks import router as retell_router
from app.webhooks.scheduling_hooks import router as scheduling_router
from app.webhooks.twilio_hooks import router as twilio_router
from app.web_views import router as web_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="Backfill",
    description="AI coordination layer for shift coverage — powered by Retell AI",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(api_router)
app.include_router(web_router)
app.include_router(retell_router)
app.include_router(scheduling_router)
app.include_router(twilio_router)
