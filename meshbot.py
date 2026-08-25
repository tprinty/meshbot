#!python3
# -*- coding: utf-8 -*-

"""
MeshBot
=======================

meshbot.py: A message bot designed for Meshtastic, providing information from modules upon request:
* weather information 
* tides information 
* whois search
* simple bbs

Author:
- Andy
- April 2024
- Ben Mason , Feb 2026

MIT License

Copyright (c) 2024 Andy

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import argparse
import logging
import secrets
import sqlite3
import threading
import time
from pathlib import Path
import requests
import yaml

try:
    import meshtastic.serial_interface
    import meshtastic.tcp_interface
    from pubsub import pub
except ImportError:
    print(
        "ERROR: Missing meshtastic library!\nYou can install it via pip:\npip install meshtastic\n"
    )

import serial.tools.list_ports

from modules.alerts import StormAlerts
from modules.bbs import BBS
from modules.current import CurrentConditions
from modules.noaa_tides import NOAATides
from modules.repeaters import Repeaters
from modules.tides import TidesScraper
from modules.tropics import TropicalWeather, hurricane_season_announcement
from modules.twin_cipher import TwinHexDecoder, TwinHexEncoder
from modules.whois import Whois
from modules.wttr import WeatherFetcher


def find_serial_ports():
    # Use the list_ports module to get a list of available serial ports
    ports = [port.device for port in serial.tools.list_ports.comports()]
    filtered_ports = [
        port for port in ports if "COM" in port.upper() or "USB" in port.upper()
    ]
    return filtered_ports


# Configure logging
log_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

_console_handler = logging.StreamHandler()
_console_handler.setFormatter(log_formatter)
logger.addHandler(_console_handler)

_file_handler = logging.FileHandler("meshbot.log")
_file_handler.setFormatter(log_formatter)
logger.addHandler(_file_handler)

class MeshBot:

    def __init__(self, ip_host = None, serial_port = None, db = None):
        self.serial_ports = serial_port
        self.ip_host = ip_host
        self.db = db
        self.weather_info = None
        self.tides_info = None
        self.alerts_info = None
        self.tropics_info = None

        self.transmission_count = 0
        self.cooldown = False
        self.kill_all_robots = 0  # Assuming you missed defining kill_all_robots
        self.seen_nodes = set()

        self.load_setting()

    def load_setting(self):

        with open("settings.yaml", "r") as file:
            settings = yaml.safe_load(file)

        if "LOCATION" in settings:
            self.location = settings.get("LOCATION")
        else:
            try:
               self.location = requests.get("https://ipinfo.io/city").text
               logger.info(f"Setting location to {self.location}")
            except:
               logger.critical("Could not calculate location.  Using defaults")
               raise Exception 

        self.tide_location = settings.get("TIDE_LOCATION", self.location)
        self.mynode = settings.get("MYNODE")
        self.mynodes = settings.get("MYNODES", None)
        self.db_filename = settings.get("DBFILENAME")
        self.dm_mode = settings.get("DM_MODE", True)
        self.firewall = settings.get("FIREWALL", True)
        self.dutycycle = settings.get("DUTYCYCLE", True)
        self.bot_name = settings.get("BOT_NAME", "WeMoBot")
        self.welcome_enabled = settings.get("WELCOME_ENABLED", False)
        self.welcome_message = settings.get(
            "WELCOME_MESSAGE",
            "🤖 Welcome {long_name} ({short_name}) to the mesh! - {bot_name}"
        )

        logger.info(f"DUTYCYCLE: {self.dutycycle}")
        logger.info(f"DM_MODE: {self.dm_mode}")
        logger.info(f"FIREWALL: {self.firewall}")

        self.weather_fetcher = WeatherFetcher(self.location)
        self.tides_scraper = TidesScraper(self.tide_location)
        self.bbs = BBS()

        # Optional: NOAA tides (overrides UK tides scraper when configured)
        noaa_station = settings.get("NOAA_STATION")
        self.noaa_tides = NOAATides(
            noaa_station,
            station_name=settings.get("NOAA_STATION_NAME", noaa_station),
        ) if noaa_station else None

        # Optional: NWS storm alerts
        nws_zone = settings.get("NWS_ZONE")
        self.storm_alerts = StormAlerts(nws_zone) if nws_zone else None

        # Optional: local repeaters via RepeaterBook
        rep_lat = settings.get("REPEATER_LAT")
        rep_lon = settings.get("REPEATER_LON")
        self.repeaters = Repeaters(
            lat=rep_lat,
            lon=rep_lon,
            radius_miles=settings.get("REPEATER_RADIUS", 25),
            state_id=settings.get("REPEATER_STATE_ID"),
        ) if (rep_lat and rep_lon) else None

        # Optional: current conditions via nearest NWS observation station
        cur_lat = settings.get("WEATHER_LAT")
        cur_lon = settings.get("WEATHER_LON")
        self.current_conditions = (
            CurrentConditions(cur_lat, cur_lon)
            if (cur_lat and cur_lon)
            else None
        )

        # Optional: NHC tropical weather
        self.tropics_enabled = settings.get("TROPICS_ENABLED", False)
        self.tropical_weather = TropicalWeather() if self.tropics_enabled else None

    # Function to periodically refresh weather and tides data
    def refresh_data(self):
        while True:
            self.weather_info = self.weather_fetcher.get_weather()
            if self.noaa_tides:
                self.tides_info = self.noaa_tides.get_tides()
            else:
                self.tides_info = self.tides_scraper.get_tides()
            if self.storm_alerts:
                self.alerts_info = self.storm_alerts.get_alerts()
            if self.tropical_weather:
                self.tropics_info = self.tropical_weather.get_tropics()
            time.sleep(3 * 60 * 60)  # Sleep for 3 hours

    def _background_resets(self):
        """Single background thread handling all periodic resets."""
        last_transmission_reset = time.time()
        last_cooldown_reset = time.time()
        last_killbot_reset = time.time()

        while True:
            now = time.time()

            if now - last_transmission_reset >= 180:
                self.transmission_count = max(0, self.transmission_count - 1)
                logger.info(f"Reducing transmission count {self.transmission_count}")
                last_transmission_reset = now

            if now - last_cooldown_reset >= 240:
                self.cooldown = False
                logger.info("Cooldown Disabled.")
                last_cooldown_reset = now

            if now - last_killbot_reset >= 120:
                self.kill_all_robots = 0
                logger.info("Killbot Disabled.")
                last_killbot_reset = now

            time.sleep(5)  # Check every 5 seconds — negligible CPU usage

    def _send(self, text, sender_id, wantAck=False):
        try:
            dest = sender_id if self.dm_mode else "^all"
            self.interface.sendText(text, wantAck=wantAck, destinationId=dest)
            self.transmission_count += 1
        except Exception as e:
            logger.error(f"Failed to send message: {e}")

    def reset_transmission_count(self):
        self.transmission_count -= 1
        if self.transmission_count < 0:
            self.transmission_count = 0
        logger.info(f"Reducing transmission count {self.transmission_count}")
        threading.Timer(180.0, self.reset_transmission_count).start()

    def reset_cooldown(self):
        self.cooldown = False
        logger.info("Cooldown Disabled.")
        threading.Timer(240.0, self.reset_cooldown).start()

    def reset_killallrobots(self):
        self.kill_all_robots = 0
        logger.info("Killbot Disabled.")
        threading.Timer(120.0, self.reset_killallrobots).start()

    def command_fw(self, message):
        logger.info("Firewall Mode Command Received")
        message_parts = message.split(" ")
        if len(message_parts) > 1:
            if message_parts[1].lower() == "off":
                self.firewall = False
                logger.info("FIREWALL=False")
            else:
                self.firewall = True
                logger.info("FIREWALL=True")
        else:
            self.firewall = True
            logger.info("FIREWALL=True")

    def command_dm(self, message):
        logger.info("DM Mode Command Received")
        message_parts = message.split(" ")
        if len(message_parts) > 1:
            if message_parts[1].lower() == "off":
                self.dm_mode = False
                logger.info("DM_MODE=False")
            else:
                self.dm_mode = True
                logger.info("DM_MODE=True")
        else:
            self.dm_mode = True
            logger.info("DM_MODE=True")

    def command_flipcoin(self, interface, sender_id):

        logger.info("Flipcoin Command Recived")
        # Increment the transmission count for this message
        self.transmission_count += 1
        
        text = secrets.choice(["Heads", "Tails"])
        self._send(text, sender_id, wantAck=True)

    def command_random(self, interface, sender_id):

        logger.info("Random Command Recived")
        self.transmission_count += 1

        text = str(secrets.randbelow(10) + 1)
        self._send(text, sender_id, wantAck=True)

    def command_twin(self, message, interface, sender_id):
        logger.info("Twin Command Recived")
#        message_parts = packet["decoded"]["text"].split(" ")
        message_parts = message.split(" ")
        content = " ".join(message_parts[2:])
        if message_parts[1].lower() == "d":
            text = TwinHexDecoder().decrypt(content)
            self._send(text, sender_id, wantAck=True)

        else:
            text = TwinHexEncoder().encrypt(content)
            self._send(text, sender_id, wantAck=True)

    def command_tst_detail(self, packet, interface, sender_id):
        logger.info("Detailed Test command Received")
        self.transmission_count += 1
        testreply = "🟢 ACK."
        if "hopStart" in packet:
            if (packet["hopStart"] - packet["hopLimit"]) == 0:
                testreply += "Received Directly at "
            else:
                testreply += "Received from " + str(packet["hopStart"] - packet["hopLimit"]) + "hop(s) away at"
        testreply += str(packet["rxRssi"]) + "dB, SNR: " + str(packet["rxSnr"]) + "dB (" + str(int(packet["rxSnr"] + 10 * 5)) + "%)"

        self._send(testreply, sender_id, wantAck=True)

    def command_whois(self, message, interface, sender_id):
        logger.info("whois command received")
        message_parts = message.split("#")
        self.transmission_count += 1
        if len(message_parts) < 3:
            return
        query = message_parts[2].strip()
        logger.info(f"Querying whois DB {self.db_filename} for: {query}")

        result = None
        try:
            whois_search = Whois(self.db_filename)
            # Try the query as a (partial) hex node ID first, then fall back
            # to a short-name lookup when it is not hex or yields no match.
            try:
                int(query, 16)
                result = whois_search.search_nodes(query)
            except ValueError:
                pass
            if not result:
                result = whois_search.search_nodes_sn(query)
            whois_search.close_connection()
        except sqlite3.Error as e:
            logger.error(f"Whois database error: {e}")
            self._send(
                "Whois lookup failed (database error).",
                sender_id,
                wantAck=False,
            )
            return

        if result:
            node_id, long_name, short_name = result
            whois_data = f"ID:{node_id}\n"
            whois_data += f"Long Name: {long_name}\n"
            whois_data += f"Short Name: {short_name}"
            logger.info(f"Data: {whois_data}")
            self._send(f"{whois_data}", sender_id, wantAck=False)
        else:
            self._send("No matching record found.", sender_id, wantAck=False)

    def command_bbs(self, packet, interface, sender_id):
        logger.info("bbs Command Received")
        message = packet["decoded"]["text"].lower()
        self.transmission_count += 1
        count = 0
        message_parts = message.split()
        addy = hex(packet["from"]).replace("0x", "!")
        if message_parts[1].lower() == "any":
            try:
                count = self.bbs.count_messages(addy)
                logger.info(f"{count} messages found")
            except ValueError as e:
                message = "No new messages."
                logger.error(f"bbs count messages error: {e}")
            if count >= 0:
                message = "You have " + str(count) + " messages."
                self._send(message, sender_id, wantAck=True)

        if message_parts[1].lower() == "get":
            try:
                messages = self.bbs.get_message(addy)
                if messages:
                    for user, message in messages:
                        logger.info(f"Message for {user}: {message}")
                        self._send(message, sender_id, wantAck=False)

                    self.bbs.delete_message(addy)
                else:
                    message = "No new messages."
                    logger.info("No new messages")
                    self._send(message, sender_id, wantAck=False)
            except Exception as e:
                logger.error(f"Error: {e}")

        if message_parts[1].lower() == "post":
            content = " ".join(
                message_parts[3:]
            )  # Join the remaining parts as the message content
            whois_search = Whois(self.db_filename)
            result = whois_search.search_nodes(
                hex(packet["from"]).replace("0x", "")
            )
            if result:
                node_id, long_name, short_name = result
            else:
                short_name = hex(packet["from"])
            content = (
                content
                + ". From: "
                + short_name
                + "("
                + str(hex(packet["from"])).replace("0x", "!")
                + ")"
            )
            self.bbs.post_message(message_parts[2], content)

    def command_kill_all_robots(self, message, interface, sender_id):
        logger.info("Kill All Robots Command Received")
        self.transmission_count += 1
        if self.kill_all_robots == 0:
            self._send("Confirm", sender_id, wantAck=False)
            self.kill_all_robots += 1
        if self.kill_all_robots > 1:
            self._send("💣 Deactivating all reachable bots... SECRET_SHUTDOWN_STRING", sender_id, wantAck=False)
            self.transmission_count += 1
            self.kill_all_robots = 0

    def _hurricane_season_announcer(self):
        """
        Background thread: on June 1 and November 30 broadcast a season
        start/end message to the mesh (channel broadcast, not a DM).
        Checks once per day at startup, then again every 24 hours.
        """
        import datetime as _dt
        announced_today = None
        while True:
            today = _dt.date.today()
            if today != announced_today and self.tropical_weather:
                msg = hurricane_season_announcement()
                if msg:
                    try:
                        self.interface.sendText(msg, wantAck=False)
                        logger.info("Hurricane season announcement sent.")
                    except Exception as e:
                        logger.error("Failed to send hurricane season announcement: %s", e)
                    announced_today = today
            time.sleep(60 * 60)  # check again in 1 hour (catches restarts close to midnight)

    def command_alerts(self, sender_id):
        logger.info("Alerts Command Received")
        self.transmission_count += 1
        if self.storm_alerts is None:
            self._send("Storm alerts not configured.", sender_id, wantAck=False)
            return
        info = self.alerts_info or self.storm_alerts.get_alerts()
        self._send(info, sender_id, wantAck=False)

    def command_repeaters(self, sender_id):
        logger.info("Repeaters Command Received")
        self.transmission_count += 1
        if self.repeaters is None:
            self._send("Repeaters not configured.", sender_id, wantAck=False)
            return
        self._send(self.repeaters.get_repeaters(), sender_id, wantAck=False)

    def command_tropics(self, sender_id):
        logger.info("Tropics Command Received")
        self.transmission_count += 1
        if self.tropical_weather is None:
            self._send("Tropical weather not enabled.", sender_id, wantAck=False)
            return
        info = self.tropics_info or self.tropical_weather.get_tropics()
        self._send(info, sender_id, wantAck=False)

    def command_temp(self, sender_id):
        logger.info("Temp Command Received")
        self.transmission_count += 1
        if self.current_conditions is None:
            self._send(
                "Current conditions not configured.", sender_id, wantAck=False
            )
            return
        self._send(
            self.current_conditions.get_current(), sender_id, wantAck=False
        )

    def command_help(self, interface, sender_id):
        logger.info("Help Command Received")
        self.transmission_count += 1
        cmds = ["#help", "#test", "#tst-detail", "#weather", "#tides", "#flipcoin", "#random"]
        if self.storm_alerts:
            cmds.append("#alerts")
        if self.repeaters:
            cmds.append("#repeaters")
        if self.tropical_weather:
            cmds.append("#tropics")
        if self.current_conditions:
            cmds.append("#temp")
        self._send("Available commands:\n " + "\n ".join(cmds), sender_id, wantAck=False)

    def _handle_nodeinfo(self, packet, interface):
        """Send a channel welcome when a node is seen for the first time this session."""
        if not self.welcome_enabled:
            return
        node_id = packet.get("from")
        if node_id is None or node_id in self.seen_nodes:
            return
        # Never greet our own node — the radio hears its own NODEINFO broadcasts.
        if self.mynode and str(node_id) == str(self.mynode):
            return
        self.seen_nodes.add(node_id)
        user = packet.get("decoded", {}).get("user", {})
        long_name = user.get("longName", f"!{node_id:08x}")
        short_name = user.get("shortName", "???")
        msg = self.welcome_message.format(
            long_name=long_name, short_name=short_name, bot_name=self.bot_name
        )
        try:
            interface.sendText(msg, wantAck=False)
            logger.info("Welcome sent for node %s", node_id)
        except Exception as e:
            logger.error("Failed to send welcome: %s", e)

    # Function to handle incoming messages
    def message_listener(self, packet, interface):

        if packet is not None and "decoded" in packet and \
                packet["decoded"].get("portnum") == "NODEINFO_APP":
            self._handle_nodeinfo(packet, interface)

        if packet is not None and "decoded" in packet and \
                packet["decoded"].get("portnum") == "TEXT_MESSAGE_APP":
            message = packet["decoded"]["text"]

            if not message.strip().startswith("#"):
                return
            message = message.lower()
            sender_id = packet["from"]
            logger.info(f"Message {packet['decoded']['text']} from {packet['from']}")
            logger.info(f"transmission count {self.transmission_count}")
            
            if (
                (self.transmission_count < 16 or self.dutycycle == False)
                and (self.dm_mode == 0 or str(packet["to"]) == self.mynode)
                and (self.firewall == 0 or any(node in str(packet["from"]) for node in self.mynodes))
            ):
                if "#fw" in message:
                    self.command_fw(message)
                elif "#dm" in message:
                    self.command_dm(message)
                elif "#flipcoin" in message:
                    self.command_flipcoin(interface, sender_id)
                elif "#random" in message:
                    self.command_random(interface, sender_id)
                elif "#twin" in message:
                    self.command_twin(message, interface, sender_id)
                elif "#weather" in message:
                    self._send(self.weather_info, sender_id, wantAck=True)
                elif "#tides" in message:
                    self._send(self.tides_info, sender_id, wantAck=True)
                elif "#alerts" in message:
                    self.command_alerts(sender_id)
                elif "#repeaters" in message:
                    self.command_repeaters(sender_id)
                elif "#tropics" in message:
                    self.command_tropics(sender_id)
                elif "#temp" in message:
                    self.command_temp(sender_id)
                elif "#test" in message:
                    self._send("🟢 ACK", sender_id, wantAck=True)
                elif "#tst-detail" in message:
                    self.command_tst_detail(packet, interface, sender_id)
                elif "#whois #" in message:
                    self.command_whois(message, interface, sender_id)
                elif "#bbs" in message:
                    self.command_bbs(packet, interface, sender_id)
                elif "#kill_all_robots" in message:
                    self.command_kill_all_robots(message, interface, sender_id)
                elif "#help" in message:
                    self.command_help(interface, sender_id)
            if self.transmission_count >= 11 and self.dutycycle == True:
                if not self.cooldown:
                    interface.sendText(
                        "❌ Bot has reached duty cycle, entering cool down... ❄",
                        wantAck=False,
                    )
                    logger.info("Cooldown enabled.")
                    self.cooldown = True
                logger.info(
                    "Duty cycle limit reached. Please wait before transmitting again."
                )
            else:
                # do nothing as not a keyword and message destination was the node
                pass


    # Main function
    def run(self):
        logger.info("Starting program.")

        reset_thread = threading.Thread(target=self._background_resets)
        reset_thread.daemon = True
        reset_thread.start()

        logger.info(f"Press CTRL-C x2 to terminate the program")

        if self.ip_host and self.serial_ports:
            self.interface = meshtastic.tcp_interface.TCPInterface(hostname=self.ip_host,noProto=False)
        else:
            self.interface = meshtastic.serial_interface.SerialInterface(self.serial_ports[0])

        # Receive Mechtastic Messages    
        pub.subscribe(self.message_listener, "meshtastic.receive")

        # Start a separate thread for refreshing data periodically
        refresh_thread = threading.Thread(target=self.refresh_data)
        refresh_thread.daemon = True
        refresh_thread.start()

        # Hurricane season start/end announcements (fires on June 1 and Nov 30)
        if self.tropical_weather:
            season_thread = threading.Thread(target=self._hurricane_season_announcer)
            season_thread.daemon = True
            season_thread.start()

        # Keep the main thread alive
        while True:
            time.sleep(1)
            continue

def load_args():
    parser = argparse.ArgumentParser(description="Meshbot a bot for Meshtastic devices")
    parser.add_argument("--port", type=str, help="Specify the serial port to probe")
    parser.add_argument("--db", type=str, help="Specify DB: mpowered or liam")
    parser.add_argument("--host", type=str, help="Specify meshtastic host (IP address) if using API")

    return parser.parse_args()

def main(args):

    cwd = Path.cwd()
    ip_host = None
    serial_ports = None
    db_mode = None

    if args.port:
        serial_ports = [args.port]
        logger.info(f"Serial port {serial_ports}\n")
    elif args.host:
        ip_host = args.host
        print(ip_host)
        logger.info(f"Meshtastic API host {ip_host}\n")
    else:
        serial_ports = find_serial_ports()
        if serial_ports:
            logger.info("Available serial ports:")
            for port in serial_ports:
                logger.info(port)
            logger.info(
                "Im not smart enough to work out the correct port, please use the --port argument with a relevent meshtastic port"
            )
        else:
            logger.info("No serial ports found.")
        exit(0)

    if args.db:
        if args.db.lower() == "mpowered":
            db_mode = str(cwd) + "/db/nodes.db"
            logger.info(f"Setting DB to mpowered data: {db_mode}")
        if args.db.lower() == "liam":
            db_mode = str(cwd) + "/db/nodes2.db"
            logger.info(f"Setting DB to Liam Cottle data: {db_mode}")
    else:
        logger.info(f"Default DB")

    meshbot = MeshBot(
        ip_host = ip_host,
        serial_port = serial_ports,
        db = db_mode,
    )

    meshbot.run()

if __name__ == "__main__":
    args = load_args()
    main(args)

