import asyncio
import sys
import itertools
from typing import Dict
import shutil


class StatusBar:
    def __init__(self, name: str = "Task"):
        self.name = name
        self.status = None  # None = in progress, "passed" or "failed"
        self.message = ""  # Status message to display
        self.spinner_chars = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
        self.spinner_iter = itertools.cycle(self.spinner_chars)

    def render(self) -> str:
        # Get terminal width, fallback to 80 if not available
        terminal_width = shutil.get_terminal_size((80, 20)).columns
        # Get the status symbol part
        if self.status == "passed":
            status_symbol = "✓"
        elif self.status == "failed":
            status_symbol = "✗"
        else:
            status_symbol = next(self.spinner_iter)

        # Create the right-aligned part (status symbol and optional message)
        right_part = status_symbol
        if self.message:
            right_part = f"{status_symbol} - {self.message}"

        # Combine with name, padding the right part to align with terminal width
        name_part = f"{self.name}: "
        padding = terminal_width - len(name_part) - len(right_part)
        return f"\r{name_part}{' ' * max(0, padding)}{right_part}"


class StatusManager:
    def __init__(self):
        self.bars: Dict[str, StatusBar] = {}
        self.lock = asyncio.Lock()
        self.is_terminal = sys.stdout.isatty()
        self._running = True
        self._render_task = None
        self._last_render_lines = 0  # Will be 0 for first render

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

        # Move up by the number of lines we last rendered
        sys.stdout.write("\033[2K\033[A" * self._last_render_lines)
        sys.stdout.flush()

        # Count how many lines we're rendering
        self._last_render_lines = len(self.bars)
        bars = list(self.bars.values())
        bars = sorted(bars, key=lambda bar: (bar.status or "~", bar.name))
        for bar in bars:
            print(bar.render())

    async def mark_passed(self, name: str):
        async with self.lock:
            if name in self.bars:
                self.bars[name].status = "passed"
                await self.render()

    async def mark_failed(self, name: str):
        async with self.lock:
            if name in self.bars:
                self.bars[name].status = "failed"
                await self.render()

    async def stop(self):
        self._running = False
        if self._render_task:
            self._render_task.cancel()
            try:
                await self._render_task
            except asyncio.CancelledError:
                pass

    async def update_message(self, name: str, message: str):
        async with self.lock:
            if name in self.bars:
                self.bars[name].message = message
                await self.render()
