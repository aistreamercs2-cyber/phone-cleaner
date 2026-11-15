"""Небольшие помощники Qt: фоновые задачи, тосты, стили."""

from __future__ import annotations

import inspect
from typing import Any, Callable

from PySide6.QtCore import QObject, QThread, Signal

from ..adb import Adb, AdbError
from ..parsers import human_size


class Task(QThread):
    """Выполняет функцию в фоне и отдаёт результат в GUI-поток."""

    succeeded = Signal(object)
    failed = Signal(str)
    progress = Signal(str, float)

    def __init__(self, func: Callable[..., Any], *args: Any, parent: QObject | None = None, **kwargs: Any) -> None:
        super().__init__(parent)
        self._func = func
        self._args = args
        self._kwargs = kwargs

    def emit_progress(self, message: str, value: float = -1) -> None:
        self.progress.emit(message, value)

    def _invoke(self) -> Any:
        """Передаём self, если функция принимает параметр task (для прогресса)."""
        try:
            params = inspect.signature(self._func).parameters
        except (TypeError, ValueError):
            params = {}
        if "task" in params:
            return self._func(*self._args, task=self, **self._kwargs)
        return self._func(*self._args, **self._kwargs)

    def run(self) -> None:  # noqa: D102
        try:
            result = self._invoke()
        except (AdbError, RuntimeError, OSError, ValueError) as exc:
            self.failed.emit(str(exc) or exc.__class__.__name__)
            return
        except Exception as exc:  # noqa: BLE001 - показываем пользователю любую ошибку
            self.failed.emit(f"{exc.__class__.__name__}: {exc}")
            return
        self.succeeded.emit(result)


def humanize(value: float) -> str:
    return human_size(value)


def run_task(owner: QObject, func: Callable[..., Any], on_done: Callable[[Any], None] | None = None,
             on_error: Callable[[str], None] | None = None,
             on_progress: Callable[[str, float], None] | None = None,
             *args: Any, **kwargs: Any) -> Task:
    """Запускает фоновую задачу, удерживая ссылку на объект у owner."""
    task = Task(func, *args, parent=owner, **kwargs)
    if on_done:
        task.succeeded.connect(on_done)
    if on_error:
        task.failed.connect(on_error)
    if on_progress:
        task.progress.connect(on_progress)
    keep = getattr(owner, "_running_tasks", None)
    if keep is None:
        keep = []
        setattr(owner, "_running_tasks", keep)
    keep.append(task)
    task.finished.connect(lambda: keep.remove(task) if task in keep else None)
    task.start()
    return task


def adb_of(serial: str | None) -> Adb:
    return Adb(serial=serial)
