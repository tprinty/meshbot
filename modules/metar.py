import logging

import requests

logger = logging.getLogger(__name__)


class Metar:
    """Fetch the latest METAR observation for an ICAO station."""

    URL = "https://aviationweather.gov/api/data/metar"

    def __init__(self, station):
        self.station = station.strip().upper()

    def get_metar(self):
        """Return the raw METAR string, or a failure string."""
        try:
            resp = requests.get(
                self.URL,
                params={"ids": self.station, "format": "raw"},
                timeout=10,
            )
            if resp.status_code != 200:
                return "Failed to fetch METAR data."
            raw = resp.text.strip()
            # The API appends a "$" end-of-report marker; drop it.
            raw = raw.rstrip("$").strip()
            if not raw:
                return "No METAR available for this station."
            return raw
        except Exception as e:
            logger.error("Failed to fetch METAR data: %s", e)
            return "Failed to fetch METAR data."
