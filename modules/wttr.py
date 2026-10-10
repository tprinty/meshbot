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


def _find_rain_window(hourly):
    """Scan 3-hourly slots, return time window for highest-rain block.

    Returns a string like '12a-9a', '3p', or '' if no rain.
    """
    slots = []
    for h in hourly:
        time_raw = str(h.get("time", "0")).zfill(4)
        hour = int(time_raw[:2] or "0")
        ampm = "a" if hour < 12 else "p"
        display = hour % 12
        if display == 0:
            display = 12
        rain = int(h.get("chanceofrain", 0) or 0)
        slots.append((f"{display}{ampm}", rain, hour))

    # Find contiguous blocks with rain > 0
    blocks = []
    current = []
    for label, rain, hour in slots:
        if rain > 0:
            current.append((label, rain, hour))
        else:
            if current:
                blocks.append(current)
                current = []
    if current:
        blocks.append(current)

    if not blocks:
        return ""

    # Pick the block with the highest peak rain chance
    best = max(blocks, key=lambda b: max(r for _, r, _ in b))
    if len(best) == 1:
        return best[0][0]
    return f"{best[0][0]}-{best[-1][0]}"


class WeatherFetcher:
    def __init__(self, location):
        self.location = location

    def get_weather(self):
        """Daily forecast: high/low, rain% + timing, sunrise/sunset.

        Compact format:
            🌡️ min°F → max°F
            ☂️ rain% time-window
            🌞 sunrise  🌛 sunset
        """
        url = f"https://wttr.in/{self.location}?format=j1"
        try:
            response = requests.get(url, timeout=15)
            if response.status_code != 200:
                return "Failed to fetch weather data."
            data = response.json()
            today = data.get("weather", [{}])[0]
            if not today:
                return "Failed to fetch weather data."

            max_temp = today.get("maxtempF", "?")
            min_temp = today.get("mintempF", "?")

            # Rain — max chance across all hours + when
            hourly = today.get("hourly", [])
            max_rain = max(
                (int(h.get("chanceofrain", 0) or 0) for h in hourly),
                default=0
            )
            rain_window = _find_rain_window(hourly)

            # Sunrise / sunset
            astro = today.get("astronomy", [{}])[0]
            sunrise = _compact_time(astro.get("sunrise", "?"))
            sunset = _compact_time(astro.get("sunset", "?"))

            output = f"🌡️ {min_temp}°F → {max_temp}°F\n"
            if max_rain > 0 and rain_window:
                output += f"☂️ {max_rain}% {rain_window}\n"
            else:
                output += "☂️ 0%\n"
            output += f"🌞 {sunrise}  🌛 {sunset}"

            # Strip any wttr.in private-use Unicode characters
            # (U+E000–U+F8FF) that Meshtastic screens can't render.
            output = "".join(
                c for c in output if ord(c) < 0xE000 or ord(c) > 0xF8FF
            )
            return output

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
            data = response.json()
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
        """Fall back to daily summary when forecast API fails."""
        return self.get_weather()