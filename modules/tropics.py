import requests
import logging
import re
import warnings
from datetime import datetime
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

# NHC RSS XML is occasionally malformed (e.g. duplicate </item> tags).
# BeautifulSoup's html.parser tolerates this; xml.etree.ElementTree does not.
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

logger = logging.getLogger(__name__)

# Meshtastic bot reports local time in Central (America/Chicago, DST-aware).
# Season boundaries (Jun 1 / Nov 30) must be judged against Central time,
# not the host's UTC clock, or the announcement fires ~5h early on the prior
# evening.
_CENTRAL = ZoneInfo("America/Chicago")


def _central_today():
    """Today's date in Central time (America/Chicago)."""
    return datetime.now(_CENTRAL).date()


NHC_RSS_URL = "https://www.nhc.noaa.gov/index-at.xml"

# Atlantic hurricane season: June 1 – November 30
SEASON_START = (6, 1)
SEASON_END   = (11, 30)


def hurricane_season_announcement():
    """
    Return an announcement string on season-start (June 1) or season-end
    (November 30), otherwise return None.
    """
    today = _central_today()
    mm_dd = (today.month, today.day)
    year  = today.year
    if mm_dd == SEASON_START:
        return (
            f"Heads up — Atlantic Hurricane Season {year} starts today!\n"
            f"Send #tropics for live storm updates."
        )
    if mm_dd == SEASON_END:
        return (
            f"Atlantic Hurricane Season {year} officially ends today.\n"
            f"Stay prepared year-round. Send #tropics for storm info."
        )
    return None


def in_hurricane_season():
    """True if today falls within the Atlantic hurricane season."""
    today = _central_today()
    mm, dd = today.month, today.day
    start_m, start_d = SEASON_START
    end_m, end_d     = SEASON_END
    start_ord = start_m * 100 + start_d
    end_ord   = end_m   * 100 + end_d
    cur_ord   = mm      * 100 + dd
    return start_ord <= cur_ord <= end_ord


class TropicalWeather:
    """Fetch active Atlantic tropical storm info from the NHC RSS feed."""

    def get_tropics(self):
        try:
            resp = requests.get(NHC_RSS_URL, timeout=10)
            if resp.status_code != 200:
                return "Failed to fetch tropical weather data."

            soup = BeautifulSoup(resp.content, "html.parser")

            items = []
            for item in soup.find_all("item"):
                title_el = item.find("title")
                desc_el  = item.find("description")
                title = title_el.get_text(strip=True) if title_el else ""
                desc  = desc_el.get_text(strip=True)  if desc_el  else ""
                # Strip HTML tags from CDATA descriptions (NHC embeds links in some items)
                desc = re.sub(r"<[^>]*>", "", desc)

                # Filter: only active storm advisories, not general summaries
                lower = title.lower()
                if any(k in lower for k in ("advisory", "tropical storm", "hurricane", "depression")):
                    if len(desc) > 200:
                        desc = desc[:197] + "..."
                    items.append(f"{title}\n{desc}")

            if not items:
                if in_hurricane_season():
                    return "No active tropical systems. Hurricane season is active — stay alert."
                return "No active tropical systems in the Atlantic."

            return "\n---\n".join(items[:2])

        except Exception as e:
            logger.error("Failed to fetch tropical weather: %s", e)
            return "Failed to fetch tropical weather data."

    def get_tropics_items(self):
        """Return active NHC advisory items as a list of dicts.

        Each dict has: id (advisory title), title, description.
        Returns None on fetch failure, empty list if no active storms.
        Used by the tropics poller to detect new advisories.
        """
        try:
            resp = requests.get(NHC_RSS_URL, timeout=10)
            if resp.status_code != 200:
                return None

            soup = BeautifulSoup(resp.content, "html.parser")

            items = []
            for item in soup.find_all("item"):
                title_el = item.find("title")
                desc_el = item.find("description")
                title = title_el.get_text(strip=True) if title_el else ""
                desc = desc_el.get_text(strip=True) if desc_el else ""
                desc = re.sub(r"<[^>]*>", "", desc)

                lower = title.lower()
                if any(k in lower for k in ("advisory", "tropical storm",
                                              "hurricane", "depression")):
                    items.append({
                        "id": title,
                        "title": title,
                        "description": desc,
                    })

            return items

        except Exception as e:
            logger.error("Failed to fetch tropics items: %s", e)
            return None

    def summarize_for_mesh(self):
        """Return a compact, mesh-friendly summary of current tropical
        activity, or None if nothing to report.

        Parses the NHC Summary advisory to extract storm type, winds,
        pressure, location, movement, and strengthening forecast.
        Output fits in a single Meshtastic packet (~237 bytes).
        """
        items = self.get_tropics_items()
        if not items:
            return None

        # Find the Summary advisory (has the compact data we need)
        summary = None
        for item in items:
            if "Summary for" in item["title"]:
                summary = item
                break
        if not summary:
            return None

        desc = summary["description"]

        # Extract storm name/type from title
        title = summary["title"]
        # "Summary for Tropical Depression Nine (AT4/AL092026)"
        storm_match = re.search(
            r"Summary for (.+?) \(", title
        )
        storm_name = storm_match.group(1) if storm_match else title

        # Extract headline between ... markers
        headline = ""
        hl_match = re.search(r"\.\.\.(.+?)\.\.\.", desc)
        if hl_match:
            headline = hl_match.group(1).strip()

        # Extract winds
        winds = ""
        wind_match = re.search(
            r"sustained winds of (?:about )?(\d+) mph", desc
        )
        if wind_match:
            winds = f"{wind_match.group(1)}mph"

        # Extract pressure
        pressure = ""
        pres_match = re.search(
            r"pressure was (\d+) mb", desc
        )
        if pres_match:
            pressure = f"{pres_match.group(1)}mb"

        # Extract location
        location = ""
        loc_match = re.search(
            r"located near ([\d.]+),\s*-?([\d.]+)", desc
        )
        if loc_match:
            lat, lon = loc_match.group(1), loc_match.group(2)
            location = f"{lat}N {lon}W"

        # Extract movement
        movement = ""
        mov_match = re.search(
            r"movement (\w+) at (\d+) mph", desc
        )
        if mov_match:
            movement = f"{mov_match.group(1)} {mov_match.group(2)}mph"

        # Build compact message
        parts = [f"\U0001f300 {storm_name}"]
        if winds or pressure:
            stats = " | ".join(x for x in (winds, pressure) if x)
            parts.append(stats)
        if location:
            loc_line = f"\U0001f4cd {location}"
            if movement:
                loc_line += f" | \u2192 {movement}"
            parts.append(loc_line)
        if headline:
            parts.append(f"\u26a0 {headline}")

        return "\n".join(parts)
