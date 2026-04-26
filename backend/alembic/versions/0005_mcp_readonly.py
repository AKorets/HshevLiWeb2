"""mcp_readonly schema — views, role, and grants for AI/MCP access

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-24

Phase 4 (MCP-first milestone):
- Creates mcp_readonly schema with 10 views (7 original + 3 gap-analysis additions)
- Creates mcp_reader role with SELECT-only on mcp_readonly
- Adds COMMENT ON TABLE/COLUMN strings as LLM-readable docstrings
- vw_user_summary and vw_daily_activity are materialized (refreshed hourly)
- vw_device_breakdown is materialized (refreshed hourly)
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Schema ---
    op.execute("CREATE SCHEMA IF NOT EXISTS mcp_readonly")
    op.execute("COMMENT ON SCHEMA mcp_readonly IS 'Read-only views for AI/MCP access. No base tables, no PII.'")

    # --- Role ---
    op.execute(
        "DO $$ BEGIN "
        "  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mcp_reader') THEN "
        "    CREATE ROLE mcp_reader NOLOGIN; "
        "  END IF; "
        "END $$"
    )
    op.execute("GRANT USAGE ON SCHEMA mcp_readonly TO mcp_reader")
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA mcp_readonly GRANT SELECT ON TABLES TO mcp_reader")

    # ---------------------------------------------------------------------------
    # Regular views (always fresh)
    # ---------------------------------------------------------------------------

    op.execute("""
        CREATE OR REPLACE VIEW mcp_readonly.vw_users AS
        SELECT
            u.id,
            u.kind,
            u.created_at,
            u.retention_bucket,
            u.deleted_at IS NOT NULL                        AS is_deleted,
            EXISTS (
                SELECT 1 FROM oauth_identities oi WHERE oi.user_id = u.id
            )                                               AS has_oauth,
            EXISTS (
                SELECT 1 FROM telegram_identities ti WHERE ti.user_id = u.id AND ti.is_active
            )                                               AS has_telegram,
            (SELECT COUNT(*) FROM user_uuids uu WHERE uu.user_id = u.id) AS device_count
        FROM users u
        WHERE u.deleted_at IS NULL
    """)
    op.execute(
        "COMMENT ON VIEW mcp_readonly.vw_users IS "
        "'Users without PII. email is never exposed here. "
        "Use get_user_summary() for aggregates.'"
    )

    op.execute("""
        CREATE OR REPLACE VIEW mcp_readonly.vw_sessions AS
        SELECT
            s.id,
            s.user_id,
            s.ga_client_id,
            s.ga_session_id,
            s.environment,
            s.locale,
            s.referrer,
            s.utm_source,
            s.utm_medium,
            s.utm_campaign,
            s.first_seen_at,
            s.last_seen_at,
            s.retention_bucket,
            s.device_type,
            s.os_family,
            s.browser_family,
            CASE
                WHEN s.screen_width IS NULL THEN NULL
                WHEN s.screen_width < 1280  THEN '<1280'
                WHEN s.screen_width <= 1920 THEN '1280-1920'
                ELSE '>1920'
            END                                             AS screen_class,
            s.country_code,
            s.connection_type,
            s.experiment_flags,
            EXTRACT(EPOCH FROM (s.last_seen_at - s.first_seen_at))::INT AS duration_seconds
        FROM sessions s
    """)
    op.execute(
        "COMMENT ON VIEW mcp_readonly.vw_sessions IS "
        "'Sessions without ip_hash, raw user_agent, and raw screen dimensions. "
        "screen_class buckets screen width into three tiers.'"
    )

    op.execute("""
        CREATE OR REPLACE VIEW mcp_readonly.vw_calculations AS
        SELECT
            c.id,
            c.session_id,
            c.user_id,
            c.rate_snapshot_id,
            c.fee_mode,
            c.total_gross_usdt,
            c.total_fee_usdt,
            c.total_net_usdt,
            c.ils_equivalent,
            c.above_min_threshold,
            c.currencies,
            c.is_saved,
            c.ga_client_id,
            c.ga_session_id,
            c.created_at,
            c.retention_bucket,
            c.client_calculated_at,
            c.client_calculated_at IS NOT NULL
                AND c.created_at - c.client_calculated_at > INTERVAL '5 minutes'
                                                            AS is_offline_sync,
            c.tab_id,
            c.experiment_flags,
            (
                SELECT jsonb_agg(
                    jsonb_build_object(
                        'line_index',  cl.line_index,
                        'currency',    cl.currency,
                        'amount',      cl.amount,
                        'fee_percent', cl.fee_percent,
                        'gross_usdt',  cl.gross_usdt,
                        'fee_usdt',    cl.fee_usdt,
                        'net_usdt',    cl.net_usdt
                    ) ORDER BY cl.line_index
                )
                FROM calculation_lines cl
                WHERE cl.calculation_id = c.id
            )                                               AS lines
        FROM calculations c
    """)
    op.execute(
        "COMMENT ON VIEW mcp_readonly.vw_calculations IS "
        "'Calculations with line items rolled up into a JSONB lines column. "
        "is_offline_sync is TRUE when client_calculated_at predates created_at by >5 minutes.'"
    )

    op.execute("""
        CREATE OR REPLACE VIEW mcp_readonly.vw_saved_deals AS
        SELECT
            sd.id,
            sd.calculation_id,
            sd.user_id,
            sd.session_id,
            sd.deal_type,
            sd.headline_sell_currency,
            sd.headline_buy_currency,
            sd.headline_sell_amount,
            sd.headline_receive_amount,
            sd.tax_percent,
            sd.saved_at,
            sd.shared_at,
            sd.note IS NOT NULL                             AS has_note
        FROM saved_deals sd
    """)
    op.execute(
        "COMMENT ON VIEW mcp_readonly.vw_saved_deals IS "
        "'Saved deals with headline fields. note is hidden; has_note flag is exposed.'"
    )

    op.execute("""
        CREATE OR REPLACE VIEW mcp_readonly.vw_session_journey AS
        SELECT
            s.id                                            AS session_id,
            s.user_id,
            s.environment,
            s.first_seen_at,
            s.last_seen_at,
            s.ga_client_id,
            s.ga_session_id,
            jsonb_agg(
                jsonb_build_object(
                    'event_name',   ue.event_name,
                    'occurred_at',  ue.occurred_at,
                    'tab_id',       ue.tab_id,
                    'params',       ue.event_params
                ) ORDER BY ue.occurred_at
            )                                               AS events
        FROM sessions s
        LEFT JOIN user_events ue ON ue.session_id = s.id
        GROUP BY s.id, s.user_id, s.environment, s.first_seen_at, s.last_seen_at,
                 s.ga_client_id, s.ga_session_id
    """)
    op.execute(
        "COMMENT ON VIEW mcp_readonly.vw_session_journey IS "
        "'One row per session with an ordered events JSONB array. "
        "Use get_session_journey(session_id) to reconstruct a full user journey.'"
    )

    op.execute("""
        CREATE OR REPLACE VIEW mcp_readonly.vw_error_events AS
        SELECT
            ue.occurred_at::DATE                            AS event_date,
            s.environment,
            ue.event_name,
            ue.event_params->>'error_code'                  AS error_code,
            ue.event_params->>'endpoint'                    AS endpoint,
            COUNT(*)                                        AS event_count,
            COUNT(DISTINCT ue.session_id)                   AS affected_sessions
        FROM user_events ue
        JOIN sessions s ON s.id = ue.session_id
        WHERE ue.event_name IN ('calculation_error', 'api_error', 'ui_crash')
        GROUP BY 1, 2, 3, 4, 5
    """)
    op.execute(
        "COMMENT ON VIEW mcp_readonly.vw_error_events IS "
        "'Aggregated error events by date and environment. "
        "Use list_error_events() to drill into specific sessions.'"
    )

    # ---------------------------------------------------------------------------
    # Materialized views (refreshed hourly by scripts/refresh_mcp_views.py)
    # ---------------------------------------------------------------------------

    op.execute("""
        CREATE MATERIALIZED VIEW mcp_readonly.vw_user_summary AS
        SELECT
            u.id                                            AS user_id,
            u.kind,
            u.created_at,
            COUNT(DISTINCT c.id)                            AS calc_count,
            COUNT(DISTINCT sd.id)                           AS save_count,
            MIN(s.first_seen_at)                            AS first_seen_at,
            MAX(s.last_seen_at)                             AS last_seen_at,
            ARRAY(
                SELECT DISTINCT unnest(c2.currencies)
                FROM calculations c2
                WHERE c2.user_id = u.id
            )                                               AS currencies_seen,
            MAX(c.ils_equivalent)                           AS max_ils_equivalent,
            AVG(c.ils_equivalent)                           AS avg_ils_equivalent,
            array_remove(ARRAY[
                CASE WHEN u.kind = 'anonymous' THEN 'anonymous' END,
                CASE WHEN EXISTS (SELECT 1 FROM oauth_identities oi WHERE oi.user_id = u.id)
                     THEN 'oauth' END,
                CASE WHEN EXISTS (SELECT 1 FROM telegram_identities ti WHERE ti.user_id = u.id AND ti.is_active)
                     THEN 'telegram' END
            ], NULL)                                        AS identity_kinds
        FROM users u
        LEFT JOIN sessions s ON s.user_id = u.id
        LEFT JOIN calculations c ON c.user_id = u.id
        LEFT JOIN saved_deals sd ON sd.user_id = u.id
        WHERE u.deleted_at IS NULL
        GROUP BY u.id, u.kind, u.created_at
        WITH DATA
    """)
    op.execute(
        "CREATE UNIQUE INDEX ON mcp_readonly.vw_user_summary (user_id)"
    )
    op.execute(
        "COMMENT ON MATERIALIZED VIEW mcp_readonly.vw_user_summary IS "
        "'Per-user aggregates. Refreshed hourly. "
        "identity_kinds lists active identity types, e.g. {anonymous,telegram}.'"
    )

    op.execute("""
        CREATE MATERIALIZED VIEW mcp_readonly.vw_daily_activity AS
        SELECT
            s.first_seen_at::DATE                           AS activity_date,
            s.environment,
            COUNT(DISTINCT s.user_id)                       AS unique_users,
            COUNT(DISTINCT c.id)                            AS calc_count,
            COUNT(DISTINCT sd.id)                           AS save_count,
            COALESCE(SUM(c.ils_equivalent), 0)              AS sum_ils_equivalent
        FROM sessions s
        LEFT JOIN calculations c ON c.session_id = s.id
        LEFT JOIN saved_deals sd ON sd.session_id = s.id
        GROUP BY 1, 2
        WITH DATA
    """)
    op.execute(
        "CREATE UNIQUE INDEX ON mcp_readonly.vw_daily_activity (activity_date, environment)"
    )
    op.execute(
        "COMMENT ON MATERIALIZED VIEW mcp_readonly.vw_daily_activity IS "
        "'Daily activity dashboard. Refreshed hourly. "
        "Use daily_activity(since, until, environment) MCP tool.'"
    )

    op.execute("""
        CREATE MATERIALIZED VIEW mcp_readonly.vw_device_breakdown AS
        SELECT
            s.first_seen_at::DATE                           AS activity_date,
            s.environment,
            s.device_type,
            s.os_family,
            s.browser_family,
            s.country_code,
            s.connection_type,
            COUNT(DISTINCT s.user_id)                       AS unique_users,
            COUNT(*)                                        AS session_count
        FROM sessions s
        WHERE s.device_type IS NOT NULL
        GROUP BY 1, 2, 3, 4, 5, 6, 7
        WITH DATA
    """)
    op.execute(
        "COMMENT ON MATERIALIZED VIEW mcp_readonly.vw_device_breakdown IS "
        "'Device/geo breakdown by date. Refreshed hourly. "
        "Use device_breakdown(since, until) MCP tool.'"
    )

    op.execute("""
        CREATE OR REPLACE VIEW mcp_readonly.vw_experiment_stats AS
        SELECT
            s.environment,
            f.key                                           AS experiment_key,
            f.value                                         AS experiment_variant,
            COUNT(DISTINCT c.user_id)                       AS unique_users,
            COUNT(*)                                        AS calc_count,
            SUM(CASE WHEN c.is_saved THEN 1 ELSE 0 END) * 100.0
                / NULLIF(COUNT(*), 0)                       AS save_rate_pct,
            AVG(c.ils_equivalent)                           AS avg_ils_equivalent,
            MAX(c.ils_equivalent)                           AS max_ils_equivalent
        FROM calculations c
        JOIN sessions s ON s.id = c.session_id
        CROSS JOIN LATERAL jsonb_each_text(c.experiment_flags) AS f(key, value)
        WHERE c.experiment_flags IS NOT NULL
        GROUP BY 1, 2, 3
    """)
    op.execute(
        "COMMENT ON VIEW mcp_readonly.vw_experiment_stats IS "
        "'A/B experiment results: save_rate_pct and ils_equivalent by variant. "
        "Use experiment_stats(experiment_name) MCP tool.'"
    )

    # Grant SELECT on all views
    op.execute("GRANT SELECT ON ALL TABLES IN SCHEMA mcp_readonly TO mcp_reader")


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS mcp_readonly.vw_experiment_stats")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mcp_readonly.vw_device_breakdown")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mcp_readonly.vw_daily_activity")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mcp_readonly.vw_user_summary")
    op.execute("DROP VIEW IF EXISTS mcp_readonly.vw_error_events")
    op.execute("DROP VIEW IF EXISTS mcp_readonly.vw_session_journey")
    op.execute("DROP VIEW IF EXISTS mcp_readonly.vw_saved_deals")
    op.execute("DROP VIEW IF EXISTS mcp_readonly.vw_calculations")
    op.execute("DROP VIEW IF EXISTS mcp_readonly.vw_sessions")
    op.execute("DROP VIEW IF EXISTS mcp_readonly.vw_users")
    op.execute("REVOKE ALL ON SCHEMA mcp_readonly FROM mcp_reader")
    op.execute("DROP SCHEMA IF EXISTS mcp_readonly CASCADE")
    op.execute(
        "DO $$ BEGIN "
        "  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mcp_reader') THEN "
        "    DROP ROLE mcp_reader; "
        "  END IF; "
        "END $$"
    )
