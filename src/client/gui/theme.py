"""
One place for the look of the interface.

Colours and fonts were repeated as literals in every widget; naming them here
means a change lands everywhere at once, and each value says what it is for
rather than what it looks like.

The palette is built around the subject: a cool slate ground with a deep sky
blue for anything the user acts on, and a warm accent reserved for temperature,
so heat reads as heat without a legend.
"""
import tkinter.font as tkfont

# ------------------------------------------------------------------ colours
INK = "#12212E"          # primary text, near black with a blue bias
INK_SOFT = "#5A6B7D"     # secondary text
INK_FAINT = "#8896A6"    # labels, captions

CANVAS = "#F1F5F9"       # the window behind the cards
SURFACE = "#FFFFFF"      # a card
SURFACE_SUNK = "#F7FAFC"  # an input inside a card
BORDER = "#DCE4ED"       # hairline

BRAND = "#1B6FA8"        # primary action, headers
BRAND_DARK = "#14547F"   # pressed
BRAND_TINT = "#E8F1F8"   # a wash of the brand, for chips

WARM = "#D9722A"         # temperature, sun
COOL = "#3E8FC4"         # rain, cold
SUCCESS = "#1F8A5F"
DANGER = "#B8443B"

ON_DARK = "#FFFFFF"

# -------------------------------------------------------------------- fonts
# Segoe UI is the Windows system face and reads far better than Tk's default;
# the fallbacks keep the layout sane on macOS and Linux.
_PREFERRED = ("Segoe UI", "Helvetica Neue", "Helvetica", "Arial")
_PREFERRED_MONO = ("Cascadia Mono", "Consolas", "Menlo", "Courier New")

_family = None
_mono_family = None


def _pick(candidates, fallback):
    """The first font actually installed, so nothing silently falls back."""
    try:
        available = {name.lower() for name in tkfont.families()}
    except Exception:
        return fallback
    for name in candidates:
        if name.lower() in available:
            return name
    return fallback


def family() -> str:
    """The UI face.  Resolved once, after a Tk root exists."""
    global _family
    if _family is None:
        _family = _pick(_PREFERRED, "Helvetica")
    return _family


def mono() -> str:
    global _mono_family
    if _mono_family is None:
        _mono_family = _pick(_PREFERRED_MONO, "Courier")
    return _mono_family


# A type scale, rather than a size picked per widget.
def display():   return (family(), 30, "bold")     # the temperature
def title():     return (family(), 19, "bold")     # window heading
def heading():   return (family(), 13, "bold")     # section heading
def body():      return (family(), 11)             # running text
def body_bold(): return (family(), 11, "bold")
def small():     return (family(), 10)
def label():     return (family(), 9, "bold")      # uppercase captions
def code():      return (mono(), 10)               # file contents
