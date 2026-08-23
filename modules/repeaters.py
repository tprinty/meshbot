import requests
import logging

logger = logging.getLogger(__name__)


class Repeaters:
    """Fetch nearby open repeaters from RepeaterBook."""

    BASE_URL = "https://www.repeaterbook.com/api/exportROW.php"

    def __init__(self, lat, lon, radius_miles=25, state_id=None):
        self.lat = lat
        self.lon = lon
        self.radius_miles = radius_miles
        self.state_id = state_id  # RepeaterBook state numeric ID (Alabama = 1)

    def get_repeaters(self):
        params = {
            "lat": self.lat,
            "lng": self.lon,
            "distance": self.radius_miles,
            "Operational": "Y",
            "Use": "OPEN",
            "format": "json",
        }
        if self.state_id:
            params["state_id"] = self.state_id

        try:
            resp = requests.get(self.BASE_URL, params=params, timeout=10)
            if resp.status_code != 200:
                return "Failed to fetch repeater data."

            data = resp.json()
            results = data.get("results", [])
            if not results:
                return "No open repeaters found nearby."

            lines = ["Nearby repeaters:"]
            for r in results[:5]:
                freq = r.get("Frequency", "?")
                offset = r.get("Input Freq", "")
                tone = r.get("PL", "")
                call = r.get("Callsign", "?")
                city = r.get("Nearest City", "")
                tone_str = f" {tone}Hz" if tone else ""
                city_str = f" ({city})" if city else ""
                lines.append(f"{call} {freq}{city_str} T{tone_str}")

            return "\n".join(lines)

        except Exception as e:
            logger.error("Failed to fetch repeater data: %s", e)
            return "Failed to fetch repeater data."
