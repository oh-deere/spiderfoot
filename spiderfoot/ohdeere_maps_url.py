"""Format MapLibre hash deep-links into the OhDeere maps web UI.

The maps web UI runs MapLibre with ``hash: true``, so the URL hash is
the standard MapLibre ``#zoom/lat/lon`` format. Module-level defaults
target the public host; consumers pass ``base_url`` from a module opt
to support self-hosters and local dev.

Pure formatter — no I/O, no SpiderFoot imports.
"""

DEFAULT_BASE_URL = "https://maps.ohdeere.se"
DEFAULT_ZOOM = 15


def maps_deeplink(
    lat: float,
    lon: float,
    *,
    base_url: str = DEFAULT_BASE_URL,
    zoom: int = DEFAULT_ZOOM,
) -> str:
    """Return a MapLibre hash URL into the OhDeere maps UI.

    Args:
        lat: Latitude in decimal degrees.
        lon: Longitude in decimal degrees.
        base_url: Base URL of the maps web UI. Trailing slash tolerated.
        zoom: MapLibre zoom level (0-20). Defaults to 15 (street-level).

    Returns:
        The deep-link URL string for the maps web UI.
    """
    base = base_url.rstrip("/")
    return f"{base}/#{zoom}/{lat}/{lon}"
