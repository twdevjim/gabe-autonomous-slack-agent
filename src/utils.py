from __future__ import annotations

import logging
import os
import sys
import uuid
from dataclasses import dataclass
from typing import Iterable, Mapping, Tuple

from dotenv import load_dotenv


@dataclass(frozen=True)
class SlackConfig:
    """Container for environment-driven Slack configuration."""

    bot_token: str
    app_token: str
    signing_secret: str
    trusted_workspace_ids: Tuple[str, ...]
    home_channel: str | None = None

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
        *,
        load_env_file: bool = True,
    ) -> "SlackConfig":
        if load_env_file:
            load_dotenv()

        source = env or os.environ

        bot_token, app_token, signing_secret = _require_env_values(
            source,
            "SLACK_BOT_TOKEN",
            "SLACK_APP_TOKEN",
            "SLACK_SIGNING_SECRET",
        )

        trusted_ids = _parse_workspace_ids(source.get("TRUSTED_WORKSPACE_IDS"))
        home_channel = source.get("GABE_HOME_CHANNEL") or None

        return cls(
            bot_token=bot_token,
            app_token=app_token,
            signing_secret=signing_secret,
            trusted_workspace_ids=trusted_ids,
            home_channel=home_channel,
        )


def _require_env_values(
    source: Mapping[str, str], *keys: str
) -> Tuple[str, ...]:
    missing: list[str] = []
    values: list[str] = []

    for key in keys:
        value = source.get(key)
        if value is None or not value.strip():
            missing.append(key)
        else:
            values.append(value)

    if missing:
        raise ValueError(
            "Missing mandatory Slack configuration: " + ", ".join(missing)
        )

    return tuple(values)


def _parse_workspace_ids(raw_value: str | None) -> Tuple[str, ...]:
    if not raw_value:
        return tuple()
    return tuple(
        workspace_id.strip()
        for workspace_id in raw_value.split(",")
        if workspace_id.strip()
    )


def create_logger(name: str) -> logging.Logger:
    """Configure a rich logger for the Slack agent."""

    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    handler = logging.StreamHandler(stream=sys.stdout)
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)

    logger.setLevel(os.environ.get("GABE_LOG_LEVEL", "INFO"))
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def correlation_id() -> str:
    """Generate a short correlation ID for tracing logs and responses."""

    return uuid.uuid4().hex[:8]


def format_bullet_list(items: Iterable[str]) -> str:
    return "\n".join(f"• {item}" for item in items)
