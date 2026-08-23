import requests
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class NOAATides:
    """Fetch today's hi/lo tide predictions from NOAA Tides & Currents API."""

    BASE_URL = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"

    def __init__(self, station_id, station_name=None):
        self.station_id = station_id
        self.station_name = station_name or station_id

    def get_tides(self):
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        params = {
            "begin_date": today,
            "end_date": today,
            "station": self.station_id,
            "product": "predictions",
            "datum": "MLLW",
            "time_zone": "lst_ldt",
            "interval": "hilo",
            "units": "english",
            "application": "meshbot",
            "format": "json",
        }
        try:
            resp = requests.get(self.BASE_URL, params=params, timeout=10)
            if resp.status_code != 200:
                return "Failed to fetch tide data."

            data = resp.json()
            predictions = data.get("predictions", [])
            if not predictions:
                return "No tide data available."

            output = f"Tides ({self.station_name})\n"
            for p in predictions:
                t = p.get("t", "")          # "2024-08-22 05:34"
                v = p.get("v", "")          # "0.234"
                tide_type = p.get("type", "")  # "H" or "L"
                label = "High" if tide_type == "H" else "Low"
                # Format time as HH:MM
                try:
                    dt = datetime.strptime(t, "%Y-%m-%d %H:%M")
                    t_fmt = dt.strftime("%H:%M")
                except ValueError:
                    t_fmt = t
                output += f"{t_fmt} {label} {float(v):.1f}ft\n"

            return output.strip()

        except Exception as e:
            logger.error("Failed to fetch NOAA tide data: %s", e)
            return "Failed to fetch tide data."
