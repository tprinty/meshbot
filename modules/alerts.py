import requests
import logging

logger = logging.getLogger(__name__)


class StormAlerts:
    """Fetch active NWS storm alerts for a given zone code (e.g. ALZ061)."""

    BASE_URL = "https://api.weather.gov/alerts/active"

    def __init__(self, zone_code):
        self.zone_code = zone_code

    def get_alerts(self):
        try:
            resp = requests.get(
                self.BASE_URL,
                params={"zone": self.zone_code},
                headers={"Accept": "application/geo+json"},
                timeout=10,
            )
            if resp.status_code != 200:
                return "Failed to fetch alerts."

            data = resp.json()
            features = data.get("features", [])
            if not features:
                return "No active alerts."

            lines = []
            for f in features[:3]:
                props = f.get("properties", {})
                event = props.get("event", "Alert")
                headline = props.get("headline") or props.get("description", "")
                # Trim headline to keep messages short
                if headline and len(headline) > 150:
                    headline = headline[:147] + "..."
                lines.append(f"{event}: {headline}")

            return "\n".join(lines)

        except Exception as e:
            logger.error("Failed to fetch alerts: %s", e)
            return "Failed to fetch alerts."
