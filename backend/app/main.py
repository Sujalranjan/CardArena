"""FastAPI application entrypoint for CardArena backend."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.auth import router as auth_router
from app.api.fairness import router as fairness_router
from app.api.rooms import router as rooms_router
from app.core.config import settings
from app.core.logging import logger, setup_logging
from app.database.session import Base, engine
import app.games  # Ensure concrete games like Hearts are registered
from app.websocket.endpoints import router as ws_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info("Initializing CardArena backend service...")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables verified/created.")

    yield

    logger.info("Shutting down CardArena backend...")
    await engine.dispose()


app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix=settings.API_V1_STR)
app.include_router(rooms_router, prefix=settings.API_V1_STR)
app.include_router(fairness_router, prefix=settings.API_V1_STR)
app.include_router(ws_router)


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "CardArena Backend", "phase": "2 - Hearts"}
