"""POST /saved-deals — save a deal referencing an existing calculation."""

from __future__ import annotations
import uuid as uuid_mod
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session_factory

router = APIRouter(prefix="/saved-deals", tags=["saved-deals"])


class SavedDealIn(BaseModel):
    calculation_id: str
    user_id: str
    session_id: str
    deal_type: str = "exchange"
    headline_sell_currency: str | None = None
    headline_buy_currency: str | None = None
    headline_sell_amount: Decimal | None = None
    headline_receive_amount: Decimal | None = None
    tax_percent: Decimal = Decimal("0")
    note: str | None = None


async def _get_session() -> AsyncSession:
    factory = get_session_factory()
    async with factory() as session:
        yield session


@router.post("", status_code=201)
async def create_saved_deal(
    body: SavedDealIn,
    db: AsyncSession = Depends(_get_session),
):
    deal_id = uuid_mod.uuid4()
    await db.execute(
        text(
            """
            INSERT INTO saved_deals (
                id, calculation_id, user_id, session_id, deal_type,
                headline_sell_currency, headline_buy_currency,
                headline_sell_amount, headline_receive_amount,
                tax_percent, note
            ) VALUES (
                :id, :calculation_id, :user_id, :session_id, :deal_type,
                :headline_sell_currency, :headline_buy_currency,
                :headline_sell_amount, :headline_receive_amount,
                :tax_percent, :note
            )
            """
        ),
        {
            "id": str(deal_id),
            "calculation_id": body.calculation_id,
            "user_id": body.user_id,
            "session_id": body.session_id,
            "deal_type": body.deal_type,
            "headline_sell_currency": body.headline_sell_currency,
            "headline_buy_currency": body.headline_buy_currency,
            "headline_sell_amount": str(body.headline_sell_amount) if body.headline_sell_amount else None,
            "headline_receive_amount": str(body.headline_receive_amount) if body.headline_receive_amount else None,
            "tax_percent": str(body.tax_percent),
            "note": body.note,
        },
    )
    # Mark the calculation as saved
    await db.execute(
        text("UPDATE calculations SET is_saved = TRUE WHERE id = :calc_id"),
        {"calc_id": body.calculation_id},
    )
    await db.commit()
    return {"saved_deal_id": str(deal_id)}
