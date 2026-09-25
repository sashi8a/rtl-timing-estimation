"""Wall-clock deadline shared by all stages in a collection process."""

import os
import time


class DeadlineExceeded(TimeoutError):
    pass


def stage_timeout(limit=600):
    deadline = os.environ.get("RTL_TIMING_DEADLINE")
    remaining = float(deadline) - time.time() if deadline else limit
    if remaining <= 0:
        raise DeadlineExceeded("Collection wall-clock deadline reached")
    return min(limit, remaining)


def set_deadline(minutes):
    if minutes <= 0:
        raise ValueError("Deadline minutes must be positive")
    deadline = time.time() + minutes * 60
    if os.environ.get("RTL_TIMING_DEADLINE"):
        deadline = min(deadline, float(os.environ["RTL_TIMING_DEADLINE"]))
    os.environ["RTL_TIMING_DEADLINE"] = str(deadline)
    return deadline
