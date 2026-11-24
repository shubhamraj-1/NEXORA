"""Request and response models for the NEXORA agent endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field, HttpUrl, field_validator

from .security import validate_public_url


class AgentRunRequest(BaseModel):
    """Input for a single navigation + extraction run."""

    url: HttpUrl = Field(description="Absolute http(s) URL to visit.")
    instruction: str = Field(
        default="Extract the main content of this page.",
        max_length=2000,
        description=(
            "Natural-language goal for the run. Keyword hints widen extraction; "
            "when AI is enabled the planner uses it to build a short plan and answer."
        ),
    )
    max_links: int = Field(
        default=25,
        ge=0,
        le=200,
        description="Maximum number of links to return.",
    )
    include_screenshot: bool = Field(
        default=False,
        description="Capture a full-page PNG and return it base64 encoded.",
    )
    timeout_ms: int = Field(
        default=30_000,
        ge=1_000,
        le=120_000,
        description="Navigation and network-idle budget in milliseconds.",
    )
    ai: bool = Field(
        default=True,
        description=(
            "Use the OpenAI planner when a key is configured. Ignored otherwise, "
            "so the endpoint keeps returning deterministic extraction."
        ),
    )

    @field_validator("url")
    @classmethod
    def reject_unsafe_urls(cls, value: HttpUrl) -> HttpUrl:
        """Block SSRF targets before any browser work is scheduled."""
        validate_public_url(value)
        return value


class ExtractedLink(BaseModel):
    """A single anchor discovered on the page."""

    text: str
    href: str


class AgentStep(BaseModel):
    """One timestamped action taken during the run."""

    action: str
    detail: str
    duration_ms: int


class AgentRunResponse(BaseModel):
    """Result of a navigation + extraction run."""

    url: str
    final_url: str
    title: str
    description: str
    status_code: int | None
    instruction: str
    text: str
    text_truncated: bool
    headings: list[str]
    links: list[ExtractedLink]
    screenshot_base64: str | None
    steps: list[AgentStep]
    elapsed_ms: int
    plan: list[str] = Field(default_factory=list)
    answer: str | None = None
    model: str | None = None
