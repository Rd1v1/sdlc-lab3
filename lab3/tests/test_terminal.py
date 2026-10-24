import asyncio
import io
import time
import unittest

from prompt_toolkit.data_structures import Size
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

from lab3.src.models import CrackConfig, WorkerProgress
from lab3.src.progress import CliProgress
from lab3.src.terminal import WorkerTerminal


class ResizableOutput(DummyOutput):
    size = Size(rows=24, columns=80)

    def get_size(self):
        return self.size


class TerminalLayoutTests(unittest.IsolatedAsyncioTestCase):
    async def wait_until(self, condition):
        async def wait():
            while not condition():
                await asyncio.sleep(0.01)
        await asyncio.wait_for(wait(), 5)

    async def test_any_worker_count_scrolling_updates_and_resize(self):
        for count in (1, 2, 32, 128, 4096):
            with self.subTest(workers=count), create_pipe_input() as source:
                output = ResizableOutput()
                progress = CliProgress(CrackConfig(workers=count, gpu=True), stream=io.StringIO())
                terminal = WorkerTerminal(progress, lambda callback: None, input=source, output=output)
                app = terminal.application
                task = asyncio.create_task(app.run_async(pre_run=terminal.update, handle_sigint=False, set_exception_handler=False))
                try:
                    await self.wait_until(lambda: terminal.table.window.render_info is not None)
                    self.assertEqual(terminal.table.document.line_count, count)
                    source.send_text('\x1b[1;5F')  # Ctrl+End
                    await self.wait_until(lambda: terminal.table.document.cursor_position_row == count - 1)
                    await self.wait_until(lambda: count - 1 in terminal.table.window.render_info.displayed_lines)
                    password = 'long password ' * 30
                    rows = [WorkerProgress(index + 1, f'candidate-{index}', 10, 'running') for index in range(count)]
                    rows[-1] = WorkerProgress(count, password, 11, 'found')
                    progress(tuple(rows))
                    terminal.update()
                    app.invalidate()
                    self.assertEqual(terminal.table.document.line_count, count)
                    self.assertEqual(terminal.table.document.cursor_position_row, count - 1)
                    self.assertIn(password, terminal.table.text)
                    source.send_text('\x1b[1;5F')
                    await self.wait_until(lambda: terminal.table.window.horizontal_scroll > 0)
                    for height, width in ((8, 40), (50, 140), (24, 80)):
                        output.size = Size(rows=height, columns=width)
                        app.invalidate()
                        await self.wait_until(lambda: terminal.table.window.render_info.window_height == height - 3)
                        self.assertIn(count - 1, terminal.table.window.render_info.displayed_lines)
                    source.send_text('\x1b[1;5H')  # Ctrl+Home
                    await self.wait_until(lambda: terminal.table.document.cursor_position_row == 0)
                    await self.wait_until(lambda: 0 in terminal.table.window.render_info.displayed_lines)
                    if count > 1:
                        source.send_text('\x1b[6~')  # PageDown
                        await self.wait_until(lambda: terminal.table.document.cursor_position_row > 0)
                finally:
                    if app.is_running:
                        app.exit()
                    await asyncio.wait_for(task, 5)


class TerminalSearchTests(unittest.TestCase):
    def test_ctrl_c_cancels_search_and_joins_thread(self):
        progress = CliProgress(CrackConfig(workers=32, gpu=True), stream=io.StringIO())
        def search(callback):
            for checked in range(1000):
                callback(tuple(WorkerProgress(index + 1, 'candidate', checked, 'running') for index in range(32)))
                time.sleep(0.005)
        with create_pipe_input() as source:
            terminal = WorkerTerminal(progress, search, input=source, output=DummyOutput())
            source.send_text('\x03')
            with self.assertRaises(KeyboardInterrupt):
                terminal.run()
        self.assertTrue(progress.cancelled.is_set())
        self.assertFalse(terminal.worker.is_alive())

    def test_search_error_reaches_cli_and_joins_thread(self):
        def search(callback):
            raise ValueError('search failed')
        with create_pipe_input() as source:
            progress = CliProgress(CrackConfig(), stream=io.StringIO())
            terminal = WorkerTerminal(progress, search, input=source, output=DummyOutput())
            with self.assertRaisesRegex(ValueError, 'search failed'):
                terminal.run()
        self.assertFalse(terminal.worker.is_alive())

    def test_redirected_output_is_printed_once(self):
        stream = io.StringIO()
        progress = CliProgress(CrackConfig(workers=32, gpu=True), stream=stream)
        def search(callback):
            for checked in range(20):
                callback(tuple(WorkerProgress(index + 1, 'candidate', checked, 'running') for index in range(32)))
            callback(tuple(WorkerProgress(index + 1, 'candidate', 20, 'done') for index in range(32)))
            return 'result'
        self.assertEqual(progress.run(search), 'result')
        output = stream.getvalue()
        self.assertEqual(output.count('WORKER  STATE'), 1)
        self.assertEqual(len(output.splitlines()), 34)
        self.assertNotIn('\x1b', output)
