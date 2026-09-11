"""Routine = a sequence of steps that accomplishes one daily activity.

Each Routine receives a Driver + Matcher. Subclasses implement `run()` using
the helpers. The base class adds: structured logging, error capture, screenshot
on failure, and graceful skip-on-precondition-fail.
"""
from __future__ import annotations

import logging
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

import cv2

from .driver import Driver
from .matcher import TemplateMatcher

log = logging.getLogger(__name__)


class StepStatus(str, Enum):
    OK = "ok"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass
class Step:
    name: str
    status: StepStatus
    detail: str = ""


@dataclass
class RoutineResult:
    name: str
    started_at: datetime
    finished_at: datetime
    steps: list[Step] = field(default_factory=list)
    error: Optional[str] = None
    screenshot_path: Optional[str] = None

    @property
    def succeeded(self) -> bool:
        return self.error is None and not any(s.status == StepStatus.FAILED for s in self.steps)

    @property
    def duration_seconds(self) -> float:
        return (self.finished_at - self.started_at).total_seconds()


class Routine:
    """Base class. Subclass and override `run()`.

    Convention: when a step encounters a missing template, raise either
      - `RoutinePrecondition` (handled as 'skipped': feature not unlocked, etc.)
      - `RoutineError` (handled as 'failed': real problem, captured w/ screenshot)
    Anything else is rethrown.
    """

    name: str = "unnamed"
    failure_screenshot_dir: str = "logs"

    def __init__(self, driver: Driver, matcher: TemplateMatcher) -> None:
        self.driver = driver
        self.matcher = matcher
        self._current: Optional[RoutineResult] = None

    # -- subclass-facing helpers ------------------------------------------------

    def step(self, name: str) -> "_StepContext":
        """Use as `with self.step("collect_mail"): ...`."""
        return _StepContext(self, name)

    def tap_template(
        self,
        template: str,
        *,
        timeout: float = 10.0,
        required: bool = True,
        threshold: Optional[float] = None,
    ) -> bool:
        ok = self.matcher.tap_when_found(template, timeout=timeout, threshold=threshold)
        if not ok and required:
            raise RoutineError(f"Template '{template}' not found within {timeout:.1f}s")
        return ok

    def wait_for(self, template: str, *, timeout: float = 15.0):
        return self.matcher.wait_for(template, timeout=timeout)

    def is_visible(self, template: str) -> bool:
        return self.matcher.is_visible(template)

    # -- entry point -------------------------------------------------------------

    def execute(self) -> RoutineResult:
        result = RoutineResult(
            name=self.name,
            started_at=datetime.now(),
            finished_at=datetime.now(),
        )
        self._current = result
        log.info("=== Starting routine: %s ===", self.name)
        try:
            self.run()
        except RoutinePrecondition as e:
            log.info("Routine '%s' skipped: %s", self.name, e)
            result.steps.append(Step(name="precondition", status=StepStatus.SKIPPED, detail=str(e)))
        except RoutineError as e:
            log.error("Routine '%s' failed: %s", self.name, e)
            result.error = str(e)
            self._capture_failure_screenshot(result)
        except Exception as e:
            log.exception("Routine '%s' crashed: %s", self.name, e)
            result.error = f"Unexpected: {e}\n{traceback.format_exc()}"
            self._capture_failure_screenshot(result)
        finally:
            result.finished_at = datetime.now()
            self._current = None
            log.info(
                "=== Finished routine: %s | success=%s | %.1fs ===",
                self.name, result.succeeded, result.duration_seconds,
            )
        return result

    # -- abstract ---------------------------------------------------------------

    def run(self) -> None:
        raise NotImplementedError

    # -- internal ---------------------------------------------------------------

    def _capture_failure_screenshot(self, result: RoutineResult) -> None:
        try:
            screen = self.driver.screenshot()
            out = Path(self.failure_screenshot_dir)
            out.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = out / f"{self.name}_{ts}_failure.png"
            cv2.imwrite(str(path), screen)
            result.screenshot_path = str(path)
            log.info("Failure screenshot saved to %s", path)
        except Exception as e:
            log.warning("Could not capture failure screenshot: %s", e)


class RoutineError(Exception):
    """Real failure — captures a screenshot."""


class RoutinePrecondition(Exception):
    """Soft skip — routine is not applicable right now (feature locked, etc.)."""


class _StepContext:
    def __init__(self, routine: Routine, name: str) -> None:
        self.routine = routine
        self.name = name

    def __enter__(self):
        log.info("[step] %s", self.name)
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        result = self.routine._current
        if result is None:
            return False
        if exc is None:
            result.steps.append(Step(name=self.name, status=StepStatus.OK))
            return False
        if isinstance(exc, RoutinePrecondition):
            result.steps.append(Step(name=self.name, status=StepStatus.SKIPPED, detail=str(exc)))
            return False
        result.steps.append(Step(name=self.name, status=StepStatus.FAILED, detail=str(exc)))
        return False  # propagate
