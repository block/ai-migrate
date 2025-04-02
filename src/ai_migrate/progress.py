import asyncio
import sys
import itertools
from enum import StrEnum
from typing import Dict
import shutil


class Status(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    RUNNING = "running"
    WAITING = "waiting"


class StatusLog:
    def __init__(self, line_limit):
        self.line_limit = line_limit
        self.lines = [""] * line_limit
        self.header = ""

    def write(self, s: str):
        self.lines.extend(s.removesuffix("\n").splitlines())
        self.lines = self.lines[-self.line_limit :]

    def flush(self):
        pass

    def close(self):
        pass

    def getvalue(self):
        body = "\n".join(self.lines)
        return f"{self.header}\n{body}" if self.header else body


class StatusBar:
    def __init__(self, name: str = "Task"):
        self.name = name
        self.status = Status.WAITING
        self.message = ""
        self.spinner_chars = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
        self.spinner_iter = itertools.cycle(self.spinner_chars)
        self.logger = StatusLog(line_limit=3)

    def render(self) -> str:
        terminal_width = shutil.get_terminal_size((80, 20)).columns

        if self.status == Status.PASSED:
            status_symbol = "✓"
        elif self.status == Status.FAILED:
            status_symbol = "✗"
        else:
            status_symbol = next(self.spinner_iter)

        right_part = status_symbol
        if self.message:
            right_part = f"{status_symbol} - {self.message}"

        name_part = f"{self.name}: "
        padding = terminal_width - len(name_part) - len(right_part)
        logs = (
            [
                f"    {line}"[:terminal_width]
                for line in self.logger.getvalue().splitlines()
            ]
            if self.status == Status.RUNNING
            else []
        )
        return f"\r{name_part}{' ' * max(0, padding)}{right_part}" + (
            f"\n{'\n'.join(logs)}" if logs else ""
        )

    def get_logger(self, header: str):
        self.logger.header = header
        return self.logger


class StatusManager:
    def __init__(self):
        self.bars: Dict[str, StatusBar] = {}
        self.lock = asyncio.Lock()
        self.is_terminal = sys.stdout.isatty()
        self._running = True
        self._render_task = None
        self._last_render_lines = 0

    async def add_status(self, name: str) -> StatusBar:
        async with self.lock:
            bar = StatusBar(name)
            self.bars[name] = bar
            if self._render_task is None:
                self._render_task = asyncio.create_task(self._render_loop())
            await self.render()
            return bar

    async def _render_loop(self):
        while self._running:
            await self.render()
            await asyncio.sleep(0.1)

    async def render(self):
        if not self.is_terminal:
            return

        sys.stdout.write("\033[2K\033[A" * self._last_render_lines)
        sys.stdout.flush()

        self._last_render_lines = 0
        bars = list(self.bars.values())
        bars = itertools.groupby(
            sorted(bars, key=lambda bar: (bar.status, bar.name)),
            key=lambda bar: bar.status,
        )
        for status, bars in bars:
            bars = [*bars]
            if status == Status.WAITING:
                print(f"{len(bars)} more in queue...")
                self._last_render_lines += 1
            else:
                for bar in bars:
                    rendered = bar.render()
                    print(rendered)
                    self._last_render_lines += len(rendered.splitlines())

    async def mark_with_status(self, name: str, status: Status):
        async with self.lock:
            if name in self.bars:
                self.bars[name].status = status
                await self.render()

    async def set_message(self, name: str, message: str):
        async with self.lock:
            if name in self.bars:
                self.bars[name].message = message
                await self.render()

    async def stop(self):
        self._running = False
        if self._render_task:
            self._render_task.cancel()
            try:
                await self._render_task
            except asyncio.CancelledError:
                pass

    def get_logger(self, name: str, header: str = ""):
        return self.bars[name].get_logger(header=header)
