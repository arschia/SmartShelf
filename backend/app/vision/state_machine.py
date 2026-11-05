"""Slot State Machine with Clock Injection and Debounced Transitions.

States:
    PRESENT -> TRANSITION -> ABSENT
    ABSENT  -> TRANSITION -> PRESENT

Emits confirmed transitions exactly once when an observation persists continuously
for STABLE_SECONDS. Transient occlusions (e.g. passing hand) are debounced and ignored.
"""
import time
from typing import Callable, Optional, Tuple


class SlotState:
    PRESENT = "PRESENT"
    ABSENT = "ABSENT"
    TRANSITION = "TRANSITION"
    UNKNOWN = "UNKNOWN"
    # Aliases
    FULL = "FULL"
    EMPTY = "EMPTY"

    @classmethod
    def normalize(cls, state: Optional[str]) -> Optional[str]:
        if not state:
            return None
        s = str(state).strip().upper()
        if s in (cls.PRESENT, cls.FULL):
            return cls.PRESENT
        if s in (cls.ABSENT, cls.EMPTY):
            return cls.ABSENT
        if s == cls.TRANSITION:
            return cls.TRANSITION
        if s == cls.UNKNOWN:
            return cls.UNKNOWN
        return None


class ZoneStateMachine:
    """Manages temporal debouncing and state transitions for a single shelf slot."""

    def __init__(
        self,
        zone_id: int,
        initial_state: str = SlotState.UNKNOWN,
        stable_seconds: float = 1.5,
        clock: Optional[Callable[[], float]] = None,
    ):
        self.zone_id = zone_id
        self.confirmed_state: str = SlotState.normalize(initial_state) or SlotState.UNKNOWN
        self.candidate_state: Optional[str] = None
        self.transition_start_time: Optional[float] = None
        self.stable_seconds: float = stable_seconds
        self.clock: Callable[[], float] = clock or time.time
        self.transition_count: int = 0

    def update(
        self,
        observation: str,
        current_time: Optional[float] = None,
    ) -> Optional[Tuple[str, str]]:
        """Feed a raw observation into the state machine.

        Args:
            observation: 'PRESENT', 'ABSENT', 'FULL', 'EMPTY', or 'UNKNOWN'
            current_time: Optional injected timestamp (for testing).

        Returns:
            Tuple[str, str] representing ('FROM_STATE', 'TO_STATE') if a transition
            is confirmed on this tick; otherwise None.
        """
        t = current_time if current_time is not None else self.clock()
        norm_obs = SlotState.normalize(observation)

        # An indeterminate frame breaks the continuity requirement. Do not allow
        # an interrupted UNKNOWN interval to count toward a confirmed removal.
        if norm_obs not in (SlotState.PRESENT, SlotState.ABSENT):
            self.candidate_state = None
            self.transition_start_time = None
            return None

        # If observation matches confirmed state, any transient candidate is aborted
        if norm_obs == self.confirmed_state:
            if self.candidate_state is not None:
                self.candidate_state = None
                self.transition_start_time = None
            return None

        # Observation differs from confirmed state: evaluate candidate
        if self.candidate_state != norm_obs:
            # Begin new debouncing window
            self.candidate_state = norm_obs
            self.transition_start_time = t
            return None

        # Candidate is persisting: check if stable duration threshold is met
        start_time = self.transition_start_time
        elapsed = t - start_time if start_time is not None else 0.0
        if elapsed >= self.stable_seconds:
            from_state = self.confirmed_state
            to_state = self.candidate_state

            # Commit confirmed state and clear candidate
            self.confirmed_state = to_state
            self.candidate_state = None
            self.transition_start_time = None
            self.transition_count += 1

            # If recovering from UNKNOWN baseline (e.g. system cold-start / restart),
            # establish baseline state without firing false PICKED/RETURNED events.
            if from_state == SlotState.UNKNOWN:
                return None

            # Emit transition event exactly once
            return (from_state, to_state)

        return None

    def get_display_state(self) -> str:
        """Returns TRANSITION if an unconfirmed change is in progress, else confirmed state."""
        if self.candidate_state is not None:
            if self.confirmed_state == SlotState.UNKNOWN:
                return SlotState.UNKNOWN
            return SlotState.TRANSITION
        return self.confirmed_state

    def reset(self, state: str = SlotState.UNKNOWN):
        """Reset state machine to a specific confirmed state."""
        self.confirmed_state = SlotState.normalize(state) or SlotState.UNKNOWN
        self.candidate_state = None
        self.transition_start_time = None
