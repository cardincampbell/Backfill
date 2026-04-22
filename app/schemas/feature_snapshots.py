from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import Field

from app.models.common import BucketAlignmentMode, DemandFeatureSnapshotStatus, DstHandlingMode
from app.schemas.common import BaseSchema


class DemandFeatureSnapshotPointPayload(BaseSchema):
    location_id: Optional[UUID] = None
    role_id: Optional[UUID] = None
    bucket_start: datetime
    bucket_end: datetime
    feature_payload: dict = Field(default_factory=dict)
    feature_vector_version: str = "v1"


class DemandFeatureSnapshotContract(BaseSchema):
    planning_window_start: datetime
    planning_window_end: datetime
    timezone_name: str
    bucket_minutes: int = Field(gt=0, le=1440)
    bucket_alignment_mode: BucketAlignmentMode = BucketAlignmentMode.local_operating_time
    dst_handling_mode: DstHandlingMode = DstHandlingMode.skip_missing_repeat_distinct
    feature_schema_version: str = "v1"
    snapshot_status: DemandFeatureSnapshotStatus = DemandFeatureSnapshotStatus.completed
    operating_hours_version: Optional[str] = None
    source_summary: dict = Field(default_factory=dict)
    points: list[DemandFeatureSnapshotPointPayload] = Field(default_factory=list)
