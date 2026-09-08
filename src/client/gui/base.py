"""
The window every screen is built on.

Each screen used to repeat the same setup and smuggle its answer out through a
mutable dictionary captured by a closure. A class holds that answer as an
attribute instead, which is both shorter and easier to follow.

Two rules here keep the screens usable on a small or scaled display, which a
fixed pixel size cannot do:

* the footer is packed against the bottom edge *before* the body, so the button
  that closes or submits the window can never be pushed off screen;
* the body scrolls when it is taller than the space available, and the window
  sizes itself to its content up to what the screen can show.
"""
import tkinter as tk

from src.client.gui import theme

SCREEN_MARGIN_X = 60      # leave room for the window frame
SCREEN_MARGIN_Y = 110     # and for the title bar and the taskbar
SCROLLBAR_ALLOWANCE = 26  # width the scrollbar takes when it appears
BODY_PADDING = 20         # the body's own top and bottom padding


class BaseWindow:
    """A modal Tk window that runs until it is closed and returns one result."""

    title = "WeatherWear"
    min_width = 420
    min_height = 320
    resizable = True

    def __init__(self) -> None:
        self.result = None
        self._header = None
        self._footer = None
        self._content = None      # the frame inside a scrollable body, if any

        self.root = tk.Tk()
        self.root.title(self.title)
        self.root.configure(bg=theme.CANVAS)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.build()
        self.fit_to_screen()

    def build(self) -> None:
        """Lay out the widgets.  Every screen implements this."""
        raise NotImplementedError

    # -------------------------------------------------------------- sizing
    def fit_to_screen(self) -> None:
        """
        Size the window to what it actually needs, capped by the screen.

        A hardcoded size is wrong on any display but the one it was written
        for: system font scaling alone changes the height a layout needs by a
        third.
        """
        self.root.update_idletasks()

        available_w = self.root.winfo_screenwidth() - SCREEN_MARGIN_X
        available_h = self.root.winfo_screenheight() - SCREEN_MARGIN_Y

        wanted_w, wanted_h = self.wanted_size()
        width = max(self.min_width, min(wanted_w, available_w))
        height = max(self.min_height, min(wanted_h, available_h))

        x = max(0, (self.root.winfo_screenwidth() - width) // 2)
        y = max(0, (self.root.winfo_screenheight() - height) // 2 - 20)
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        self.root.minsize(self.min_width, min(self.min_height, available_h))
        self.root.resizable(self.resizable, self.resizable)

    def wanted_size(self) -> tuple[int, int]:
        """
        How much room the layout would like.

        A scrolling body sits inside a Canvas, and a Canvas reports its own
        default size rather than its content's, so the window would collapse to
        its minimum. Measuring the content frame and adding the fixed header
        and footer gives the honest number.
        """
        if self._content is None:
            return self.root.winfo_reqwidth(), self.root.winfo_reqheight()

        chrome = sum(part.winfo_reqheight()
                     for part in (self._header, self._footer) if part is not None)
        return (self._content.winfo_reqwidth() + SCROLLBAR_ALLOWANCE,
                self._content.winfo_reqheight() + chrome + BODY_PADDING)

    # -------------------------------------------------------------- pieces
    def add_header(self, text: str, subtitle: str = "") -> tk.Frame:
        """The coloured band across the top of a window."""
        header = tk.Frame(self.root, bg=theme.BRAND)
        header.pack(fill=tk.X, side=tk.TOP)
        self._header = header

        inner = tk.Frame(header, bg=theme.BRAND)
        inner.pack(fill=tk.X, padx=22, pady=(14, 12))

        tk.Label(inner, text=text, font=theme.title(),
                 fg=theme.ON_DARK, bg=theme.BRAND, anchor="w").pack(fill=tk.X)
        if subtitle:
            tk.Label(inner, text=subtitle, font=theme.small(),
                     fg=theme.BRAND_TINT, bg=theme.BRAND, anchor="w").pack(
                fill=tk.X, pady=(2, 0))
        return header

    def add_footer(self, text: str, command) -> tk.Frame:
        """
        The action bar, pinned to the bottom edge.

        Packed before the body so the body gives up space first: the button
        stays reachable however little room is left.
        """
        footer = tk.Frame(self.root, bg=theme.CANVAS)
        footer.pack(fill=tk.X, side=tk.BOTTOM, padx=18, pady=(8, 14))
        self.primary_button(footer, text, command).pack(fill=tk.X)
        self._footer = footer
        return footer

    def scrollable_body(self) -> tk.Frame:
        """
        A body that scrolls only when its content does not fit.

        Returns the frame to put the content in; the scrollbar appears and
        disappears on its own as the window is resized.
        """
        container = tk.Frame(self.root, bg=theme.CANVAS)
        container.pack(fill=tk.BOTH, expand=True, side=tk.TOP)

        canvas = tk.Canvas(container, bg=theme.CANVAS, highlightthickness=0, bd=0)
        bar = tk.Scrollbar(container, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=bar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        inner = tk.Frame(canvas, bg=theme.CANVAS)
        window = canvas.create_window((0, 0), window=inner, anchor="nw")
        self._content = inner

        def resized(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfigure(window, width=canvas.winfo_width())
            overflows = inner.winfo_reqheight() > canvas.winfo_height()
            if overflows and not bar.winfo_ismapped():
                bar.pack(side=tk.RIGHT, fill=tk.Y)
            elif not overflows and bar.winfo_ismapped():
                bar.pack_forget()

        inner.bind("<Configure>", resized)
        canvas.bind("<Configure>", resized)
        self._bind_wheel(canvas, inner)
        return inner

    def _bind_wheel(self, canvas, inner) -> None:
        """Scroll with the wheel, but only while there is something to scroll."""
        def on_wheel(event):
            if inner.winfo_reqheight() > canvas.winfo_height():
                canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")

        # bind_all is scoped to this window's own interpreter, since every
        # screen creates its own Tk root
        self.root.bind_all("<MouseWheel>", on_wheel)

    @staticmethod
    def card(parent, **pack) -> tk.Frame:
        """A white panel with a hairline border."""
        frame = tk.Frame(parent, bg=theme.SURFACE,
                         highlightbackground=theme.BORDER, highlightthickness=1)
        frame.pack(**pack)
        return frame

    @staticmethod
    def caption(parent, text: str, **pack) -> tk.Label:
        """A small uppercase label above a control."""
        widget = tk.Label(parent, text=text.upper(), font=theme.label(),
                          fg=theme.INK_FAINT, bg=parent["bg"], anchor="w")
        widget.pack(**pack)
        return widget

    def primary_button(self, parent, text: str, command) -> tk.Button:
        return self._button(parent, text, command, theme.BRAND, theme.BRAND_DARK,
                            theme.ON_DARK)

    @staticmethod
    def _button(parent, text, command, background, hover, foreground):
        button = tk.Button(
            parent, text=text, command=command, font=theme.body_bold(),
            bg=background, fg=foreground, activebackground=hover,
            activeforeground=foreground, relief=tk.FLAT, bd=0,
            padx=18, pady=8, cursor="hand2", highlightthickness=0)
        button.bind("<Enter>", lambda _e: button.configure(bg=hover))
        button.bind("<Leave>", lambda _e: button.configure(bg=background))
        return button

    # ------------------------------------------------------------ lifecycle
    def on_close(self) -> None:
        """Closing the window without choosing leaves the result unset."""
        self.result = None
        self.close()

    def close(self) -> None:
        try:
            self.root.unbind_all("<MouseWheel>")
        except tk.TclError:
            pass
        self.root.destroy()

    def show(self):
        """Display the window and block until it closes, then return its result."""
        self.root.mainloop()
        return self.result
