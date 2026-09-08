"""
One place for the look of the interface.

Colours and fonts were repeated as literals in every widget; naming them here
means a change lands everywhere at once, and each value says what it is for
rather than what it looks like.
"""

# ------------------------------------------------------------------ colours
BACKGROUND = "#eef2f5"
SURFACE = "#ffffff"
FIELD = "#f8f9fa"

HEADER_DARK = "#34495e"       # the dashboard header
HEADER_BLUE = "#2980b9"       # the result header
TEXT = "#2c3e50"
TEXT_ON_DARK = "#ffffff"

ACCENT_GREEN = "#27ae60"      # primary action
ACCENT_MINT = "#2ecc71"       # secondary action
ACCENT_RED = "#e74c3c"        # dismiss
SELECTION = "#3498db"

# -------------------------------------------------------------------- fonts
FAMILY = "Helvetica"
MONO_FAMILY = "Consolas"

TITLE = (FAMILY, 16, "bold")
BIG_TITLE = (FAMILY, 20, "bold")
SECTION = (FAMILY, 11, "bold")
BODY = (FAMILY, 10)
LIST_ITEM = (FAMILY, 12)
BUTTON = (FAMILY, 12, "bold")
CONTENT = (MONO_FAMILY, 11)
