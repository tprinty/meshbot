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
