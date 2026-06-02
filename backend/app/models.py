import uuid
from sqlalchemy import (
    BigInteger,
    Boolean,
    CHAR,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    LargeBinary,
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from .database import Base


class RateSnapshot(Base):
    __tablename__ = "rate_snapshots"

    id = Column(Integer, primary_key=True)
    ils_to_usdt = Column(Float, nullable=False)
    usd_to_usdt = Column(Float, nullable=False)
    euro_to_usdt = Column(Float, nullable=False)
    fetched_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('anonymous','oauth','deleted')",
            name="users_kind_check",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kind = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    consent_pii = Column(Boolean, nullable=False, server_default="false")
    retention_bucket = Column(Text, nullable=False, server_default="standard")
    deleted_at = Column(DateTime(timezone=True), nullable=True)


class UserUuid(Base):
    __tablename__ = "user_uuids"

    uuid = Column(UUID(as_uuid=True), primary_key=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    first_seen_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_seen_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class OAuthIdentity(Base):
    __tablename__ = "oauth_identities"
    __table_args__ = (
        UniqueConstraint("provider", "provider_subject", name="uq_oauth_provider_subject"),
        CheckConstraint(
            "provider IN ('google','apple')",
            name="oauth_identities_provider_check",
        ),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    provider = Column(Text, nullable=False)
    provider_subject = Column(Text, nullable=False)
    email = Column(Text, nullable=True)
    linked_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class TelegramIdentity(Base):
    __tablename__ = "telegram_identities"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    telegram_chat_id = Column(BigInteger, nullable=False, unique=True)
    telegram_username = Column(Text, nullable=True)
    telegram_first_name = Column(Text, nullable=True)
    telegram_last_name = Column(Text, nullable=True)
    telegram_language_code = Column(Text, nullable=True)
    connected_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_interaction_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, nullable=False, server_default="true")
    consecutive_errors = Column(Integer, nullable=False, server_default="0")


class Session(Base):
    __tablename__ = "sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    user_uuid = Column(UUID(as_uuid=True), ForeignKey("user_uuids.uuid", ondelete="RESTRICT"), nullable=False)
    ga_client_id = Column(Text, nullable=False)
    ga_session_id = Column(Text, nullable=False)
    environment = Column(Text, nullable=False)
    locale = Column(Text, nullable=True)
    user_agent = Column(Text, nullable=True)
    referrer = Column(Text, nullable=True)
    utm_source = Column(Text, nullable=True)
    utm_medium = Column(Text, nullable=True)
    utm_campaign = Column(Text, nullable=True)
    ip_hash = Column(LargeBinary, nullable=True)
    first_seen_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_seen_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    retention_bucket = Column(Text, nullable=False, server_default="standard")
    # Device context
    device_type = Column(Text, nullable=True)
    os_family = Column(Text, nullable=True)
    browser_family = Column(Text, nullable=True)
    screen_width = Column(SmallInteger, nullable=True)
    screen_height = Column(SmallInteger, nullable=True)
    viewport_width = Column(SmallInteger, nullable=True)
    viewport_height = Column(SmallInteger, nullable=True)
    device_pixel_ratio = Column(Numeric(4, 2), nullable=True)
    cpu_cores = Column(SmallInteger, nullable=True)
    device_memory_gb = Column(Numeric(4, 1), nullable=True)
    # Geo
    country_code = Column(CHAR(2), nullable=True)
    city = Column(Text, nullable=True)
    isp = Column(Text, nullable=True)
    connection_type = Column(Text, nullable=True)
    # Experiments
    experiment_flags = Column(JSONB, nullable=True)


class Calculation(Base):
    # Partitioned table — __tablename__ maps to the parent partition
    __tablename__ = "calculations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="RESTRICT"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    rate_snapshot_id = Column(Integer, ForeignKey("rate_snapshots.id"), nullable=False)
    fee_mode = Column(Text, nullable=False)
    total_gross_usdt = Column(Numeric(20, 8), nullable=False)
    total_fee_usdt = Column(Numeric(20, 8), nullable=False)
    total_net_usdt = Column(Numeric(20, 8), nullable=False)
    ils_equivalent = Column(Numeric(20, 2), nullable=False)
    above_min_threshold = Column(Boolean, nullable=False)
    currencies = Column(ARRAY(Text), nullable=False)
    is_saved = Column(Boolean, nullable=False, server_default="false")
    ga_client_id = Column(Text, nullable=False)
    ga_session_id = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    retention_bucket = Column(Text, nullable=False, server_default="standard")
    client_calculated_at = Column(DateTime(timezone=True), nullable=True)
    client_request_id = Column(UUID(as_uuid=True), nullable=True)
    tab_id = Column(Text, nullable=True)
    experiment_flags = Column(JSONB, nullable=True)


class CalculationLine(Base):
    __tablename__ = "calculation_lines"
    __table_args__ = (
        ForeignKeyConstraint(
            ["calculation_id", "calculation_created_at"],
            ["calculations.id", "calculations.created_at"],
            ondelete="CASCADE",
        ),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    calculation_id = Column(UUID(as_uuid=True), nullable=False)
    calculation_created_at = Column(DateTime(timezone=True), nullable=False)
    line_index = Column(SmallInteger, nullable=False)
    amount = Column(Numeric(20, 8), nullable=False)
    currency = Column(Text, nullable=False)
    fee_percent = Column(Numeric(6, 3), nullable=False)
    gross_usdt = Column(Numeric(20, 8), nullable=False)
    fee_usdt = Column(Numeric(20, 8), nullable=False)
    net_usdt = Column(Numeric(20, 8), nullable=False)


class SavedDeal(Base):
    __tablename__ = "saved_deals"
    __table_args__ = (
        ForeignKeyConstraint(
            ["calculation_id", "calculation_created_at"],
            ["calculations.id", "calculations.created_at"],
            ondelete="RESTRICT",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    calculation_id = Column(UUID(as_uuid=True), nullable=False)
    calculation_created_at = Column(DateTime(timezone=True), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="RESTRICT"), nullable=False)
    deal_type = Column(Text, nullable=False, server_default="exchange")
    headline_sell_currency = Column(Text, nullable=True)
    headline_buy_currency = Column(Text, nullable=True)
    headline_sell_amount = Column(Numeric(20, 8), nullable=True)
    headline_receive_amount = Column(Numeric(20, 8), nullable=True)
    tax_percent = Column(Numeric(8, 4), nullable=False, server_default="0")
    saved_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    shared_at = Column(DateTime(timezone=True), nullable=True)
    note = Column(Text, nullable=True)


class TelegramDealSend(Base):
    __tablename__ = "telegram_deal_sends"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    saved_deal_id = Column(UUID(as_uuid=True), ForeignKey("saved_deals.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    telegram_chat_id = Column(BigInteger, nullable=False)
    telegram_username = Column(Text, nullable=True)
    message_text = Column(Text, nullable=False)
    sent_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    status = Column(Text, nullable=False)
    error_text = Column(Text, nullable=True)


class UserEvent(Base):
    # Partitioned table
    __tablename__ = "user_events"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="RESTRICT"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    event_name = Column(Text, nullable=False)
    event_params = Column(JSONB, nullable=False, server_default="{}")
    occurred_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    tab_id = Column(Text, nullable=True)


class UserMerge(Base):
    __tablename__ = "user_merges"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    from_user_id = Column(UUID(as_uuid=True), nullable=False)
    to_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    merge_reason = Column(Text, nullable=False, server_default="oauth_link")
    merged_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class AppSetting(Base):
    __tablename__ = "app_settings"

    key = Column(Text, primary_key=True)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
