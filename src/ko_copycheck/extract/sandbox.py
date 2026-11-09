"""Run extraction in one child process that is killed on timeout and then replaced.

A ``ProcessPoolExecutor`` future timeout does not stop the worker, so a file that hangs
keeps eating a CPU. Here the parent owns one spawned ``Process`` and a ``Pipe``; on a
timeout it calls ``Process.kill()`` and starts a fresh worker for the next file.
"""
from __future__ import annotations

import importlib
import multiprocessing as mp
import os
import sys
import time
from dataclasses import dataclass
from multiprocessing.connection import Connection
from typing import Any

from .formats import ExtractError, Limits

DEFAULT_HANDLER = "ko_copycheck.extract.formats:extract_file"


@dataclass
class ExtractResult:
    """Outcome for one file: ``text`` on success, otherwise ``error`` (``code: message``)."""

    path: str
    text: str | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def _resolve(handler: str) -> Any:
    module, _, func = handler.partition(":")
    return getattr(importlib.import_module(module), func)


def _worker_main(conn: Connection, handler: str, limits: Limits) -> None:
    """Child process loop: receive a path, send back ``("ok", text)`` or ``("err", code, msg)``."""
    if sys.platform.startswith("linux"):
        try:  # memory cap only works on Linux; macOS rejects RLIMIT_AS
            import resource

            cap = 2 * 1024**3
            resource.setrlimit(resource.RLIMIT_AS, (cap, cap))
        except (ImportError, ValueError, OSError):
            pass
    func = _resolve(handler)
    conn.send(("ready",))
    while True:
        try:
            msg = conn.recv()
        except EOFError:
            return
        if msg is None:
            return
        try:
            conn.send(("ok", func(msg, limits)))
        except ExtractError as exc:
            conn.send(("err", exc.code, str(exc)))
        except MemoryError:
            conn.send(("err", "too_large", "out of memory while reading"))
        except Exception as exc:  # an unknown reader failure must not kill the run
            conn.send(("err", "error", f"{type(exc).__name__}: {exc}"))


class SandboxedExtractor:
    """Extract files one at a time in a killable child process.

    Use as a context manager. ``retired_exitcodes`` lists the exit codes of workers that
    were killed (negative on POSIX) or recycled.
    """

    def __init__(
        self,
        timeout: float = 60.0,
        recycle_after: int = 50,
        limits: Limits | None = None,
        handler: str = DEFAULT_HANDLER,
        start_timeout: float = 60.0,
        max_rss_bytes: int = 2 * 1024**3,
    ) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be > 0 seconds; try --timeout 60")
        self.timeout = timeout
        self.recycle_after = recycle_after
        self.limits = limits or Limits()
        self.handler = handler
        self.start_timeout = start_timeout
        self.max_rss_bytes = max_rss_bytes
        self.retired_exitcodes: list[int | None] = []
        self._ctx = mp.get_context("spawn")
        self._proc: Any = None
        self._conn: Connection | None = None
        self._handled = 0

    def __enter__(self) -> "SandboxedExtractor":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- worker lifecycle -------------------------------------------------
    def _start(self) -> bool:
        parent, child = self._ctx.Pipe()
        proc = self._ctx.Process(target=_worker_main, args=(child, self.handler, self.limits), daemon=True)
        proc.start()
        child.close()
        self._proc, self._conn, self._handled = proc, parent, 0
        if parent.poll(self.start_timeout):
            try:
                if parent.recv() == ("ready",):
                    return True
            except EOFError:
                pass
        self._kill()
        return False

    def _kill(self) -> None:
        if self._proc is None:
            return
        if self._proc.is_alive():
            self._proc.kill()
        self._proc.join()
        self.retired_exitcodes.append(self._proc.exitcode)
        if self._conn is not None:
            self._conn.close()
        self._proc = self._conn = None

    def _retire_gracefully(self) -> None:
        if self._proc is None or self._conn is None:
            return
        try:
            self._conn.send(None)
        except (BrokenPipeError, OSError):
            pass
        self._proc.join(5)
        self._kill()

    def close(self) -> None:
        """Stop the worker (always call this, or use ``with``)."""
        self._retire_gracefully()

    # -- extraction -------------------------------------------------------
    def extract(self, path: str | os.PathLike[str]) -> ExtractResult:
        """Extract one file; never raises for a bad file, returns an error result instead."""
        path = str(path)
        if self._proc is None and not self._start():
            return ExtractResult(path, error="worker_failed: could not start the extraction worker")
        assert self._conn is not None and self._proc is not None
        try:
            self._conn.send(path)
        except (BrokenPipeError, OSError):
            self._kill()
            return ExtractResult(path, error="worker_crashed: worker was gone; retry")
        deadline = time.monotonic() + self.timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self._kill()
                return ExtractResult(path, error=f"timeout: no result after {self.timeout:g}s (worker killed)")
            if self._conn.poll(min(0.5, remaining)):
                break
            if self._rss_exceeded():
                self._kill()
                return ExtractResult(path, error="too_large: worker memory exceeded the limit (killed)")
            if not self._proc.is_alive() and not self._conn.poll(0):
                self._kill()
                return ExtractResult(path, error="worker_crashed: extraction worker exited unexpectedly")
        try:
            msg = self._conn.recv()
        except EOFError:
            self._kill()
            return ExtractResult(path, error="worker_crashed: extraction worker exited unexpectedly")
        self._handled += 1
        if msg[0] == "ok":
            result = ExtractResult(path, text=msg[1])
        else:
            result = ExtractResult(path, error=f"{msg[1]}: {msg[2]}")
        if self._handled >= self.recycle_after:
            self._retire_gracefully()  # fresh worker for the next file bounds memory growth
        return result

    def _rss_exceeded(self) -> bool:
        """Linux only: compare the worker's resident memory with the cap."""
        if not sys.platform.startswith("linux") or self._proc is None:
            return False
        try:
            with open(f"/proc/{self._proc.pid}/status", encoding="ascii") as fh:
                for line in fh:
                    if line.startswith("VmRSS:"):
                        return int(line.split()[1]) * 1024 > self.max_rss_bytes
        except OSError:
            return False
        return False
