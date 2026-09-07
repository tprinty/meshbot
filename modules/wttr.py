import json
import requests
import logging

logger = logging.getLogger(__name__)


# Shared emoji map: condition keyword → emoji
_CONDITION_EMOJIS = {
    "☀️": ["Sunny", "Clear"],
    "🌤️": ["Partly cloudy", "Partly Cloudy"],
    "☁️": ["Cloudy", "Overcast"],
    "🌧️": [
        "Rain", "Light rain", "Drizzle",
        "Moderate rain", "Heavy rain",
        "Light Rain", "Moderate Rain",
        "Patchy rain possible", "Patchy rain nearby",
        "Rain shower", "Light shower rain",
    ],
    "🌩️": ["Thunderstorm", "Thundershower"],
    "❄️": ["Snow", "Light snow", "Light shower snow"],
    "🌨️": ["Snow shower", "Shower snow"],
    "🌬️": ["Windy"],
    "🌫️": ["Mist", "Fog"],
}


def _pick_emoji(condition):
    """Return the best emoji for a weather condition string."""
    for emoji, keywords in _CONDITION_EMOJIS.items():
        if any(k.lower() in condition.lower() for k in keywords):
            return emoji
    return "🌡️"


def _compact_time(t):
    """Compress '06:32 AM' → '6:32a'."""
    try:
        parts = t.replace(":", " ").split()
        h = int(parts[0])
        m = parts[1]
        ampm = parts[2].lower() if len(parts) > 2 else ""
        return f"{h}:{m}{ampm[0]}"
    except Exception:
        return t


class WeatherFetcher:
    def __init__(self, location):
        self.location = location

    def get_weather(self):
        """Current conditions from wttr.in text format."""
        url = f"https://wttr.in/{self.location}?format=%C+%t+%w+%S+%s"
        try:
            response = requests.get(url)
            if response.status_code == 200:
                response_text = response.text.replace("Partly ", "")
                response_text = response_text.replace("Light ", "")
                response_text = response_text.replace(" shower", "")
                weather_info = response_text.split()
                condition = weather_info[0].strip()
                temperature = weather_info[1].strip().lstrip('+')
                wind = weather_info[2].strip()
                dawn = weather_info[-2].strip()
                sunset = weather_info[-1].strip()

                emoji = _pick_emoji(condition)

                output = f"{emoji} {condition}\n"
                output += f"🌡️ {temperature}\n"
                output += f"💨 {wind}\n"
                output += f"🌞 {dawn}\n"
                output += f"🌛 {sunset}\n"
                # Strip any wttr.in private-use Unicode characters
                # (U+E000–U+F8FF) that Meshtastic screens can't render.
                output = "".join(
                    c for c in output if ord(c) < 0xE000 or ord(c) > 0xF8FF
                )
                return output
            else:
                return "Failed to fetch weather data."
        except ConnectionResetError as e:
            logger.error("Failed to fetch weather data: Connection reset error: %s", e)
            return "Failed to fetch weather data."
        except Exception as e:
            logger.error("Failed to fetch weather data: %s", e)
            return "Failed to fetch weather data."

    def get_forecast(self):
        """Return today's daily forecast from wttr.in JSON API.

        Compact Meshtastic-friendly format:
            ☀️ Condition  ☂️ rain%
            🌡️ min°F → max°F
            💨 WindDir mph  UV index
            🌞 sunrise  🌛 sunset

        Falls back to current conditions on error.
        """
        url = f"https://wttr.in/{self.location}?format=j1"
        try:
            response = requests.get(url, timeout=15)
            if response.status_code != 200:
                return self._forecast_fallback()
            data = json.loads(response.text)
            today = data.get("weather", [{}])[0]
            if not today:
                return self._forecast_fallback()

            max_temp = today.get("maxtempF", "?")
            min_temp = today.get("mintempF", "?")
            uv = today.get("uvIndex", "?")

            # Dominant daytime condition (first hourly slot)
            hourly = today.get("hourly", [])
            condition = "?"
            rain_pct = "?"
            wind_dir = ""
            wind_speed = "?"
            for h in hourly:
                descs = h.get("weatherDesc", [])
                if descs:
                    condition = descs[0].get("value", "?")
                if h.get("chanceofrain") is not None:
                    rain_pct = h["chanceofrain"]
                wind_dir = h.get("winddir16Point", "")
                wind_speed = h.get("windspeedMiles", "?")
                break

            # Sunrise / sunset
            astro = today.get("astronomy", [{}])
            sunrise = "?"
            sunset = "?"
            for a in astro:
                sunrise = a.get("sunrise", "?").upper()
                sunset = a.get("sunset", "?").upper()
                break

            emoji = _pick_emoji(condition)
            sr_short = _compact_time(sunrise)
            ss_short = _compact_time(sunset)

            output = f"{emoji} {condition}  ☂️ {rain_pct}%\n"
            output += f"🌡️ {min_temp}°F → {max_temp}°F\n"
            output += f"💨 {wind_dir} {wind_speed}mph  UV {uv}\n"
            output += f"🌞 {sr_short}  🌛 {ss_short}"

            return output

        except Exception as e:
            logger.error("Failed to fetch forecast: %s", e)
            return self._forecast_fallback()

    def _forecast_fallback(self):
        """Fall back to current conditions when forecast API fails."""
        return self.get_weather()