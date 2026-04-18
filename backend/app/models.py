from sqlalchemy import Column, Float, Integer, DateTime, func
from .database import Base


class RateSnapshot(Base):
    __tablename__ = "rate_snapshots"

    id = Column(Integer, primary_key=True)
    ils_to_usdt = Column(Float, nullable=False)
    usd_to_usdt = Column(Float, nullable=False)
    euro_to_usdt = Column(Float, nullable=False)
    fetched_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
