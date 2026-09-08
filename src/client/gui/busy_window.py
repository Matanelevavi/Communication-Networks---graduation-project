"""The window shown while a request is on the wire."""
import threading
import tkinter as tk

from src.client.gui import theme
from src.client.gui.base import BaseWindow


class BusyWindow(BaseWindow):
    """
    Shown while a request is on the wire.

    Without it the interface simply disappears for a couple of seconds while
    the server talks to two external services, which reads as a freeze. The
    work runs on a thread and the window polls it, so Tk keeps redrawing.
    """

    size = "360x150"
    resizable = False

    def __init__(self, message: str, work) -> None:
        self.message = message
        self.work = work
        self.error = None
        self.finished = False
        self.title = "WeatherWear"
        super().__init__()

    def build(self) -> None:
        frame = tk.Frame(self.root, bg=theme.SURFACE)
        frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(frame, text=self.message, font=theme.body_bold(), fg=theme.INK,
                 bg=theme.SURFACE).pack(pady=(34, 6))
        self.dots = tk.Label(frame, text="", font=theme.heading(), fg=theme.BRAND,
                             bg=theme.SURFACE)
        self.dots.pack()

        self.root.after(60, self._start)
        self._animate(0)

    def _start(self) -> None:
        def run():
            try:
                self.result = self.work()
            except Exception as e:                       # surfaced by the caller
                self.error = e
            finally:
                self.finished = True

        threading.Thread(target=run, daemon=True).start()
        self._poll()

    def _poll(self) -> None:
        if self.finished:
            self.close()
        else:
            self.root.after(80, self._poll)

    def _animate(self, step: int) -> None:
        if self.finished:
            return
        self.dots.config(text="● " * (step % 4))
        self.root.after(320, self._animate, step + 1)

    def on_close(self) -> None:
        """The work cannot be cancelled, so closing early is ignored."""
