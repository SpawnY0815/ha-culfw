"""Learner for the thermostat that each window contact belongs to."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any, Final

from .const import (
    PAIRING_ALIVE,
    PAIRING_BURST_WINDOW,
    PAIRING_HIGH_POINTS,
    PAIRING_MAX_DELAY,
    PAIRING_MEDIUM_POINTS,
    PAIRING_MIN_POINTS,
    PAIRING_POINT_LIMIT,
    PAIRING_QUICK_POINTS,
    PAIRING_QUICK_REACTION,
    PAIRING_REACTION_LOG,
    PAIRING_RIVAL_SHARE,
    PAIRING_SILENT_POINTS,
    PAIRING_SLOW_POINTS,
)
from .parser import FhtCode

# The version of the stored votes. A store without a version holds the votes of the
# first learner, which counted nothing but changes of the window flag.
STORE_VERSION: Final = 2

# The commands that carry what a thermostat does when a contact changes state.
_ANSWER_CODES: Final = (FhtCode.DESIRED_TEMP, FhtCode.WARNINGS)
_MEASURED_CODES: Final = (FhtCode.MEASURED_LOW, FhtCode.MEASURED_HIGH)


class Confidence(StrEnum):
    """How sure the votes make the learner of a proposal."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True, slots=True)
class Evidence:
    """The proposal for a contact and what supports it."""

    thermostat: str
    confidence: Confidence
    # The changes of the contact that the thermostat answered, each counted once.
    events: int


@dataclass(slots=True)
class Votes:
    """What the radio showed about one contact and one thermostat.

    A quick answer is a telegram off the schedule of the thermostat within seconds of
    a change of the contact. A slow vote is a change of the window flag within minutes,
    and also a quick answer that another contact, which changed minutes before, could
    have caused as well. A silent vote is a change that the thermostat could have heard and did not answer
    while another thermostat did.
    """

    quick: int = 0
    slow: int = 0
    silent: int = 0

    @property
    def positive(self) -> int:
        """Return the points of the answers."""
        return PAIRING_QUICK_POINTS * self.quick + PAIRING_SLOW_POINTS * self.slow

    @property
    def points(self) -> int:
        """Return the points for the thermostat, the silence taken off."""
        return max(0, self.positive - PAIRING_SILENT_POINTS * self.silent)

    def to_dict(self) -> dict[str, int]:
        """Return the counts that are not zero."""
        return {
            name: count
            for name, count in (
                ("quick", self.quick),
                ("slow", self.slow),
                ("silent", self.silent),
            )
            if count
        }

    @classmethod
    def from_dict(cls, data: Any) -> Votes | None:
        """Return the votes stored by to_dict(), None if there are none or it is broken."""
        if not isinstance(data, Mapping):
            return None
        counts: dict[str, int] = {}
        for name in ("quick", "slow", "silent"):
            count = data.get(name, 0)
            if not _is_count(count):
                return None
            counts[name] = count
        votes = cls(**counts)
        return votes if votes.to_dict() else None

    def halve(self) -> None:
        """Halve the counts, so that old votes weigh less than new ones."""
        self.quick //= 2
        self.slow //= 2
        self.silent //= 2


@dataclass(frozen=True, slots=True)
class Reaction:
    """The answer of a thermostat to a change of state of a contact, for diagnostics."""

    thermostat: str
    at: datetime
    seconds: float
    opened: bool
    ambiguous: bool

    def to_dict(self) -> dict[str, Any]:
        """Return the reaction as a JSON-serializable dict."""
        return {
            "thermostat": self.thermostat,
            "at": self.at.isoformat(),
            "seconds": self.seconds,
            "opened": self.opened,
            "ambiguous": self.ambiguous,
        }

    @classmethod
    def from_dict(cls, data: Any) -> Reaction | None:
        """Return the reaction stored by to_dict(), None if it is broken."""
        if not isinstance(data, Mapping):
            return None
        thermostat, seconds = data.get("thermostat"), data.get("seconds")
        opened, ambiguous = data.get("opened"), data.get("ambiguous")
        try:
            at = datetime.fromisoformat(data["at"])
        except KeyError, TypeError, ValueError:
            return None
        if (
            not isinstance(thermostat, str)
            or at.tzinfo is None
            or not isinstance(seconds, int | float)
            or isinstance(seconds, bool)
            or seconds < 0
            or not isinstance(opened, bool)
            or not isinstance(ambiguous, bool)
        ):
            return None
        return cls(thermostat, at, float(seconds), opened, ambiguous)


@dataclass(slots=True)
class _ContactEvent:
    """A contact that opened or closed, and what the thermostats did about it."""

    contact: str
    opened: bool
    at: datetime
    # The thermostats that transmitted shortly before and so could have heard it.
    alive: set[str]
    # Another contact changed within the quick window, so no answer can be assigned.
    ambiguous: bool = False
    judged: bool = False
    quick: set[str] = field(default_factory=set)
    # The thermostats that answered quickly while another contact had changed within
    # `max_delay`, so that the answer may belong to the other one.
    crowded: set[str] = field(default_factory=set)
    voted: set[str] = field(default_factory=set)
    silent: set[str] = field(default_factory=set)
    reacted: set[str] = field(default_factory=set)


@dataclass(slots=True)
class WindowPairing:
    """Votes of the contacts for the thermostats they seem to belong to.

    A thermostat stores its contacts in slots and shows only the state of each slot,
    never the code of the contact, so the pairing cannot be read from the thermostat.
    The radio may still tell, in two ways:

    - A thermostat that has the contact answers a change of its state within about a
      second with a telegram off its schedule: the desired temperature, the warnings
      register, or both. No unpaired thermostat does. When exactly one contact changed
      and exactly one thermostat answered within `PAIRING_QUICK_REACTION`, that is a
      quick vote for the pair. The thermostats that could have heard the change and
      stayed silent get a silent vote, which counts less, because a thermostat that is
      busy misses a change now and then. A silent vote is taken back when the same
      thermostat answers later, because some answers come minutes late.
    - A thermostat sets the window flag of its warnings when one of its contacts is
      open, some time after the contact sent its telegram. When a flag change follows
      the change of exactly one contact within `max_delay`, that contact gets a slow
      vote for the thermostat. It is the weaker sign, and it is the only one for a
      thermostat that does not answer quickly.

    A change counts only when no other contact changed within the window around it. A
    quick answer while another contact changed within `max_delay` before counts as a
    slow vote and takes no silent votes along, because a thermostat answers minutes
    late as often as seconds.
    The quick votes are counted when the quick window has closed, so that a second
    thermostat that answers a moment later cannot make the proposal flicker. A
    thermostat is named when its points reach `PAIRING_MIN_POINTS` and the points of all
    others are at most a fraction of its own. One clean change is enough for that,
    further changes confirm it, and the learner only proposes: whoever owns it decides
    what to do with that.

    The owner reports the changes of the state of the contacts with `note_contact()`,
    every telegram of a thermostat with `note_telegram()` and the changes of its window
    flag with `note_thermostat()`, all with the time of the telegram. A contact that
    repeats its state is no change. Each call returns the contacts whose proposal
    or whose evidence for it (confidence, events) changed. The learner works on the
    times it is given and never waits, so a vote that depends on the end of a window is
    cast with the first call after it, or with `settle()`.

    The events are kept for `max_delay` only and are not persisted. The votes and the
    last answers per contact are persistent through `to_dict()` and `load()`. A contact
    that two thermostats follow collects points for both, so none of them gets a
    proposal.
    """

    max_delay: timedelta = PAIRING_MAX_DELAY
    votes: dict[str, dict[str, Votes]] = field(default_factory=dict)
    reactions: dict[str, list[Reaction]] = field(default_factory=dict)
    _events: list[_ContactEvent] = field(default_factory=list, repr=False)
    _heard: dict[str, datetime] = field(default_factory=dict, repr=False)
    _measured: dict[str, datetime] = field(default_factory=dict, repr=False)

    def note_contact(self, contact: str, opened: bool, at: datetime) -> tuple[str, ...]:
        """Remember that a contact opened or closed."""
        changed = self.settle(at)
        event = _ContactEvent(
            contact,
            opened,
            at,
            {
                thermostat
                for thermostat, last in self._heard.items()
                if at - last <= PAIRING_ALIVE
            },
        )
        for other in self._events:
            if other.contact != contact and at - other.at <= PAIRING_QUICK_REACTION:
                other.ambiguous = event.ambiguous = True
        self._events.append(event)
        return changed

    def note_telegram(
        self, thermostat: str, code: int, at: datetime
    ) -> tuple[str, ...]:
        """Look at a telegram of a thermostat for the answer to a contact.

        The actuator telegrams, the measured temperature and the warnings that come in
        the burst after it are the schedule of the thermostat. A desired temperature
        or a warnings telegram off the schedule is an answer.
        """
        changed = self.settle(at)
        self._heard[thermostat] = at
        if code in _MEASURED_CODES:
            self._measured[thermostat] = at
            return changed
        if code not in _ANSWER_CODES:
            return changed
        measured = self._measured.get(thermostat)
        if (
            code == FhtCode.WARNINGS
            and measured is not None
            and at - measured <= PAIRING_BURST_WINDOW
        ):
            return changed
        return _merge(changed, self._answer(thermostat, at, None))

    def note_thermostat(
        self, thermostat: str, window_open: bool, at: datetime
    ) -> tuple[str, ...]:
        """Count a change of the window flag of a thermostat."""
        changed = self.settle(at)
        self._heard[thermostat] = at
        return _merge(changed, self._answer(thermostat, at, window_open))

    def settle(self, now: datetime) -> tuple[str, ...]:
        """Cast the votes of the changes whose quick window has closed.

        Returns the contacts whose proposal or evidence changed because of that.
        """
        changed: list[str] = []
        for event in self._events:
            if not event.judged and now - event.at > PAIRING_QUICK_REACTION:
                event.judged = True
                if not event.ambiguous:
                    self._judge(event, changed)
        self._events = [e for e in self._events if now - e.at <= self.max_delay]
        return tuple(dict.fromkeys(changed))

    def suggestion(self, contact: str) -> str | None:
        """Return the thermostat that the votes name for a contact, if they are clear."""
        evidence = self.evidence(contact)
        return None if evidence is None else evidence.thermostat

    def evidence(self, contact: str) -> Evidence | None:
        """Return the proposal for a contact with its confidence, None if unclear.

        The confidence follows the points of the thermostat and drops one level while
        another thermostat has points as well. The events are the answers and the
        changes of the window flag that the thermostat gave to the contact. A change of
        the contact counts once, however many signs it left.
        """
        counts = self.votes.get(contact)
        if not counts:
            return None
        points = {thermostat: vote.points for thermostat, vote in counts.items()}
        thermostat, best = max(points.items(), key=lambda item: item[1])
        rivals = sum(points.values()) - best
        if best < PAIRING_MIN_POINTS or rivals > best * PAIRING_RIVAL_SHARE:
            return None
        # One level for each threshold that the points reach, and one less for a rival.
        level = (best >= PAIRING_MEDIUM_POINTS) + (best >= PAIRING_HIGH_POINTS)
        level = max(0, level - (rivals > 0))
        vote = counts[thermostat]
        return Evidence(thermostat, tuple(Confidence)[level], vote.quick + vote.slow)

    def forget(self, device_id: str) -> None:
        """Drop everything about a device, a contact or a thermostat."""
        self.votes.pop(device_id, None)
        self.reactions.pop(device_id, None)
        self._heard.pop(device_id, None)
        self._measured.pop(device_id, None)
        for contact, counts in list(self.votes.items()):
            counts.pop(device_id, None)
            if not counts:
                del self.votes[contact]
        for contact, log in list(self.reactions.items()):
            kept = [r for r in log if r.thermostat != device_id]
            if kept:
                self.reactions[contact] = kept
            else:
                del self.reactions[contact]
        self._events = [event for event in self._events if event.contact != device_id]
        for event in self._events:
            event.alive.discard(device_id)
            event.quick.discard(device_id)
            event.crowded.discard(device_id)
            event.voted.discard(device_id)
            event.silent.discard(device_id)
            event.reacted.discard(device_id)

    def to_dict(self) -> dict[str, Any]:
        """Return the votes and the answers as a JSON-serializable dict."""
        if not self.votes and not self.reactions:
            return {}
        data: dict[str, Any] = {
            "version": STORE_VERSION,
            "votes": {
                contact: {
                    thermostat: vote.to_dict() for thermostat, vote in counts.items()
                }
                for contact, counts in self.votes.items()
            },
        }
        if self.reactions:
            data["reactions"] = {
                contact: [reaction.to_dict() for reaction in log]
                for contact, log in self.reactions.items()
            }
        return data

    def report(self) -> dict[str, Any]:
        """Return what the learner knows per contact, for the diagnostics."""
        report: dict[str, Any] = {}
        for contact in sorted({*self.votes, *self.reactions}):
            evidence = self.evidence(contact)
            report[contact] = {
                "suggestion": None if evidence is None else evidence.thermostat,
                "confidence": None if evidence is None else evidence.confidence.value,
                "events": None if evidence is None else evidence.events,
                "thermostats": {
                    thermostat: {**vote.to_dict(), "points": vote.points}
                    for thermostat, vote in self.votes.get(contact, {}).items()
                },
                "reactions": [r.to_dict() for r in self.reactions.get(contact, [])],
            }
        return report

    def load(self, data: Any) -> None:
        """Restore what to_dict() saved, skipping what does not look like it.

        A store of the first learner has no version and holds the changes of the window
        flag per contact and thermostat, which are slow votes. A store of a version
        that is not known is left alone, because its meaning is not known.
        """
        if not isinstance(data, Mapping):
            return
        if "version" not in data:
            self._load_votes(data, legacy=True)
        elif data["version"] == STORE_VERSION:
            self._load_votes(data.get("votes"), legacy=False)
            self._load_reactions(data.get("reactions"))

    def _load_votes(self, stored: Any, *, legacy: bool) -> None:
        """Restore the votes of the current or of the first format."""
        if not isinstance(stored, Mapping):
            return
        for contact, counts in stored.items():
            if not (isinstance(contact, str) and isinstance(counts, Mapping)):
                continue
            valid: dict[str, Votes] = {}
            for thermostat, entry in counts.items():
                if not isinstance(thermostat, str):
                    continue
                if legacy:
                    vote = Votes(slow=entry) if _is_count(entry) else None
                    vote = vote if vote is not None and vote.slow else None
                else:
                    vote = Votes.from_dict(entry)
                if vote is not None:
                    valid[thermostat] = vote
            if valid:
                self.votes[contact] = valid

    def _load_reactions(self, stored: Any) -> None:
        """Restore the last answers per contact."""
        if not isinstance(stored, Mapping):
            return
        for contact, log in stored.items():
            if not (isinstance(contact, str) and isinstance(log, list)):
                continue
            kept = [r for entry in log if (r := Reaction.from_dict(entry)) is not None]
            if kept:
                self.reactions[contact] = kept[-PAIRING_REACTION_LOG:]

    def _judge(self, event: _ContactEvent, changed: list[str]) -> None:
        """Cast the quick votes of a change and the silent votes that go with them."""
        before = self.evidence(event.contact)
        for thermostat in sorted(event.quick):
            event.voted.add(thermostat)
            self._vote(event.contact, thermostat, quick=1)
        for thermostat in sorted(event.crowded - event.quick):
            # The thermostat of an earlier contact answers late as often as not, so
            # this answer is no more than a slow one.
            event.voted.add(thermostat)
            self._vote(event.contact, thermostat, slow=1)
        if event.quick:
            # Without a clear answer nobody can tell the silent thermostat that has
            # the contact from the ones that do not.
            for thermostat in sorted(event.alive - event.quick - event.crowded):
                event.silent.add(thermostat)
                self._vote(event.contact, thermostat, silent=1)
        if self.evidence(event.contact) != before:
            changed.append(event.contact)

    def _answer(
        self, thermostat: str, at: datetime, window_open: bool | None
    ) -> tuple[str, ...]:
        """Find the contact that a telegram of a thermostat answers and count it.

        `window_open` is the new window flag, or None for a telegram off the schedule.
        A flag follows only a contact that changed in the same direction.
        """
        fits = [
            event
            for event in self._events
            if (window_open is None or event.opened == window_open)
            and timedelta(0) <= at - event.at <= self.max_delay
        ]
        quick = [e for e in fits if at - e.at <= PAIRING_QUICK_REACTION]
        # The quick window decides first: an answer one second after a contact is that
        # contact's, also when another one changed a minute earlier.
        candidates = quick or fits
        if len({event.contact for event in candidates}) != 1:
            return ()
        event = max(candidates, key=lambda e: e.at)
        if thermostat not in event.reacted:
            event.reacted.add(thermostat)
            self._log(event, thermostat, at)
        if quick:
            if not event.ambiguous:
                crowded = any(
                    other.contact != event.contact
                    and (window_open is None or other.opened == window_open)
                    and timedelta(0) <= at - other.at <= self.max_delay
                    and not other.reacted - {thermostat}
                    for other in self._events
                )
                (event.crowded if crowded else event.quick).add(thermostat)
            return ()
        before = self.evidence(event.contact)
        if thermostat in event.silent:
            event.silent.discard(thermostat)
            self._vote(event.contact, thermostat, silent=-1)
        if window_open is not None and thermostat not in event.voted:
            event.voted.add(thermostat)
            self._vote(event.contact, thermostat, slow=1)
        return (event.contact,) if self.evidence(event.contact) != before else ()

    def _vote(
        self,
        contact: str,
        thermostat: str,
        *,
        quick: int = 0,
        slow: int = 0,
        silent: int = 0,
    ) -> None:
        """Add to the votes of a pair, and halve the votes of the contact if too many."""
        counts = self.votes.setdefault(contact, {})
        vote = counts.setdefault(thermostat, Votes())
        vote.quick += quick
        vote.slow += slow
        vote.silent = max(0, vote.silent + silent)
        if sum(v.positive for v in counts.values()) > PAIRING_POINT_LIMIT:
            for other in counts.values():
                other.halve()
        for key in [key for key, v in counts.items() if not v.to_dict()]:
            del counts[key]
        if not counts:
            del self.votes[contact]

    def _log(self, event: _ContactEvent, thermostat: str, at: datetime) -> None:
        """Keep the time that a thermostat took to answer a contact."""
        log = self.reactions.setdefault(event.contact, [])
        log.append(
            Reaction(
                thermostat,
                event.at,
                round((at - event.at).total_seconds(), 1),
                event.opened,
                event.ambiguous,
            )
        )
        del log[:-PAIRING_REACTION_LOG]


def _is_count(value: object) -> bool:
    """Return True for a stored count: an int that is not negative and no bool."""
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _merge(first: tuple[str, ...], second: tuple[str, ...]) -> tuple[str, ...]:
    """Return the contacts of both, each once and in order."""
    return tuple(dict.fromkeys((*first, *second)))
