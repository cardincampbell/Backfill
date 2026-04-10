from __future__ import annotations

from dataclasses import dataclass

from app.schemas.copilot import CopilotIntentRead, CopilotToolRead


@dataclass(frozen=True)
class CopilotToolDefinition:
    name: str
    title: str
    description: str
    intent_family: str
    mutates_state: bool = False
    availability: str = "available"

    def to_read(self) -> CopilotToolRead:
        return CopilotToolRead(
            name=self.name,
            title=self.title,
            description=self.description,
            intent_family=self.intent_family,
            mutates_state=self.mutates_state,
            availability=self.availability,
        )


_TOOL_REGISTRY: tuple[CopilotToolDefinition, ...] = (
    CopilotToolDefinition(
        name="schedule.list_open_shifts",
        title="Open shifts",
        description="Summarize open shifts that still need coverage.",
        intent_family="schedule",
    ),
    CopilotToolDefinition(
        name="coverage.list_active_campaigns",
        title="Active campaigns",
        description="Summarize active coverage campaigns and their current status.",
        intent_family="coverage",
    ),
    CopilotToolDefinition(
        name="schedule.list_manager_actions",
        title="Manager actions",
        description="Show items that need manager attention right now.",
        intent_family="schedule",
    ),
)

_HELP_TOOL = CopilotToolDefinition(
    name="copilot.help",
    title="Copilot help",
    description="Explain what the Copilot can do today.",
    intent_family="copilot",
)


def list_tools() -> list[CopilotToolRead]:
    return [tool.to_read() for tool in (*_TOOL_REGISTRY, _HELP_TOOL)]


def get_tool(tool_name: str) -> CopilotToolDefinition | None:
    for tool in (*_TOOL_REGISTRY, _HELP_TOOL):
        if tool.name == tool_name:
            return tool
    return None


def resolve_intent(text: str) -> CopilotIntentRead:
    normalized = " ".join(text.lower().split())

    if any(phrase in normalized for phrase in ("open shift", "open shifts", "needs coverage", "unfilled shift")):
        return CopilotIntentRead(
            family="schedule",
            tool_name="schedule.list_open_shifts",
            reasoning="The request is asking for unfilled shifts that still need coverage.",
            confidence=0.94,
        )

    if any(phrase in normalized for phrase in ("needs my attention", "manager action", "what needs attention", "attention right now")):
        return CopilotIntentRead(
            family="schedule",
            tool_name="schedule.list_manager_actions",
            reasoning="The request is asking for issues that require operator review or follow-up.",
            confidence=0.91,
        )

    if any(phrase in normalized for phrase in ("campaign", "coverage status", "active coverage", "active campaign")):
        return CopilotIntentRead(
            family="coverage",
            tool_name="coverage.list_active_campaigns",
            reasoning="The request is asking for the current state of active coverage campaigns.",
            confidence=0.9,
        )

    return CopilotIntentRead(
        family="copilot",
        tool_name="copilot.help",
        reasoning="No execution tool matched confidently, so return the Copilot help surface.",
        confidence=0.42,
    )
