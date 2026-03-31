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
        await db.execute("PRAGMA foreign_keys=OFF")
        await _migrate_location_schema(db)
        await db.execute("PRAGMA foreign_keys=ON")

        await db.execute("""
            CREATE TABLE IF NOT EXISTS organizations (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                name          TEXT NOT NULL UNIQUE,
                vertical      TEXT,
                contact_name  TEXT,
                contact_phone TEXT,
                contact_email TEXT,
                location_count_estimate INTEGER
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS locations (
                id                        INTEGER PRIMARY KEY AUTOINCREMENT,
                name                      TEXT NOT NULL,
                organization_id           INTEGER REFERENCES organizations(id),
                vertical                  TEXT NOT NULL DEFAULT 'restaurant',
                address                   TEXT,
                place_provider            TEXT,
                place_id                  TEXT,
                place_resource_name       TEXT,
                place_display_name        TEXT,
                place_brand_name          TEXT,
                place_location_label      TEXT,
                place_formatted_address   TEXT,
                place_primary_type        TEXT,
                place_primary_type_display_name TEXT,
                place_business_status     TEXT,
                place_latitude            REAL,
                place_longitude           REAL,
                place_google_maps_uri     TEXT,
                place_website_uri         TEXT,
                place_national_phone_number TEXT,
                place_international_phone_number TEXT,
                place_utc_offset_minutes  INTEGER,
                place_rating              REAL,
                place_user_rating_count   INTEGER,
                place_city                TEXT,
                place_state_region        TEXT,
                place_postal_code         TEXT,
                place_country_code        TEXT,
                place_neighborhood        TEXT,
                place_sublocality         TEXT,
                place_types               TEXT NOT NULL DEFAULT '[]',
                place_address_components  TEXT NOT NULL DEFAULT '[]',
                place_regular_opening_hours TEXT NOT NULL DEFAULT '{}',
                place_plus_code           TEXT NOT NULL DEFAULT '{}',
                place_metadata            TEXT NOT NULL DEFAULT '{}',
                employee_count            INTEGER,
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
                last_manager_digest_sent_at TEXT,
                writeback_enabled        INTEGER NOT NULL DEFAULT 0,
                writeback_subscription_tier TEXT NOT NULL DEFAULT 'core',
                backfill_shifts_enabled INTEGER NOT NULL DEFAULT 1,
                backfill_shifts_launch_state TEXT NOT NULL DEFAULT 'enabled',
                backfill_shifts_beta_eligible INTEGER NOT NULL DEFAULT 0,
                coverage_requires_manager_approval INTEGER NOT NULL DEFAULT 0,
                late_arrival_policy     TEXT NOT NULL DEFAULT 'wait',
                missed_check_in_policy  TEXT NOT NULL DEFAULT 'start_coverage',
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
                location_id           INTEGER REFERENCES locations(id),
                location_assignments  TEXT NOT NULL DEFAULT '[]',
                locations_worked      TEXT NOT NULL DEFAULT '[]',
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
                location_id     INTEGER REFERENCES locations(id),
                scheduling_platform_id TEXT,
                role            TEXT NOT NULL,
                date            TEXT NOT NULL,
                start_time      TEXT NOT NULL,
                end_time        TEXT NOT NULL,
                spans_midnight  INTEGER NOT NULL DEFAULT 0,
                pay_rate        REAL NOT NULL,
                requirements    TEXT NOT NULL DEFAULT '[]',
                status          TEXT NOT NULL DEFAULT 'scheduled',
                called_out_by   INTEGER REFERENCES workers(id),
                filled_by       INTEGER REFERENCES workers(id),
                fill_tier       TEXT,
                escalated_from_worker_id INTEGER REFERENCES workers(id),
                reminder_sent_at TEXT,
                confirmation_requested_at TEXT,
                worker_confirmed_at TEXT,
                worker_declined_at TEXT,
                confirmation_escalated_at TEXT,
                check_in_requested_at TEXT,
                checked_in_at TEXT,
                late_reported_at TEXT,
                late_eta_minutes INTEGER,
                check_in_escalated_at TEXT,
                attendance_action_state TEXT,
                attendance_action_updated_at TEXT,
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
                pending_claim_worker_id INTEGER REFERENCES workers(id),
                pending_claim_at      TEXT,
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
            CREATE TABLE IF NOT EXISTS retell_conversations (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                external_id          TEXT NOT NULL UNIQUE,
                conversation_type    TEXT NOT NULL,
                event_type           TEXT,
                direction            TEXT,
                status               TEXT,
                agent_id             TEXT,
                location_id          INTEGER REFERENCES locations(id),
                shift_id             INTEGER REFERENCES shifts(id),
                cascade_id           INTEGER REFERENCES cascades(id),
                worker_id            INTEGER REFERENCES workers(id),
                phone_from           TEXT,
                phone_to             TEXT,
                disconnection_reason TEXT,
                conversation_summary TEXT,
                transcript_text      TEXT,
                transcript_items     TEXT NOT NULL DEFAULT '[]',
                analysis             TEXT NOT NULL DEFAULT '{}',
                metadata             TEXT NOT NULL DEFAULT '{}',
                raw_payload          TEXT NOT NULL DEFAULT '{}',
                started_at           TEXT,
                ended_at             TEXT,
                created_at           TEXT NOT NULL,
                updated_at           TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_retell_conversations_shift
            ON retell_conversations(shift_id, id DESC)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_retell_conversations_cascade
            ON retell_conversations(cascade_id, id DESC)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_retell_conversations_worker
            ON retell_conversations(worker_id, id DESC)
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS app_state (
                key        TEXT PRIMARY KEY,
                value      TEXT,
                updated_at TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS onboarding_sessions (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                token_hash           TEXT NOT NULL UNIQUE,
                source_conversation_id INTEGER REFERENCES retell_conversations(id),
                source_external_id   TEXT UNIQUE,
                organization_id      INTEGER REFERENCES organizations(id),
                location_id          INTEGER REFERENCES locations(id),
                status               TEXT NOT NULL DEFAULT 'pending',
                call_type            TEXT,
                contact_name         TEXT,
                contact_phone        TEXT,
                contact_email        TEXT,
                role_name            TEXT,
                business_name        TEXT,
                location_name        TEXT,
                vertical             TEXT,
                location_count       INTEGER,
                lead_source          TEXT,
                employee_count       INTEGER,
                address              TEXT,
                pain_point_summary   TEXT,
                urgency              TEXT,
                notes                TEXT,
                setup_kind           TEXT,
                scheduling_platform  TEXT,
                extracted_fields     TEXT NOT NULL DEFAULT '{}',
                sent_message_sid     TEXT,
                sent_at              TEXT,
                completed_at         TEXT,
                created_at           TEXT NOT NULL,
                updated_at           TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_onboarding_sessions_org
            ON onboarding_sessions(organization_id, id DESC)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_onboarding_sessions_location
            ON onboarding_sessions(location_id, id DESC)
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
            CREATE TABLE IF NOT EXISTS webhook_receipts (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                source               TEXT NOT NULL,
                external_id          TEXT NOT NULL,
                status               TEXT NOT NULL DEFAULT 'processing',
                duplicate_count      INTEGER NOT NULL DEFAULT 0,
                request_payload      TEXT NOT NULL DEFAULT '{}',
                response_body        TEXT,
                response_status_code INTEGER,
                last_seen_at         TEXT,
                created_at           TEXT NOT NULL,
                updated_at           TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_webhook_receipts_source_external
            ON webhook_receipts(source, external_id)
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS dashboard_access_requests (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                phone             TEXT NOT NULL,
                organization_id   INTEGER REFERENCES organizations(id),
                location_ids_json TEXT NOT NULL DEFAULT '[]',
                token_hash        TEXT NOT NULL UNIQUE,
                status            TEXT NOT NULL DEFAULT 'pending',
                expires_at        TEXT NOT NULL,
                used_at           TEXT,
                requested_at      TEXT NOT NULL,
                created_at        TEXT NOT NULL,
                updated_at        TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_dashboard_access_requests_phone
            ON dashboard_access_requests(phone, status, id DESC)
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS dashboard_sessions (
                id                     INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id        INTEGER REFERENCES organizations(id),
                location_ids_json      TEXT NOT NULL DEFAULT '[]',
                subject_phone          TEXT NOT NULL,
                session_token_hash     TEXT NOT NULL UNIQUE,
                access_request_id      INTEGER REFERENCES dashboard_access_requests(id),
                status                 TEXT NOT NULL DEFAULT 'active',
                expires_at             TEXT NOT NULL,
                last_seen_at           TEXT,
                created_at             TEXT NOT NULL,
                updated_at             TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_dashboard_sessions_org
            ON dashboard_sessions(organization_id, status, id DESC)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_dashboard_sessions_phone
            ON dashboard_sessions(subject_phone, status, id DESC)
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS setup_access_tokens (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                location_id     INTEGER NOT NULL REFERENCES locations(id),
                token_hash      TEXT NOT NULL UNIQUE,
                status          TEXT NOT NULL DEFAULT 'active',
                source          TEXT,
                expires_at      TEXT NOT NULL,
                last_seen_at    TEXT,
                created_at      TEXT NOT NULL,
                updated_at      TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_setup_access_tokens_location
            ON setup_access_tokens(location_id, status, id DESC)
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS integration_events (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                platform        TEXT NOT NULL,
                location_id     INTEGER REFERENCES locations(id),
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
                location_id          INTEGER REFERENCES locations(id),
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
            ON sync_jobs(status, next_run_at, priority, platform, location_id)
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
        await db.execute("""
            CREATE TABLE IF NOT EXISTS ops_jobs (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                job_type        TEXT NOT NULL,
                location_id     INTEGER REFERENCES locations(id),
                priority        INTEGER NOT NULL DEFAULT 50,
                payload_json    TEXT NOT NULL DEFAULT '{}',
                status          TEXT NOT NULL DEFAULT 'queued',
                attempt_count   INTEGER NOT NULL DEFAULT 0,
                max_attempts    INTEGER NOT NULL DEFAULT 3,
                next_run_at     TEXT NOT NULL,
                started_at      TEXT,
                completed_at    TEXT,
                last_error      TEXT,
                idempotency_key TEXT,
                created_at      TEXT NOT NULL,
                updated_at      TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_ops_jobs_due
            ON ops_jobs(status, next_run_at, priority, location_id)
        """)
        await db.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_ops_jobs_idempotency
            ON ops_jobs(idempotency_key)
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS ai_action_requests (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                channel             TEXT NOT NULL,
                actor_type          TEXT NOT NULL,
                actor_id            INTEGER,
                organization_id     INTEGER REFERENCES organizations(id),
                location_id         INTEGER NOT NULL REFERENCES locations(id),
                original_text       TEXT NOT NULL,
                intent_type         TEXT,
                status              TEXT NOT NULL DEFAULT 'received',
                risk_class          TEXT,
                requires_confirmation INTEGER NOT NULL DEFAULT 0,
                redirect_reason     TEXT,
                action_plan_json    TEXT NOT NULL DEFAULT '{}',
                result_summary_json TEXT NOT NULL DEFAULT '{}',
                error_code          TEXT,
                error_message       TEXT,
                created_at          TEXT NOT NULL,
                updated_at          TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_ai_action_requests_location
            ON ai_action_requests(location_id, status, created_at DESC, id DESC)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_ai_action_requests_actor
            ON ai_action_requests(actor_type, actor_id, created_at DESC, id DESC)
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS ai_action_entities (
                id                    INTEGER PRIMARY KEY AUTOINCREMENT,
                ai_action_request_id  INTEGER NOT NULL REFERENCES ai_action_requests(id),
                entity_type           TEXT NOT NULL,
                entity_id             INTEGER,
                raw_reference         TEXT,
                normalized_reference  TEXT,
                confidence_score      REAL,
                resolution_status     TEXT NOT NULL,
                candidate_payload_json TEXT NOT NULL DEFAULT '[]',
                created_at            TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_ai_action_entities_request
            ON ai_action_entities(ai_action_request_id, id ASC)
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS ai_action_events (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                ai_action_request_id INTEGER NOT NULL REFERENCES ai_action_requests(id),
                event_type           TEXT NOT NULL,
                payload_json         TEXT NOT NULL DEFAULT '{}',
                created_at           TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_ai_action_events_request
            ON ai_action_events(ai_action_request_id, id ASC)
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS action_sessions (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                ai_action_request_id INTEGER NOT NULL REFERENCES ai_action_requests(id),
                channel              TEXT NOT NULL,
                actor_type           TEXT NOT NULL,
                actor_id             INTEGER,
                organization_id      INTEGER REFERENCES organizations(id),
                location_id          INTEGER NOT NULL REFERENCES locations(id),
                status               TEXT NOT NULL DEFAULT 'active',
                pending_prompt_type  TEXT,
                pending_payload_json TEXT NOT NULL DEFAULT '{}',
                expires_at           TEXT,
                created_at           TEXT NOT NULL,
                updated_at           TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_action_sessions_request
            ON action_sessions(ai_action_request_id, status, id DESC)
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS schedules (
                id                       INTEGER PRIMARY KEY AUTOINCREMENT,
                location_id              INTEGER NOT NULL REFERENCES locations(id),
                week_start_date          TEXT NOT NULL,
                week_end_date            TEXT NOT NULL,
                lifecycle_state          TEXT NOT NULL DEFAULT 'draft',
                current_version_id       INTEGER,
                derived_from_schedule_id INTEGER REFERENCES schedules(id),
                created_by               TEXT,
                created_at               TEXT NOT NULL,
                updated_at               TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_schedules_location_week
            ON schedules(location_id, week_start_date)
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS schedule_versions (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                schedule_id         INTEGER NOT NULL REFERENCES schedules(id),
                version_number      INTEGER NOT NULL,
                version_type        TEXT NOT NULL,
                snapshot_json       TEXT NOT NULL DEFAULT '{}',
                change_summary_json TEXT NOT NULL DEFAULT '{}',
                published_at        TEXT,
                published_by        TEXT,
                created_at          TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_schedule_versions_schedule_version
            ON schedule_versions(schedule_id, version_number)
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS schedule_templates (
                id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                location_id        INTEGER NOT NULL REFERENCES locations(id),
                name               TEXT NOT NULL,
                description        TEXT,
                source_schedule_id INTEGER REFERENCES schedules(id),
                created_by         TEXT,
                created_at         TEXT NOT NULL,
                updated_at         TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_schedule_templates_location
            ON schedule_templates(location_id, id DESC)
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS schedule_template_shifts (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                template_id       INTEGER NOT NULL REFERENCES schedule_templates(id),
                day_of_week       INTEGER NOT NULL,
                role              TEXT NOT NULL,
                start_time        TEXT NOT NULL,
                end_time          TEXT NOT NULL,
                spans_midnight    INTEGER NOT NULL DEFAULT 0,
                pay_rate          REAL NOT NULL DEFAULT 0,
                requirements      TEXT NOT NULL DEFAULT '[]',
                shift_label       TEXT,
                notes             TEXT,
                worker_id         INTEGER REFERENCES workers(id),
                assignment_status TEXT NOT NULL DEFAULT 'open',
                created_at        TEXT NOT NULL,
                updated_at        TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_schedule_template_shifts_template
            ON schedule_template_shifts(template_id, day_of_week, start_time, id)
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS shift_assignments (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                shift_id          INTEGER NOT NULL REFERENCES shifts(id),
                worker_id         INTEGER REFERENCES workers(id),
                assignment_status TEXT NOT NULL DEFAULT 'open',
                source            TEXT NOT NULL DEFAULT 'manual',
                created_at        TEXT NOT NULL,
                updated_at        TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_shift_assignments_shift
            ON shift_assignments(shift_id)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_shift_assignments_worker
            ON shift_assignments(worker_id, assignment_status)
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS import_jobs (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                location_id  INTEGER NOT NULL REFERENCES locations(id),
                import_type  TEXT NOT NULL,
                filename     TEXT,
                status       TEXT NOT NULL DEFAULT 'uploaded',
                mapping_json TEXT NOT NULL DEFAULT '{}',
                summary_json TEXT NOT NULL DEFAULT '{}',
                columns_json TEXT NOT NULL DEFAULT '[]',
                uploaded_csv TEXT,
                created_at   TEXT NOT NULL,
                updated_at   TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_import_jobs_location_status
            ON import_jobs(location_id, status, id DESC)
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS import_row_results (
                id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                import_job_id      INTEGER NOT NULL REFERENCES import_jobs(id),
                row_number         INTEGER NOT NULL,
                entity_type        TEXT NOT NULL,
                outcome            TEXT NOT NULL,
                error_code         TEXT,
                error_message      TEXT,
                raw_payload        TEXT NOT NULL DEFAULT '{}',
                normalized_payload TEXT,
                resolution_action  TEXT,
                resolved_at        TEXT,
                resolved_by        TEXT,
                committed_at       TEXT,
                committed_entity_id INTEGER,
                created_at         TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_import_row_results_job_row
            ON import_row_results(import_job_id, row_number, id)
        """)

        await _ensure_column(
            db,
            "organizations",
            "location_count_estimate",
            "INTEGER",
        )
        await _ensure_column(
            db,
            "locations",
            "organization_id",
            "INTEGER REFERENCES organizations(id)",
        )
        await _ensure_column(
            db,
            "locations",
            "employee_count",
            "INTEGER",
        )
        await _ensure_column(
            db,
            "locations",
            "vertical",
            "TEXT NOT NULL DEFAULT 'restaurant'",
        )
        await _ensure_column(
            db,
            "locations",
            "integration_status",
            "TEXT",
        )
        await _ensure_column(
            db,
            "locations",
            "last_roster_sync_at",
            "TEXT",
        )
        await _ensure_column(
            db,
            "locations",
            "last_roster_sync_status",
            "TEXT",
        )
        await _ensure_column(
            db,
            "locations",
            "last_schedule_sync_at",
            "TEXT",
        )
        await _ensure_column(
            db,
            "locations",
            "last_schedule_sync_status",
            "TEXT",
        )
        await _ensure_column(
            db,
            "locations",
            "last_sync_error",
            "TEXT",
        )
        await _ensure_column(
            db,
            "locations",
            "integration_state",
            "TEXT",
        )
        await _ensure_column(
            db,
            "locations",
            "last_event_sync_at",
            "TEXT",
        )
        await _ensure_column(
            db,
            "locations",
            "last_rolling_sync_at",
            "TEXT",
        )
        await _ensure_column(
            db,
            "locations",
            "last_daily_sync_at",
            "TEXT",
        )
        await _ensure_column(
            db,
            "locations",
            "last_writeback_at",
            "TEXT",
        )
        await _ensure_column(
            db,
            "locations",
            "last_manager_digest_sent_at",
            "TEXT",
        )
        await _ensure_column(
            db,
            "locations",
            "writeback_enabled",
            "INTEGER NOT NULL DEFAULT 0",
        )
        await _ensure_column(
            db,
            "locations",
            "writeback_subscription_tier",
            "TEXT NOT NULL DEFAULT 'core'",
        )
        await _ensure_column(
            db,
            "locations",
            "backfill_shifts_enabled",
            "INTEGER NOT NULL DEFAULT 1",
        )
        await _ensure_column(
            db,
            "locations",
            "backfill_shifts_launch_state",
            "TEXT NOT NULL DEFAULT 'enabled'",
        )
        await _ensure_column(
            db,
            "locations",
            "backfill_shifts_beta_eligible",
            "INTEGER NOT NULL DEFAULT 0",
        )
        await _ensure_column(
            db,
            "locations",
            "coverage_requires_manager_approval",
            "INTEGER NOT NULL DEFAULT 0",
        )
        await _ensure_column(
            db,
            "locations",
            "late_arrival_policy",
            "TEXT NOT NULL DEFAULT 'wait'",
        )
        await _ensure_column(
            db,
            "locations",
            "missed_check_in_policy",
            "TEXT NOT NULL DEFAULT 'start_coverage'",
        )
        await _ensure_column(
            db,
            "locations",
            "timezone",
            "TEXT",
        )
        await _ensure_column(
            db,
            "locations",
            "operating_mode",
            "TEXT",
        )
        await _ensure_column(
            db,
            "locations",
            "place_provider",
            "TEXT",
        )
        await _ensure_column(
            db,
            "locations",
            "place_id",
            "TEXT",
        )
        await _ensure_column(
            db,
            "locations",
            "place_resource_name",
            "TEXT",
        )
        await _ensure_column(
            db,
            "locations",
            "place_display_name",
            "TEXT",
        )
        await _ensure_column(
            db,
            "locations",
            "place_brand_name",
            "TEXT",
        )
        await _ensure_column(
            db,
            "locations",
            "place_location_label",
            "TEXT",
        )
        await _ensure_column(
            db,
            "locations",
            "place_formatted_address",
            "TEXT",
        )
        await _ensure_column(
            db,
            "locations",
            "place_primary_type",
            "TEXT",
        )
        await _ensure_column(
            db,
            "locations",
            "place_primary_type_display_name",
            "TEXT",
        )
        await _ensure_column(
            db,
            "locations",
            "place_business_status",
            "TEXT",
        )
        await _ensure_column(
            db,
            "locations",
            "place_latitude",
            "REAL",
        )
        await _ensure_column(
            db,
            "locations",
            "place_longitude",
            "REAL",
        )
        await _ensure_column(
            db,
            "locations",
            "place_google_maps_uri",
            "TEXT",
        )
        await _ensure_column(
            db,
            "locations",
            "place_website_uri",
            "TEXT",
        )
        await _ensure_column(
            db,
            "locations",
            "place_national_phone_number",
            "TEXT",
        )
        await _ensure_column(
            db,
            "locations",
            "place_international_phone_number",
            "TEXT",
        )
        await _ensure_column(
            db,
            "locations",
            "place_utc_offset_minutes",
            "INTEGER",
        )
        await _ensure_column(
            db,
            "locations",
            "place_rating",
            "REAL",
        )
        await _ensure_column(
            db,
            "locations",
            "place_user_rating_count",
            "INTEGER",
        )
        await _ensure_column(
            db,
            "locations",
            "place_city",
            "TEXT",
        )
        await _ensure_column(
            db,
            "locations",
            "place_state_region",
            "TEXT",
        )
        await _ensure_column(
            db,
            "locations",
            "place_postal_code",
            "TEXT",
        )
        await _ensure_column(
            db,
            "locations",
            "place_country_code",
            "TEXT",
        )
        await _ensure_column(
            db,
            "locations",
            "place_neighborhood",
            "TEXT",
        )
        await _ensure_column(
            db,
            "locations",
            "place_sublocality",
            "TEXT",
        )
        await _ensure_column(
            db,
            "locations",
            "place_types",
            "TEXT NOT NULL DEFAULT '[]'",
        )
        await _ensure_column(
            db,
            "locations",
            "place_address_components",
            "TEXT NOT NULL DEFAULT '[]'",
        )
        await _ensure_column(
            db,
            "locations",
            "place_regular_opening_hours",
            "TEXT NOT NULL DEFAULT '{}'",
        )
        await _ensure_column(
            db,
            "locations",
            "place_plus_code",
            "TEXT NOT NULL DEFAULT '{}'",
        )
        await _ensure_column(
            db,
            "locations",
            "place_metadata",
            "TEXT NOT NULL DEFAULT '{}'",
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
            "location_assignments",
            "TEXT NOT NULL DEFAULT '[]'",
        )
        await _ensure_column(
            db,
            "workers",
            "locations_worked",
            "TEXT NOT NULL DEFAULT '[]'",
        )
        await _ensure_column(
            db,
            "workers",
            "first_name",
            "TEXT",
        )
        await _ensure_column(
            db,
            "workers",
            "last_name",
            "TEXT",
        )
        await _ensure_column(
            db,
            "workers",
            "employment_status",
            "TEXT",
        )
        await _ensure_column(
            db,
            "workers",
            "max_hours_per_week",
            "INTEGER",
        )
        await _ensure_column(
            db,
            "shifts",
            "reminder_sent_at",
            "TEXT",
        )
        await _ensure_column(
            db,
            "shifts",
            "spans_midnight",
            "INTEGER NOT NULL DEFAULT 0",
        )
        await _ensure_column(
            db,
            "shifts",
            "schedule_id",
            "INTEGER REFERENCES schedules(id)",
        )
        await _ensure_column(
            db,
            "shifts",
            "shift_label",
            "TEXT",
        )
        await _ensure_column(
            db,
            "shifts",
            "notes",
            "TEXT",
        )
        await _ensure_column(
            db,
            "shifts",
            "published_state",
            "TEXT",
        )
        await _ensure_column(
            db,
            "shifts",
            "escalated_from_worker_id",
            "INTEGER REFERENCES workers(id)",
        )
        await _ensure_column(
            db,
            "shifts",
            "confirmation_requested_at",
            "TEXT",
        )
        await _ensure_column(
            db,
            "shifts",
            "worker_confirmed_at",
            "TEXT",
        )
        await _ensure_column(
            db,
            "shifts",
            "worker_declined_at",
            "TEXT",
        )
        await _ensure_column(
            db,
            "shifts",
            "confirmation_escalated_at",
            "TEXT",
        )
        await _ensure_column(
            db,
            "shifts",
            "check_in_requested_at",
            "TEXT",
        )
        await _ensure_column(
            db,
            "shifts",
            "checked_in_at",
            "TEXT",
        )
        await _ensure_column(
            db,
            "shifts",
            "late_reported_at",
            "TEXT",
        )
        await _ensure_column(
            db,
            "shifts",
            "late_eta_minutes",
            "INTEGER",
        )
        await _ensure_column(
            db,
            "shifts",
            "check_in_escalated_at",
            "TEXT",
        )
        await _ensure_column(
            db,
            "shifts",
            "attendance_action_state",
            "TEXT",
        )
        await _ensure_column(
            db,
            "shifts",
            "attendance_action_updated_at",
            "TEXT",
        )
        await _ensure_column(
            db,
            "webhook_receipts",
            "duplicate_count",
            "INTEGER NOT NULL DEFAULT 0",
        )
        await _ensure_column(
            db,
            "webhook_receipts",
            "last_seen_at",
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
            "pending_claim_worker_id",
            "INTEGER REFERENCES workers(id)",
        )
        await _ensure_column(
            db,
            "cascades",
            "pending_claim_at",
            "TEXT",
        )
        await _ensure_column(
            db,
            "cascades",
            "standby_queue",
            "TEXT NOT NULL DEFAULT '[]'",
        )
        await _ensure_column(
            db,
            "onboarding_sessions",
            "lead_source",
            "TEXT",
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
        await _ensure_column(
            db,
            "import_row_results",
            "resolution_action",
            "TEXT",
        )
        await _ensure_column(
            db,
            "import_row_results",
            "resolved_at",
            "TEXT",
        )
        await _ensure_column(
            db,
            "import_row_results",
            "resolved_by",
            "TEXT",
        )
        await _ensure_column(
            db,
            "import_row_results",
            "committed_at",
            "TEXT",
        )
        await _ensure_column(
            db,
            "import_row_results",
            "committed_entity_id",
            "INTEGER",
        )

        await _normalize_location_json_fields(db)
        await db.commit()


async def _ensure_column(
    db: aiosqlite.Connection,
    table_name: str,
    column_name: str,
    column_def: str,
) -> None:
    async with db.execute(f'PRAGMA table_info("{table_name}")') as cur:
        rows = await cur.fetchall()
    existing = {row[1] for row in rows}
    if column_name not in existing:
        await db.execute(
            f'ALTER TABLE "{table_name}" ADD COLUMN "{column_name}" {column_def}'
        )


async def _table_exists(db: aiosqlite.Connection, table_name: str) -> bool:
    async with db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ) as cur:
        return await cur.fetchone() is not None


async def _column_exists(
    db: aiosqlite.Connection,
    table_name: str,
    column_name: str,
) -> bool:
    if not await _table_exists(db, table_name):
        return False
    async with db.execute(f'PRAGMA table_info("{table_name}")') as cur:
        rows = await cur.fetchall()
    return any(row[1] == column_name for row in rows)


async def _rename_column_if_needed(
    db: aiosqlite.Connection,
    table_name: str,
    old_name: str,
    new_name: str,
) -> None:
    if await _column_exists(db, table_name, old_name) and not await _column_exists(
        db, table_name, new_name
    ):
        await db.execute(
            f'ALTER TABLE "{table_name}" RENAME COLUMN "{old_name}" TO "{new_name}"'
        )


async def _migrate_location_schema(db: aiosqlite.Connection) -> None:
    if await _table_exists(db, "restaurants") and not await _table_exists(db, "locations"):
        await db.execute("ALTER TABLE restaurants RENAME TO locations")

    await _rename_column_if_needed(db, "workers", "restaurant_id", "location_id")
    await _rename_column_if_needed(
        db, "workers", "restaurant_assignments", "location_assignments"
    )
    await _rename_column_if_needed(db, "workers", "restaurants_worked", "locations_worked")
    await _rename_column_if_needed(db, "shifts", "restaurant_id", "location_id")
    await _rename_column_if_needed(db, "integration_events", "restaurant_id", "location_id")
    await _rename_column_if_needed(db, "sync_jobs", "restaurant_id", "location_id")


async def _normalize_location_json_fields(db: aiosqlite.Connection) -> None:
    if await _column_exists(db, "workers", "location_assignments"):
        await db.execute(
            """
            UPDATE workers
            SET location_assignments = REPLACE(location_assignments, '"restaurant_id"', '"location_id"')
            WHERE location_assignments LIKE '%"restaurant_id"%'
            """
        )
    if await _column_exists(db, "locations", "place_types"):
        await db.execute(
            """
            UPDATE locations
            SET place_types = COALESCE(NULLIF(place_types, ''), '[]'),
                place_address_components = COALESCE(NULLIF(place_address_components, ''), '[]'),
                place_regular_opening_hours = COALESCE(NULLIF(place_regular_opening_hours, ''), '{}'),
                place_plus_code = COALESCE(NULLIF(place_plus_code, ''), '{}'),
                place_metadata = COALESCE(NULLIF(place_metadata, ''), '{}')
            """
        )
