"""POST /calculations — idempotent calculation ingest."""

from __future__ import annotations
import logging
import uuid as uuid_mod
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session_factory
import os

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/calculations", tags=["calculations"])

_GA_HEADERS_REQUIRED = os.environ.get("GA_HEADERS_REQUIRED", "true").lower() == "true"


class CalculationLineIn(BaseModel):
    line_index: int
    amount: Decimal
    currency: str
    fee_percent: Decimal
    gross_usdt: Decimal
    fee_usdt: Decimal
    net_usdt: Decimal


class CalculationIn(BaseModel):
    session_id: str
    user_id: str
    rate_snapshot_id: int
    fee_mode: str
    total_gross_usdt: Decimal
    total_fee_usdt: Decimal
    total_net_usdt: Decimal
    ils_equivalent: Decimal
    above_min_threshold: bool
    currencies: list[str]
    is_saved: bool = False
    client_calculated_at: datetime | None = None
    client_request_id: str | None = None
    tab_id: str | None = None
    experiment_flags: dict | None = None
    lines: list[CalculationLineIn]


async def _get_session() -> AsyncSession:
    factory = get_session_factory()
    async with factory() as session:
        yield session


@router.post("", status_code=201)
async def create_calculation(
    body: CalculationIn,
    request: Request,
    x_ga_client_id: str | None = Header(None, alias="X-GA-Client-Id"),
    x_ga_session_id: str | None = Header(None, alias="X-GA-Session-Id"),
    db: AsyncSession = Depends(_get_session),
):
    if _GA_HEADERS_REQUIRED:
        if not x_ga_client_id or not x_ga_session_id:
            raise HTTPException(400, "X-GA-Client-Id and X-GA-Session-Id are required")

    # Idempotency: check client_request_id
    if body.client_request_id:
        existing = await db.execute(
            text("SELECT id FROM calculations WHERE client_request_id = :crid"),
            {"crid": body.client_request_id},
        )
        row = existing.fetchone()
        if row:
            logger.info("Duplicate calculation ignored client_request_id=%s", body.client_request_id)
            return {"calculation_id": str(row.id), "created": False}

    calc_id = uuid_mod.uuid4()
    insert_result = await db.execute(
        text(
            """
            INSERT INTO calculations (
                id, session_id, user_id, rate_snapshot_id, fee_mode,
                total_gross_usdt, total_fee_usdt, total_net_usdt,
                ils_equivalent, above_min_threshold, currencies,
                is_saved, ga_client_id, ga_session_id,
                client_calculated_at, client_request_id, tab_id, experiment_flags
            ) VALUES (
                :id, :session_id, :user_id, :rate_snapshot_id, :fee_mode,
                :total_gross_usdt, :total_fee_usdt, :total_net_usdt,
                :ils_equivalent, :above_min_threshold, :currencies,
                :is_saved, :ga_client_id, :ga_session_id,
                :client_calculated_at, :client_request_id, :tab_id, :experiment_flags
            )
            RETURNING created_at
            """
        ),
        {
            "id": str(calc_id),
            "session_id": body.session_id,
            "user_id": body.user_id,
            "rate_snapshot_id": body.rate_snapshot_id,
            "fee_mode": body.fee_mode,
            "total_gross_usdt": str(body.total_gross_usdt),
            "total_fee_usdt": str(body.total_fee_usdt),
            "total_net_usdt": str(body.total_net_usdt),
            "ils_equivalent": str(body.ils_equivalent),
            "above_min_threshold": body.above_min_threshold,
            "currencies": body.currencies,
            "is_saved": body.is_saved,
            "ga_client_id": x_ga_client_id or "",
            "ga_session_id": x_ga_session_id or "",
            "client_calculated_at": body.client_calculated_at,
            "client_request_id": body.client_request_id,
            "tab_id": body.tab_id,
            "experiment_flags": body.experiment_flags,
        },
    )

    calc_created_at = insert_result.scalar_one()

    for line in body.lines:
        await db.execute(
            text(
                """
                INSERT INTO calculation_lines
                    (calculation_id, calculation_created_at, line_index,
                     amount, currency, fee_percent, gross_usdt, fee_usdt, net_usdt)
                VALUES
                    (:calc_id, :calc_created_at, :line_index,
                     :amount, :currency, :fee_percent, :gross_usdt, :fee_usdt, :net_usdt)
                """
            ),
            {
                "calc_id": str(calc_id),
                "calc_created_at": calc_created_at,
                "line_index": line.line_index,
                "amount": str(line.amount),
                "currency": line.currency,
                "fee_percent": str(line.fee_percent),
                "gross_usdt": str(line.gross_usdt),
                "fee_usdt": str(line.fee_usdt),
                "net_usdt": str(line.net_usdt),
            },
        )

    await db.commit()
    return {"calculation_id": str(calc_id), "created": True}
