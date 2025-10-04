# Main Slack bot logic for Gabe

from __future__ import annotations

import re
from typing import Any, Dict

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_sdk.errors import SlackApiError

from .utils import SlackConfig, correlation_id, create_logger, format_bullet_list
from .volition_core import IntentResult, VolitionCore

logger = create_logger(__name__)


def sanitise_text(raw_text: str, bot_user_id: str | None) -> str:
    if not raw_text:
        return ""
    if bot_user_id:
        return re.sub(rf"<@{bot_user_id}>", "", raw_text).strip()
    return raw_text.strip()


def register_routes(app: App, *, volition: VolitionCore, config: SlackConfig) -> None:
    @app.event("app_mention")
    def handle_app_mention(body: Dict[str, Any], say):  # type: ignore[override]
        event = body.get("event", {})
        bot_user_id = body.get("authorizations", [{}])[0].get("user_id")
        text = sanitise_text(event.get("text", ""), bot_user_id)
        team_id = event.get("team", "") or body.get("team_id", "")
        user_id = event.get("user")
        if not user_id:
            return
        cid = correlation_id()

        result = volition.handle_intent(
            user_id=user_id,
            team_id=team_id,
            text=text,
            correlation_id=cid,
        )

        say(_format_response(result, cid))

    @app.event("message")
    def handle_dm(body: Dict[str, Any], say):  # type: ignore[override]
        event = body.get("event", {})
        if event.get("channel_type") != "im":
            return
        bot_user_id = body.get("authorizations", [{}])[0].get("user_id")
        user_id = event.get("user")
        if user_id == bot_user_id:
            return
        if not user_id:
            return
        cid = correlation_id()
        team_id = event.get("team", "") or body.get("team_id", "")
        text = sanitise_text(event.get("text", ""), bot_user_id)
        result = volition.handle_intent(
            user_id=user_id,
            team_id=team_id,
            text=text,
            correlation_id=cid,
        )
        say(_format_response(result, cid))

    @app.command("/gabe")
    def handle_slash_command(ack, body, respond):  # type: ignore[override]
        ack()
        cid = correlation_id()
        result = volition.handle_intent(
            user_id=body.get("user_id"),
            team_id=body.get("team_id"),
            text=body.get("text", ""),
            correlation_id=cid,
        )
        respond(_format_response(result, cid))


def _format_response(result: IntentResult, cid: str) -> str:
    memory_lines = [
        f"{record.timestamp.strftime('%H:%M:%S')} {record.user_id}: {record.text}"
        for record in result.memory
    ]
    memory_block = (
        f"\nRecent intents:\n{format_bullet_list(memory_lines)}"
        if memory_lines
        else ""
    )
    status = "✅" if result.accepted else "⚠️"
    return f"{status} {result.message}\n• correlation_id={cid}{memory_block}"


def send_startup_heartbeat(app: App, config: SlackConfig) -> None:
    if not config.home_channel:
        return
    try:
        app.client.chat_postMessage(
            channel=config.home_channel,
            text="Gabe reporting for duty. Mention me or DM to give instructions.",
        )
    except SlackApiError as exc:  # pragma: no cover - best effort notification
        logger.warning(
            "Unable to post startup heartbeat: %s",
            getattr(exc.response, "data", exc),
        )


def build_app(config: SlackConfig) -> App:
    app = App(
        token=config.bot_token,
        signing_secret=config.signing_secret,
        process_before_response=True,
    )
    volition = VolitionCore(trusted_workspace_ids=config.trusted_workspace_ids)
    register_routes(app, volition=volition, config=config)
    return app


def main() -> None:
    try:
        config = SlackConfig.from_env()
    except ValueError as exc:
        logger.error("Configuration error: %s", exc)
        logger.info(
            "Create a .env file (cp config/.env.example .env) and fill in your Slack app tokens, "
            "or export the SLACK_* variables before rerunning."
        )
        raise SystemExit(1) from exc

    logger.info("Starting Gabe Slack agent")
    app = build_app(config)
    send_startup_heartbeat(app, config)
    handler = SocketModeHandler(app, app_token=config.app_token)
    handler.start()


if __name__ == "__main__":
    main()
