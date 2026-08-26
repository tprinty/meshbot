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
            structured = self.get_alerts_structured()
            if structured is None:
                return "Failed to fetch alerts."
            if not structured:
                return "No active alerts."

            lines = []
            for a in structured[:3]:
                headline = a["headline"] or a["description"]
                if headline and len(headline) > 150:
                    headline = headline[:147] + "..."
                lines.append(f"{a['event']}: {headline}")

            return "\n".join(lines)

        except Exception as e:
            logger.error("Failed to fetch alerts: %s", e)
            return "Failed to fetch alerts."

    def get_alerts_structured(self):
        """Return active alerts as a list of dicts for programmatic use.

        Each dict has: id, event, headline, severity, expires, description.
        Returns None on fetch failure, empty list if no active alerts.
        """
        try:
            resp = requests.get(
                self.BASE_URL,
                params={"zone": self.zone_code},
                headers={"Accept": "application/geo+json"},
                timeout=10,
            )
            if resp.status_code != 200:
                logger.warning(
                    "NWS alerts API returned %d", resp.status_code
                )
                return None

            data = resp.json()
            features = data.get("features", [])
            results = []
            for f in features:
                props = f.get("properties", {})
                results.append({
                    "id": props.get("id", ""),
                    "event": props.get("event", "Alert"),
                    "headline": props.get("headline", ""),
                    "severity": props.get("severity", "Unknown"),
                    "expires": props.get("expires", ""),
                    "description": props.get("description", ""),
                })
            return results

        except Exception as e:
            logger.error("Failed to fetch structured alerts: %s", e)
            return None
