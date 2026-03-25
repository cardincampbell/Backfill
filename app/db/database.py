import aiosqlite
from pathlib import Path
from app.config import settings

DB_PATH = Path(settings.database_url)


async def get_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    try:
        yield db
    finally:
        await db.close()


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys=ON")

        await db.execute("""
            CREATE TABLE IF NOT EXISTS restaurants (
                id                        INTEGER PRIMARY KEY AUTOINCREMENT,
                name                      TEXT NOT NULL,
                address                   TEXT,
                manager_name              TEXT,
                manager_phone             TEXT,
                manager_email             TEXT,
                scheduling_platform       TEXT NOT NULL DEFAULT 'backfill_native',
                scheduling_platform_id    TEXT,
                integration_status       TEXT,
                last_roster_sync_at      TEXT,
                last_roster_sync_status  TEXT,
                last_schedule_sync_at    TEXT,
                last_schedule_sync_status TEXT,
                last_sync_error          TEXT,
                integration_state        TEXT,
                last_event_sync_at       TEXT,
                last_rolling_sync_at     TEXT,
                last_daily_sync_at       TEXT,
                last_writeback_at        TEXT,
                writeback_enabled        INTEGER NOT NULL DEFAULT 0,
                writeback_subscription_tier TEXT NOT NULL DEFAULT 'core',
                onboarding_info           TEXT,
                agency_supply_approved    INTEGER NOT NULL DEFAULT 0,
                preferred_agency_partners TEXT NOT NULL DEFAULT '[]'
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS workers (
                id                    INTEGER PRIMARY KEY AUTOINCREMENT,
                name                  TEXT NOT NULL,
                phone                 TEXT NOT NULL UNIQUE,
                email                 TEXT,
                source_id             TEXT,
                worker_type           TEXT NOT NULL DEFAULT 'internal',
                preferred_channel     TEXT NOT NULL DEFAULT 'sms',
                roles                 TEXT NOT NULL DEFAULT '[]',
                certifications        TEXT NOT NULL DEFAULT '[]',
                priority_rank         INTEGER NOT NULL DEFAULT 1,
                restaurant_id         INTEGER REFERENCES restaurants(id),
                restaurant_assignments TEXT NOT NULL DEFAULT '[]',
                restaurants_worked    TEXT NOT NULL DEFAULT '[]',
                source                TEXT NOT NULL DEFAULT 'csv_import',
                response_rate         REAL,
                acceptance_rate       REAL,
                show_up_rate          REAL,
                rating                REAL,
                total_shifts_filled   INTEGER NOT NULL DEFAULT 0,
                sms_consent_status    TEXT NOT NULL DEFAULT 'pending',
                voice_consent_status  TEXT NOT NULL DEFAULT 'pending',
                consent_text_version  TEXT,
                consent_timestamp     TEXT,
                consent_channel       TEXT,
                opt_out_timestamp     TEXT,
                opt_out_channel       TEXT
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS shifts (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                restaurant_id   INTEGER REFERENCES restaurants(id),
                scheduling_platform_id TEXT,
                role            TEXT NOT NULL,
                date            TEXT NOT NULL,
                start_time      TEXT NOT NULL,
                end_time        TEXT NOT NULL,
                pay_rate        REAL NOT NULL,
                requirements    TEXT NOT NULL DEFAULT '[]',
                status          TEXT NOT NULL DEFAULT 'scheduled',
                called_out_by   INTEGER REFERENCES workers(id),
                filled_by       INTEGER REFERENCES workers(id),
                fill_tier       TEXT,
                source_platform TEXT NOT NULL DEFAULT 'backfill_native'
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS cascades (
                id                    INTEGER PRIMARY KEY AUTOINCREMENT,
                shift_id              INTEGER NOT NULL REFERENCES shifts(id),
                status                TEXT NOT NULL DEFAULT 'active',
                outreach_mode         TEXT NOT NULL DEFAULT 'cascade',
                current_tier          INTEGER NOT NULL DEFAULT 1,
                current_batch         INTEGER NOT NULL DEFAULT 0,
                current_position      INTEGER NOT NULL DEFAULT 0,
                confirmed_worker_id   INTEGER REFERENCES workers(id),
                standby_queue         TEXT NOT NULL DEFAULT '[]',
                manager_approved_tier3 INTEGER NOT NULL DEFAULT 0
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS outreach_attempts (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                cascade_id           INTEGER NOT NULL REFERENCES cascades(id),
                worker_id            INTEGER NOT NULL REFERENCES workers(id),
                tier                 INTEGER NOT NULL,
                channel              TEXT NOT NULL DEFAULT 'sms',
                status               TEXT NOT NULL DEFAULT 'pending',
                outcome              TEXT,
                standby_position     INTEGER,
                promoted_at          TEXT,
                sent_at              TEXT,
                responded_at         TEXT,
                conversation_summary TEXT
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS agency_partners (
                id                         INTEGER PRIMARY KEY AUTOINCREMENT,
                name                       TEXT NOT NULL,
                coverage_areas             TEXT NOT NULL DEFAULT '[]',
                roles_supported            TEXT NOT NULL DEFAULT '[]',
                certifications_supported   TEXT NOT NULL DEFAULT '[]',
                contact_channel            TEXT NOT NULL DEFAULT 'email',
                contact_info               TEXT,
                avg_response_time_minutes  INTEGER,
                acceptance_rate            REAL,
                fill_rate                  REAL,
                billing_model              TEXT NOT NULL DEFAULT 'referral_fee',
                sla_tier                   TEXT NOT NULL DEFAULT 'standard',
                active                     INTEGER NOT NULL DEFAULT 1
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS agency_requests (
                id                    INTEGER PRIMARY KEY AUTOINCREMENT,
                shift_id              INTEGER NOT NULL REFERENCES shifts(id),
                cascade_id            INTEGER NOT NULL REFERENCES cascades(id),
                agency_partner_id     INTEGER NOT NULL REFERENCES agency_partners(id),
                status                TEXT NOT NULL DEFAULT 'sent',
                request_timestamp     TEXT,
                response_deadline     TEXT,
                confirmed_worker_name TEXT,
                confirmed_worker_eta  TEXT,
                agency_reference_id   TEXT,
                notes                 TEXT
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp   TEXT NOT NULL,
                actor       TEXT NOT NULL,
                action      TEXT NOT NULL,
                entity_type TEXT,
                entity_id   INTEGER,
                details     TEXT NOT NULL DEFAULT '{}'
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS integration_events (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                platform        TEXT NOT NULL,
                restaurant_id   INTEGER REFERENCES restaurants(id),
                source_event_id TEXT,
                event_type      TEXT,
                event_scope     TEXT,
                payload         TEXT NOT NULL DEFAULT '{}',
                received_at     TEXT NOT NULL,
                processed_at    TEXT,
                status          TEXT NOT NULL DEFAULT 'received',
                error           TEXT
            )
        """)
        await db.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_integration_events_source
            ON integration_events(platform, source_event_id)
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS sync_jobs (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                platform             TEXT NOT NULL,
                restaurant_id        INTEGER REFERENCES restaurants(id),
                integration_event_id INTEGER REFERENCES integration_events(id),
                job_type             TEXT NOT NULL,
                priority             INTEGER NOT NULL DEFAULT 50,
                scope                TEXT,
                scope_ref            TEXT,
                window_start         TEXT,
                window_end           TEXT,
                status               TEXT NOT NULL DEFAULT 'queued',
                attempt_count        INTEGER NOT NULL DEFAULT 0,
                max_attempts         INTEGER NOT NULL DEFAULT 3,
                next_run_at          TEXT NOT NULL,
                started_at           TEXT,
                completed_at         TEXT,
                last_error           TEXT,
                idempotency_key      TEXT
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_sync_jobs_due
            ON sync_jobs(status, next_run_at, priority, platform, restaurant_id)
        """)
        await db.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_sync_jobs_idempotency
            ON sync_jobs(idempotency_key)
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS sync_runs (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                sync_job_id   INTEGER NOT NULL REFERENCES sync_jobs(id),
                attempt_number INTEGER NOT NULL,
                started_at    TEXT NOT NULL,
                completed_at  TEXT,
                status        TEXT NOT NULL,
                created_count INTEGER NOT NULL DEFAULT 0,
                updated_count INTEGER NOT NULL DEFAULT 0,
                skipped_count INTEGER NOT NULL DEFAULT 0,
                latency_ms    INTEGER,
                error         TEXT
            )
        """)

        await _ensure_column(
            db,
            "restaurants",
            "integration_status",
            "TEXT",
        )
        await _ensure_column(
            db,
            "restaurants",
            "last_roster_sync_at",
            "TEXT",
        )
        await _ensure_column(
            db,
            "restaurants",
            "last_roster_sync_status",
            "TEXT",
        )
        await _ensure_column(
            db,
            "restaurants",
            "last_schedule_sync_at",
            "TEXT",
        )
        await _ensure_column(
            db,
            "restaurants",
            "last_schedule_sync_status",
            "TEXT",
        )
        await _ensure_column(
            db,
            "restaurants",
            "last_sync_error",
            "TEXT",
        )
        await _ensure_column(
            db,
            "restaurants",
            "integration_state",
            "TEXT",
        )
        await _ensure_column(
            db,
            "restaurants",
            "last_event_sync_at",
            "TEXT",
        )
        await _ensure_column(
            db,
            "restaurants",
            "last_rolling_sync_at",
            "TEXT",
        )
        await _ensure_column(
            db,
            "restaurants",
            "last_daily_sync_at",
            "TEXT",
        )
        await _ensure_column(
            db,
            "restaurants",
            "last_writeback_at",
            "TEXT",
        )
        await _ensure_column(
            db,
            "restaurants",
            "writeback_enabled",
            "INTEGER NOT NULL DEFAULT 0",
        )
        await _ensure_column(
            db,
            "restaurants",
            "writeback_subscription_tier",
            "TEXT NOT NULL DEFAULT 'core'",
        )
        await _ensure_column(
            db,
            "workers",
            "source_id",
            "TEXT",
        )
        await _ensure_column(
            db,
            "shifts",
            "scheduling_platform_id",
            "TEXT",
        )
        await _ensure_column(
            db,
            "workers",
            "restaurant_assignments",
            "TEXT NOT NULL DEFAULT '[]'",
        )
        await _ensure_column(
            db,
            "workers",
            "restaurants_worked",
            "TEXT NOT NULL DEFAULT '[]'",
        )
        await _ensure_column(
            db,
            "shifts",
            "reminder_sent_at",
            "TEXT",
        )
        await _ensure_column(
            db,
            "cascades",
            "outreach_mode",
            "TEXT NOT NULL DEFAULT 'cascade'",
        )
        await _ensure_column(
            db,
            "cascades",
            "current_batch",
            "INTEGER NOT NULL DEFAULT 0",
        )
        await _ensure_column(
            db,
            "cascades",
            "confirmed_worker_id",
            "INTEGER REFERENCES workers(id)",
        )
        await _ensure_column(
            db,
            "cascades",
            "standby_queue",
            "TEXT NOT NULL DEFAULT '[]'",
        )
        await _ensure_column(
            db,
            "outreach_attempts",
            "standby_position",
            "INTEGER",
        )
        await _ensure_column(
            db,
            "outreach_attempts",
            "promoted_at",
            "TEXT",
        )

        await db.commit()


async def _ensure_column(
    db: aiosqlite.Connection,
    table_name: str,
    column_name: str,
    column_def: str,
) -> None:
    async with db.execute(f"PRAGMA table_info({table_name})") as cur:
        rows = await cur.fetchall()
    existing = {row[1] for row in rows}
    if column_name not in existing:
        await db.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_def}"
        )
