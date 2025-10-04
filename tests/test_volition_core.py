from datetime import datetime, timedelta, timezone

import pytest

from src.volition_core import VolitionCore


class FakeClock:
    def __init__(self, start: datetime) -> None:
        self._now = start

    def now(self) -> datetime:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now = self._now + timedelta(seconds=seconds)


@pytest.fixture()
def clock() -> FakeClock:
    return FakeClock(datetime(2024, 1, 1, tzinfo=timezone.utc))


def test_accepts_first_intent(clock: FakeClock) -> None:
    core = VolitionCore(clock=clock.now)
    result = core.handle_intent(
        user_id="U1",
        team_id="T1",
        text="Plan the weekly standup",
        correlation_id="abc123",
    )
    assert result.accepted is True
    assert result.memory[0].text == "Plan the weekly standup"


def test_rejects_duplicate_within_window(clock: FakeClock) -> None:
    core = VolitionCore(clock=clock.now, duplicate_window=timedelta(minutes=5))
    core.handle_intent(
        user_id="U1",
        team_id="T1",
        text="Send the latest metrics",
        correlation_id="c1",
    )
    clock.advance(120)
    result = core.handle_intent(
        user_id="U1",
        team_id="T1",
        text="Send the latest metrics",
        correlation_id="c2",
    )
    assert result.accepted is False
    assert "already" in result.message.lower()


def test_enforces_cooldown(clock: FakeClock) -> None:
    core = VolitionCore(clock=clock.now, cooldown=timedelta(seconds=45))
    core.handle_intent(
        user_id="U1",
        team_id="T1",
        text="Summarise the slack channel",
        correlation_id="c1",
    )
    clock.advance(20)
    result = core.handle_intent(
        user_id="U1",
        team_id="T1",
        text="Look up release notes",
        correlation_id="c2",
    )
    assert result.accepted is False
    assert "seconds" in result.message.lower()


def test_rejects_untrusted_workspace(clock: FakeClock) -> None:
    core = VolitionCore(clock=clock.now, trusted_workspace_ids=("TRUSTED",))
    result = core.handle_intent(
        user_id="U2",
        team_id="UNTRUSTED",
        text="Deploy to prod",
        correlation_id="c3",
    )
    assert result.accepted is False
    assert "trusted" in result.message.lower()
