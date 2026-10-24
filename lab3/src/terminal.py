"""Прокручиваемая таблица; размером окна и перерисовкой управляет prompt_toolkit."""
import asyncio
from contextlib import contextmanager
import os
import threading

from prompt_toolkit import Application
from prompt_toolkit.document import Document
from prompt_toolkit.data_structures import Size
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import HSplit, Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.output.defaults import create_output
from prompt_toolkit.output.vt100 import Vt100_Output
from prompt_toolkit.widgets import TextArea


@contextmanager
def terminal_output(stream):
    if os.name != 'nt':
        yield create_output(stdout=stream)
        return
    import ctypes
    import msvcrt
    kernel = ctypes.windll.kernel32
    handle = ctypes.c_void_p(msvcrt.get_osfhandle(stream.fileno()))
    mode = ctypes.c_ulong()
    if not kernel.GetConsoleMode(handle, ctypes.byref(mode)) or not kernel.SetConsoleMode(handle, mode.value | 4):
        raise RuntimeError('Терминал не поддерживает ANSI; используйте --no-progress')
    def size():
        columns, rows = os.get_terminal_size(stream.fileno())
        return Size(rows=rows, columns=columns)
    try:
        # Вывод привязан к stderr, независимо от перенаправления stdout с JSON.
        yield Vt100_Output(stream, size, enable_cpr=False)
    finally:
        kernel.SetConsoleMode(handle, mode.value)


class WorkerTerminal:
    def __init__(self, progress, search, *, input=None, output):
        self.progress = progress
        self.search = search
        self.finished = threading.Event()
        self.result = None
        self.error = None
        self.previous = None
        self.summary = FormattedTextControl(progress.summary)
        self.header = FormattedTextControl('')
        self.table = TextArea(read_only=True, scrollbar=True, wrap_lines=False)
        keys = KeyBindings()

        @keys.add('c-c', eager=True)
        def cancel(event):
            self.progress.cancelled.set()

        layout = HSplit([Window(self.summary, height=1),
                         Window(self.header, height=1, get_horizontal_scroll=lambda window: self.table.window.horizontal_scroll), self.table,
                         Window(FormattedTextControl('Arrows / PgUp PgDn: scroll | Ctrl+Home/End: first/last | Ctrl+C: stop'), height=1)])
        self.application = Application(layout=Layout(layout, focused_element=self.table), key_bindings=keys,
                                       full_screen=True, mouse_support=True, input=input,
                                       output=output)
        self.worker = threading.Thread(target=self.execute, name='lab3-search')

    def update(self):
        if self.previous == self.progress.rows:
            return
        self.previous = self.progress.rows
        header, body = self.progress.table()
        self.header.text = header
        # Сохраняем выбранную строку и колонку при смене кандидатов.
        old = self.table.document
        document = Document(body)
        position = document.translate_row_col_to_index(old.cursor_position_row, old.cursor_position_col)
        self.table.buffer.set_document(Document(body, position), bypass_readonly=True)

    def execute(self):
        try:
            self.result = self.search(self.progress)
        except BaseException as error:
            # Ошибка и отмена передаются из потока поиска в вызывающий CLI.
            self.error = error
        finally:
            self.finished.set()

    async def refresh(self):
        while not self.finished.is_set():
            self.update()
            self.application.invalidate()
            await asyncio.sleep(0.1)
        self.update()
        self.application.exit()

    def start(self):
        self.update()
        self.worker.start()
        self.application.create_background_task(self.refresh())

    def run(self):
        try:
            self.application.run(pre_run=self.start, handle_sigint=False, set_exception_handler=False)
        finally:
            self.progress.cancelled.set()
            if self.worker.ident is not None:
                self.worker.join()
        if self.error is not None:
            raise self.error
        return self.result
