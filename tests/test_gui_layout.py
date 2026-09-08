"""
Layout regressions.

A window taller than the screen hides its own submit button, and the user
simply cannot finish. That happened: the request form was given a fixed height
of 660 pixels, needed 779 on a display with system font scaling, and the
transport choice fell off the bottom where nothing could reach it.

Each test opens one window, measures it and closes it before opening the next.
Tkinter keeps a single default root per process, so several live roots at once
interfere with each other's timers and variables.

These tests need a display, so they skip where there is none.
"""
import tkinter as tk
import unittest
import unittest.mock

try:
    _probe = tk.Tk()
    SCREEN = (_probe.winfo_screenwidth(), _probe.winfo_screenheight())
    _probe.destroy()
    HAS_DISPLAY = True
except Exception:                                  # headless machine or CI
    SCREEN = (0, 0)
    HAS_DISPLAY = False

from src.client.gui.busy_window import BusyWindow
from src.client.gui.file_windows import ArchiveWindow, TextWindow
from src.client.gui.forecast_window import ForecastWindow
from src.client.gui.request_window import RequestWindow

CARD = {"kind": "forecast", "city": "Ariel", "min_temp": 19.9, "max_temp": 33.3,
        "current_temp": 22.6, "rain": "No rain expected",
        # the local advisor writes long paragraphs, so the layout must cope
        "advice": "Ariel is hot today, 19.9 to 33.3 degrees. " * 8,
        "source": "local", "cached": False}

LISTING = ("--- WEATHERWEAR FTP ARCHIVE ---\n"
           "- Ariel_forecast.json (Size: 0.8 KB)\n"
           "- Ariel_full_report.csv (Size: 4.1 KB)\n")


def buttons_in(widget) -> list:
    found = []
    for child in widget.winfo_children():
        if isinstance(child, tk.Button):
            found.append(child)
        found.extend(buttons_in(child))
    return found


def labelled(widget, text: str):
    """The first widget showing exactly this text, or None."""
    for child in widget.winfo_children():
        try:
            if child.cget("text") == text:
                return child
        except tk.TclError:
            pass
        found = labelled(child, text)
        if found is not None:
            return found
    return None


@unittest.skipUnless(HAS_DISPLAY, "needs a display")
class WindowTestCase(unittest.TestCase):
    """Opens one window, hands it to a check, and always closes it."""

    def inspect(self, make, check):
        window = make()
        try:
            window.root.update_idletasks()
            # a full update maps the window; without it every reported
            # position is relative to nothing and comes back negative
            window.root.update()
            return check(window)
        finally:
            try:
                window.root.destroy()
            except tk.TclError:
                pass                       # a check may have closed it already

    @staticmethod
    def size_of(window) -> tuple[int, int]:
        width, height = window.root.geometry().split("+")[0].split("x")
        return int(width), int(height)

    @staticmethod
    def held_open_busy_window() -> BusyWindow:
        """
        A progress window measured before its work begins.

        It closes itself the moment the work returns, so the start is called
        off instead: no thread runs, and nothing races the teardown.
        """
        window = BusyWindow("Working", lambda: None)
        window.root.after_cancel(window.start_job)
        return window

    def every_window(self) -> dict:
        return {
            "RequestWindow": RequestWindow,
            "ForecastWindow": lambda: ForecastWindow(CARD),
            "ArchiveWindow": lambda: ArchiveWindow(LISTING),
            "TextWindow": lambda: TextWindow("report.csv", "a,b\n1,2"),
            "BusyWindow": self.held_open_busy_window,
        }


class TestEveryWindowFits(WindowTestCase):

    def test_no_window_is_bigger_than_the_screen(self):
        for name, make in self.every_window().items():
            with self.subTest(window=name):
                width, height = self.inspect(make, self.size_of)
                self.assertLessEqual(width, SCREEN[0], name)
                self.assertLessEqual(height, SCREEN[1], name)

    def test_the_action_button_is_inside_the_window(self):
        """Pinning the footer to the bottom edge is what guarantees this."""
        def button_bottom_and_height(window):
            button = buttons_in(window.root)[-1]
            bottom = (button.winfo_rooty() - window.root.winfo_rooty()
                      + button.winfo_reqheight())
            return bottom, self.size_of(window)[1]

        for name, make in self.every_window().items():
            if name == "BusyWindow":
                continue                       # it has no button by design
            with self.subTest(window=name):
                bottom, height = self.inspect(make, button_bottom_and_height)
                self.assertLessEqual(bottom, height, f"{name}: the button is cut off")


class TestRequestForm(WindowTestCase):

    def test_the_transport_choice_is_visible_without_scrolling(self):
        """
        The reported bug: TCP could not be reached at all. The form has to fit,
        not merely be scrollable to.
        """
        def positions(window):
            return {
                "wanted": window.wanted_size()[1],
                "height": self.size_of(window)[1],
                "tops": {name: labelled(window.root, name).winfo_rooty()
                               - window.root.winfo_rooty()
                         for name in ("TCP", "RUDP")},
            }

        seen = self.inspect(RequestWindow, positions)

        self.assertLessEqual(seen["wanted"], seen["height"],
                             "the request form does not fit and has to scroll")
        for option, top in seen["tops"].items():
            self.assertGreaterEqual(top, 0, option)
            self.assertLess(top, seen["height"], f"{option} sits below the window")

    def test_both_transports_are_offered(self):
        def toggle(window):
            first = window.protocol_choice.get()
            window.protocol_choice.set("TCP")
            return first, window.protocol_choice.get()

        self.assertEqual(self.inspect(RequestWindow, toggle), ("RUDP", "TCP"))

    def test_submitting_collects_every_field(self):
        def submit(window):
            window.protocol_choice.set("TCP")
            window.submit()
            return window.result

        action, city, profiles, protocol = self.inspect(RequestWindow, submit)

        self.assertEqual(action, "FORECAST")
        self.assertEqual(city, "Ariel")
        self.assertEqual(protocol, "TCP")
        self.assertTrue(profiles)

    def test_a_forecast_without_a_city_is_refused(self):
        def submit_empty(window):
            window.city_entry.delete(0, tk.END)
            with unittest.mock.patch(
                    "src.client.gui.request_window.messagebox.showwarning") as warned:
                window.submit()
            return warned.call_count, window.result

        calls, result = self.inspect(RequestWindow, submit_empty)

        self.assertEqual(calls, 1)
        self.assertIsNone(result)


class TestForecastCard(WindowTestCase):

    def shows(self, card: dict, *texts) -> list:
        return self.inspect(lambda: ForecastWindow(card),
                            lambda w: [labelled(w.root, t) is not None for t in texts])

    def test_it_shows_the_numbers_and_the_advice(self):
        self.assertEqual(self.shows(CARD, "22.6°", "19.9°", "33.3°", "What to wear"),
                         [True] * 4)

    def test_the_advisor_is_named(self):
        self.assertEqual(self.shows(CARD, "local advisor"), [True])
        self.assertEqual(self.shows({**CARD, "source": "ai"}, "AI advisor"), [True])

    def test_a_cached_answer_says_so(self):
        self.assertEqual(self.shows({**CARD, "cached": True},
                                    "local advisor - cached"), [True])

    def test_a_missing_temperature_does_not_break_the_card(self):
        self.assertEqual(self.shows({**CARD, "current_temp": None}, "--"), [True])


if __name__ == "__main__":
    unittest.main()
