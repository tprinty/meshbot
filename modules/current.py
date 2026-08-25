import logging

import requests

logger = logging.getLogger(__name__)


class CurrentConditions:
    """Fetch current temperature and heat index from the nearest NWS
    observation station."""

    POINTS_URL = "https://api.weather.gov/points/{lat},{lon}"
    HEADERS = {"Accept": "application/geo+json"}

    def __init__(self, lat, lon):
        self.lat = lat
        self.lon = lon

    @staticmethod
    def _c_to_f(c):
        """Convert Celsius to Fahrenheit, rounded to the nearest degree."""
        return round(c * 9 / 5 + 32)

    def _nearest_station(self):
        """Resolve the nearest NWS observation station identifier."""
        resp = requests.get(
            self.POINTS_URL.format(lat=self.lat, lon=self.lon),
            headers=self.HEADERS,
            timeout=10,
        )
        if resp.status_code != 200:
            return None
        stations_url = resp.json().get("properties", {}).get(
            "observationStations"
        )
        if not stations_url:
            return None
        stations_resp = requests.get(stations_url, timeout=10)
        if stations_resp.status_code != 200:
            return None
        stations = stations_resp.json().get("features", [])
        if not stations:
            return None
        return stations[0]["properties"]["stationIdentifier"]

    def get_current(self):
        """Return a one-line current-conditions summary, or a failure
        string."""
        try:
            station_id = self._nearest_station()
            if not station_id:
                return "Failed to fetch current conditions."

            resp = requests.get(
                f"https://api.weather.gov/stations/{station_id}"
                "/observations/latest",
                timeout=10,
            )
            if resp.status_code != 200:
                return "Failed to fetch current conditions."

            props = resp.json().get("properties", {})
            temp_c = props.get("temperature", {}).get("value")
            if temp_c is None:
                return "Failed to fetch current conditions."

            heat_index_c = props.get("heatIndex", {}).get("value")
            humidity = props.get("relativeHumidity", {}).get("value")
            description = props.get("textDescription", "")

            parts = [f"🌡️ {self._c_to_f(temp_c)}°F"]
            if heat_index_c is not None:
                parts.append(f"feels {self._c_to_f(heat_index_c)}°F")
            if humidity is not None:
                parts.append(f"💧 {round(humidity)}%")
            if description:
                parts.append(description)
            return " · ".join(parts)
        except Exception as e:
            logger.error("Failed to fetch current conditions: %s", e)
            return "Failed to fetch current conditions."
