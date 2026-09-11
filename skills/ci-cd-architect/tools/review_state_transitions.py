"""Deterministic adversarial review for state-transition failure classes."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TransitionProbe:
    illegal_transition: bool = False
    stale_generation: bool = False
    unsafe_replay: bool = False
    timeout_after_effect_unreconciled: bool = False
    concurrent_writers_unserialized: bool = False
    tombstone_reused: bool = False
    lease_reused_across_generation: bool = False
    partial_effect_unrecovered: bool = False
    recovery_on_new_generation_unbound: bool = False


_FINDINGS = (
    ("illegal_transition", "STATE_GRAPH_VIOLATION"),
    ("stale_generation", "STALE_GENERATION_ACCEPTED"),
    ("unsafe_replay", "UNSAFE_REPLAY_ACCEPTED"),
    ("timeout_after_effect_unreconciled", "TIMEOUT_AFTER_EFFECT_UNRECONCILED"),
    ("concurrent_writers_unserialized", "CONCURRENT_WRITERS_UNSERIALIZED"),
    ("tombstone_reused", "TOMBSTONE_REUSE"),
    ("lease_reused_across_generation", "LEASE_REUSE_ACROSS_GENERATION"),
    ("partial_effect_unrecovered", "PARTIAL_EFFECT_UNRECOVERED"),
    ("recovery_on_new_generation_unbound", "RECOVERY_NEW_GENERATION_UNBOUND"),
)


def review_transition_probe(probe: TransitionProbe) -> tuple[str, ...]:
    """Return stable findings for adversarial transition conditions."""
    return tuple(code for field, code in _FINDINGS if getattr(probe, field))
