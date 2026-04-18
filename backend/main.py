import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import rates
from services.xe_service import background_refresh_loop

app = FastAPI(title="HshevLi Rates API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(rates.router)


@app.on_event("startup")
async def startup() -> None:
    asyncio.create_task(background_refresh_loop())
