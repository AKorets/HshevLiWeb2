import asyncio
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .auth import require_api_key
from .cache import background_refresh_loop, get_cache
from .config import settings
from .database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.database_url:
        init_db(settings.database_url)
    asyncio.create_task(background_refresh_loop())
    yield


app = FastAPI(title="HshevLi Rates API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

DEFAULT_CURRENCIES = ["ILS", "USD", "EUR", "GBP", "RUB", "CHF", "PLN", "HUF", "JPY"]


@app.get("/health")
async def health() -> dict:
    cache = get_cache()
    return {
        "status": "ok",
        "xe_credentials_configured": bool(settings.xe_account_id and settings.xe_api_key),
        "rates_fresh": cache.is_fresh,
        "last_fetch_error": cache.last_fetch_error,
    }


@app.get("/currencies")
async def get_currencies() -> dict:
    return {"currencies": DEFAULT_CURRENCIES}


@app.get("/rates/current", dependencies=[Depends(require_api_key)])
async def get_current_rates() -> dict:
    return get_cache().snapshot()


@app.post("/rates/refresh", dependencies=[Depends(require_api_key)])
async def refresh_rates() -> dict:
    return await get_cache().try_manual_refresh()
