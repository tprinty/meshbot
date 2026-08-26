# MeshBot

![Meshbot](./img/meshbot.png)

MeshBot is an OpenSource Python program designed to run on computers with a connected Meshtastic device, allowing users to send and receive messages efficiently over a mesh network.

Our Mission: 
 - To provide low-bandwidth functionality to a low bandwidth mesh.  This has originated in the EU where we have 1x longfast channel, and 10% duty cycle, so we try hard to make this low bandwidth, efficient, purposeful and helpful.  
 - For those outside of the EU, knock yourselves out, its opensource, modify at will. Just please dont be offended if we reject high bandwidth pull-requests, but we have no issues with extending commands.
 - As we are open source and an open community, please publish and share your meshtastic work. 

## Features

- Broadcast messages: Send text broadcasts to all devices on the mesh network.
- Weather updates: Get real-time weather updates for a specified location.
- Tides information: Receive tidal information for coastal areas (UK scraper or NOAA station).
- NOAA Tides: Pull official tide predictions from any NOAA Tides & Currents station.
- Storm Alerts: Real-time NWS storm alerts for a configured zone.
- Repeaters: Query nearby amateur radio repeaters via RepeaterBook.
- Tropical Weather: NHC Atlantic tropical weather tracking.
- METAR: Raw aviation METAR observation for a configured ICAO station.
- Whois: Query one of two User databases: mpowered247 or liamcottle.
- Simple BBS: Store and retrieve messages via the bot.
- Channel mode: Optionally respond to channel 0 broadcasts so all nodes see replies.
- Debug logging: All activity written to `meshbot.log` for easy monitoring.

## Requirements

- Python 3.x
- Meshtastic Python library
- Access to a Meshtastic device [Meshtastic](https://meshtastic.org)
- Serial drivers for your meshtastic device, See [Installing Serial Drivers](https://meshtastic.org/docs/getting-started/serial-drivers/)

## Installation

1. Clone this repository to your local machine:

```
git clone https://github.com/868meshbot/meshbot.git
```

2. Navigate into the folder and setup a virtual environment

```
cd meshbot
python3 -m venv .venv
. .venv/bin/activate
```

3. Install the required dependencies:

```
pip install -r requirements.txt
```

4. Copy the sample settings file and edit it for your setup:

```
cp settings.yaml.sample settings.yaml
```

5. Connect your Meshtastic device to your computer via USB and run the program:

```
python ./meshbot.py --port /dev/ttyACM0
```

## Configuration

There is a `settings.yaml` file which makes the program easy to manage. Copy `settings.yaml.sample` as a starting point.

Example Content:

```yaml
---
LOCATION: "Mobile, AL"
TIDE_LOCATION: "Mobile"
MYNODE: "3661660496"
MYNODES:
  - "3661660496"
DBFILENAME: "./db/nodes.db"
DM_MODE: False
FIREWALL: False
DUTYCYCLE: False
BOT_NAME: "WeMoBot"
WELCOME_ENABLED: False

# NOAA Tides & Currents station (overrides UK tides scraper when set)
NOAA_STATION: "8735180"
NOAA_STATION_NAME: "Dauphin Island"

# NWS storm alert zone code (https://alerts.weather.gov/)
NWS_ZONE: "ALZ061"

# RepeaterBook — nearby open repeaters
REPEATER_LAT: 30.6954
REPEATER_LON: -88.0399
REPEATER_RADIUS: 25
REPEATER_STATE_ID: 1

# NHC tropical weather tracker (Atlantic basin)
TROPICS_ENABLED: True

# Current conditions via nearest NWS observation station
WEATHER_LAT: 30.6954
WEATHER_LON: -88.0399

# METAR observation (aviation weather, terse format)
METAR_STATION: "KMOB"
```

### Settings Reference

| Setting | Description |
|---|---|
| `LOCATION` | City/location used for weather lookups. Falls back to IP geolocation if omitted. |
| `TIDE_LOCATION` | Location for UK tides scraper. Ignored if `NOAA_STATION` is set. |
| `MYNODE` | Node number (integer) of the connected radio. Used for DM filtering. |
| `MYNODES` | List of node numbers allowed to interact with the bot when `FIREWALL: True`. |
| `DBFILENAME` | Path to the whois SQLite database. |
| `DM_MODE` | `True`: only respond to direct messages. `False`: respond to channel 0 broadcasts (all nodes see replies). |
| `FIREWALL` | `True`: only respond to nodes listed in `MYNODES`. `False`: respond to anyone. |
| `DUTYCYCLE` | `True`: enforce EU 10% duty cycle limit. `False`: disable for regions without duty cycle rules. |
| `BOT_NAME` | Display name used in welcome messages. Default: `WeMoBot`. |
| `WELCOME_ENABLED` | `True`: send a channel welcome when a new node is seen for the first time. |
| `WELCOME_MESSAGE` | Custom welcome message template. Supports `{long_name}`, `{short_name}`, and `{bot_name}` placeholders. |
| `NOAA_STATION` | NOAA Tides & Currents station ID. When set, overrides the UK tides scraper. Find station IDs at [tidesandcurrents.noaa.gov](https://tidesandcurrents.noaa.gov/). |
| `NOAA_STATION_NAME` | Human-readable name for the NOAA station shown in responses. |
| `NWS_ZONE` | NWS zone code for storm alerts (e.g. `ALZ061`). Find yours at [alerts.weather.gov](https://alerts.weather.gov/). |
| `REPEATER_LAT` / `REPEATER_LON` | Coordinates for RepeaterBook nearby repeater search. |
| `REPEATER_RADIUS` | Search radius in miles (default: 25). |
| `REPEATER_STATE_ID` | RepeaterBook state ID for filtering results. |
| `TROPICS_ENABLED` | `True`: enable NHC Atlantic tropical weather tracking. |
| `WEATHER_LAT` / `WEATHER_LON` | Coordinates for the current-conditions lookup. The bot resolves the nearest NWS observation station and reports temperature, heat index, and humidity. |
| `METAR_STATION` | ICAO station code for the `#metar` command (e.g. `KMOB`). Fetches the latest aviation METAR observation. |

## Usage

```
python meshbot.py --help
```

Example on Linux:

```
python meshbot.py --port /dev/ttyACM0
```

Example on OSX:

```
python meshbot.py --port /dev/cu.usbserial-0001
```

Example on Windows:

```
python meshbot.py --port COM7
```

Example using TCP client:

```
python meshbot.py --host meshtastic.local
or
python meshbot.py --host 192.168.0.100
```

## Monitoring

All bot activity is written to `meshbot.log` in the working directory. Watch it live with:

```
tail -f meshbot.log
```

Logs rotate at midnight and are retained for 7 days (older files are deleted automatically).

## Bot Commands

With `DM_MODE: False`, send commands on channel 0 and everyone will see the response. With `DM_MODE: True`, DM the bot node directly.

Replies go back on the same channel the message arrived on: a direct message to the bot gets a private reply, and a channel broadcast gets a broadcast reply.

| Command | Description |
|---|---|
| `#help` | List available commands |
| `#test` | Receive a test acknowledgement |
| `#tst-detail` | Test with SNR, RSSI, and hop count detail |
| `#weather` | Local weather report |
| `#temp` | Current temperature, heat index, and humidity (requires `WEATHER_LAT`/`LON`) |
| `#metar` | Raw aviation METAR observation (requires `METAR_STATION`) |
| `#tides` | Tide info for the configured location |
| `#alerts` | Current NWS storm alerts (requires `NWS_ZONE`) |
| `#repeaters` | Nearby amateur radio repeaters (requires `REPEATER_LAT`/`LON`) |
| `#tropics` | Atlantic tropical weather summary (requires `TROPICS_ENABLED: True`) |
| `#flipcoin` | Flip a coin |
| `#random` | Random number 1–10 |
| `#whois # xxxx` | Look up a node by ID or short name |
| `#bbs any` | Check if you have BBS messages waiting |
| `#bbs get` | Retrieve your BBS messages |
| `#bbs post !address message` | Leave a message for another node |

## Contributors

- [868meshbot](https://github.com/868meshbot)

## Acknowledgements

This project utilizes the Meshtastic Python library, which provides communication capabilities for Meshtastic devices. For more information about Meshtastic, visit [meshtastic.org](https://meshtastic.org/).

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## References

Database of IDs, long_name and short_names obtained from the node list from the following URLs:

- [https://map.mpowered247.com/](https://map.mpowered247.com/)
- [https://meshtastic.liamcottle.net/](https://meshtastic.liamcottle.net/)
