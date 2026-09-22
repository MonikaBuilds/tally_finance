from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
from app.api.admin import router as admin_router
from app.api.dashboard import router as dashboard_router
from app.api.reports import router as reports_router
from app.api.tally import router as tally_router
from app.core.logging_config import configure_logging
from app.security.user_store import initialize_user_store
from app.tally.client import TallyClient


configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create authentication tables if they do not exist.
    initialize_user_store()

    # Start shared HTTP client for Tally connections.
    await TallyClient.start_shared_client()

    try:
        yield
    finally:
        await TallyClient.close_shared_client()


app = FastAPI(
    title="Tally Financial Intelligence API",
    version="1.0.0",
    lifespan=lifespan,
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(
    auth_router,
    prefix="/api/v1/auth",
    tags=["Authentication"],
)

app.include_router(
    admin_router,
    prefix="/api/v1/admin",
    tags=["Admin"],
)

app.include_router(
    tally_router,
    prefix="/api/v1/tally",
    tags=["Tally"],
)

app.include_router(
    dashboard_router,
    prefix="/api/v1/dashboard",
    tags=["Dashboard"],
)

app.include_router(
    reports_router,
    prefix="/api/v1/reports",
    tags=["Reports"],
)

app.include_router(
    chat_router,
    prefix="/api/v1",
    tags=["Chatbot"],
)


@app.get("/")
async def root():
    return {
        "message": "Tally Financial Intelligence API is running"
    }