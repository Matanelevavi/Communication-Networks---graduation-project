"""
Turning what the user typed, and what the server sent, into plain data.

Kept away from the widgets so it can be tested without a display.
"""

SIZE_MARKER = " (Size:"


def degrees(value) -> str:
    if value is None:
        return "--"
    return f"{value:g}°"


def first_hour(rain_summary: str) -> str:
    """The server sends "07:00 (40%), 08:00 (55%)"; the tile shows the first."""
    return f"from {rain_summary.split(' ')[0]}"


def parse_profiles(raw: str) -> list[dict]:
    """Read the free text box as one profile per comma separated line."""
    profiles = []
    for line in raw.strip().split("\n"):
        if not line.strip():
            continue
        parts = [part.strip() for part in line.split(",")]
        if len(parts) >= 3:
            profiles.append({
                "name": parts[0],
                "gender": parts[1],
                "age_category": parts[2],
                "notes": parts[3] if len(parts) > 3 else "",
            })
    return profiles


def parse_listing(listing: str) -> list[tuple[str, str]]:
    """
    Read the file names and sizes out of the archive listing.

    Each row is ``- <name> (Size: N KB)``. Splitting on the size marker rather
    than on whitespace keeps names that contain a space intact.
    """
    entries = []
    for line in listing.split("\n"):
        if not line.startswith("- "):
            continue
        name, _, size = line[2:].partition(SIZE_MARKER)
        name = name.strip()
        if name:
            entries.append((name, size.rstrip(")").strip()))
    return entries


def readable(content) -> str:
    """Text widgets cannot display bytes, so describe a binary answer instead."""
    if isinstance(content, (bytes, bytearray)):
        return f"Binary file, {len(content)} bytes.\nIt cannot be displayed as text."
    return content
