from __future__ import annotations

from uuid import UUID

from app.models.common import MembershipRole
from app.schemas.copilot import CopilotValidationResultRead
from app.services.auth import AuthContext, has_business_access, has_location_access

READ_ROLES = {
    MembershipRole.owner,
    MembershipRole.admin,
    MembershipRole.manager,
    MembershipRole.viewer,
}


def validate_tool_call(
    *,
    auth_ctx: AuthContext,
    business_id: UUID,
    location_id: UUID | None,
    tool_name: str,
) -> CopilotValidationResultRead:
    if not has_business_access(auth_ctx, business_id, allowed_roles=READ_ROLES):
        return CopilotValidationResultRead(
            ok=False,
            code="business_access_denied",
            message="You do not have access to this business context.",
        )

    if location_id is not None and not has_location_access(
        auth_ctx,
        business_id,
        location_id,
        allowed_roles=READ_ROLES,
    ):
        return CopilotValidationResultRead(
            ok=False,
            code="location_access_denied",
            message="You do not have access to this location context.",
        )

    if tool_name == "coverage.start_campaign":
        return CopilotValidationResultRead(
            ok=False,
            code="tool_not_available",
            message="Campaign-starting tools are not available in this Copilot scaffold yet.",
        )

    return CopilotValidationResultRead(
        ok=True,
        code="ok",
        message="Tool call validated.",
    )
