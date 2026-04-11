from sqlalchemy import CheckConstraint, UniqueConstraint

from app.models.events import PlatformEvent
from app.models.projections import FeedProjection, ProjectionCursor


def test_feed_projection_table_contract_includes_replay_and_scope_indexes():
    constraint_columns = {
        constraint.name: tuple(column.name for column in constraint.columns)
        for constraint in FeedProjection.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    index_names = {index.name for index in FeedProjection.__table__.indexes}

    assert constraint_columns["uq_feed_projections_projection_name_source_event_id"] == (
        "projection_name",
        "source_event_id",
    )
    assert {
        "ix_feed_projections_projection_name_business_id_occurred_at_id",
        "ix_feed_projections_projection_name_business_location_occurred_at_id",
        "ix_feed_projections_projection_name_event_type_occurred_at_id",
        "ix_feed_projections_projection_name_trace_id_occurred_at_id",
    }.issubset(index_names)


def test_projection_cursor_checkpoint_pair_contract_is_explicit():
    check_constraints = [
        constraint
        for constraint in ProjectionCursor.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    ]

    assert ProjectionCursor.__table__.c.projection_name.primary_key is True
    assert ProjectionCursor.__table__.c.schema_version.server_default is not None
    assert any(
        constraint.name == "ck_projection_cursors_checkpoint_pair"
        and "last_source_created_at IS NULL" in str(constraint.sqltext)
        and "last_source_event_id IS NULL" in str(constraint.sqltext)
        for constraint in check_constraints
    )


def test_platform_event_table_includes_created_at_replay_index():
    index_names = {index.name for index in PlatformEvent.__table__.indexes}

    assert "ix_platform_events_created_at_id" in index_names
