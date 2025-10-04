from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Deque, Iterable, Sequence


@dataclass(frozen=True)
class IntentRecord:
    user_id: str
    team_id: str
    text: str
    timestamp: datetime
    correlation_id: str


@dataclass(frozen=True)
class IntentResult:
    accepted: bool
    message: str
    memory: Sequence[IntentRecord]


class InMemoryVolitionStore:
    """Simple bounded store for intent records."""

    def __init__(self, *, max_events: int = 200) -> None:
        self._events: Deque[IntentRecord] = deque(maxlen=max_events)

    def append(self, record: IntentRecord) -> None:
        self._events.append(record)

    def recent(self, limit: int = 5) -> Sequence[IntentRecord]:
        events = list(self._events)
        events.reverse()
        return events[:limit]

    def last_for_user(self, user_id: str) -> IntentRecord | None:
        for record in reversed(self._events):
            if record.user_id == user_id:
                return record
        return None


class VolitionCore:
    def __init__(
        self,
        *,
        store: InMemoryVolitionStore | None = None,
        duplicate_window: timedelta = timedelta(minutes=3),
        cooldown: timedelta = timedelta(seconds=20),
        trusted_workspace_ids: Iterable[str] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.store = store or InMemoryVolitionStore()
        self.duplicate_window = duplicate_window
        self.cooldown = cooldown
        self.trusted_workspace_ids = tuple(trusted_workspace_ids or ())
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def handle_intent(
        self,
        *,
        user_id: str,
        team_id: str,
        text: str,
        correlation_id: str,
    ) -> IntentResult:
        now = self._clock()

        if self.trusted_workspace_ids and team_id not in self.trusted_workspace_ids:
            return IntentResult(
                accepted=False,
                message=(
                    "I am scoped to trusted workspaces only. "
                    "Ask an admin to add this workspace to TRUSTED_WORKSPACE_IDS."
                ),
                memory=self.store.recent(),
            )

        last_for_user = self.store.last_for_user(user_id)
        if last_for_user:
            if last_for_user.text.strip() == text.strip() and (
                now - last_for_user.timestamp
            ) <= self.duplicate_window:
                return IntentResult(
                    accepted=False,
                    message="I already have that request on my queue.",
                    memory=self.store.recent(),
                )
            if (now - last_for_user.timestamp) <= self.cooldown:
                remaining = int((self.cooldown - (now - last_for_user.timestamp)).total_seconds())
                return IntentResult(
                    accepted=False,
                    message=f"Hold on — give me about {remaining} more seconds before sending another instruction.",
                    memory=self.store.recent(),
                )

        record = IntentRecord(
            user_id=user_id,
            team_id=team_id,
            text=text,
            timestamp=now,
            correlation_id=correlation_id,
        )
        self.store.append(record)

        return IntentResult(
            accepted=True,
            message="Intent acknowledged. Logging it to my volition ledger now.",
            memory=self.store.recent(),
        )
