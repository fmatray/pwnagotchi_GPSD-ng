# Based on the GPS/GPSD plugin from:
# - https://github.com/evilsocket
# - https://github.com/kellertk/pwnagotchi-plugin-gpsd
# - https://github.com/nothingbutlucas/pwnagotchi-plugin-gpsd
# - https://gpsd.gitlab.io/gpsd/index.html
#
# Install :
# - Install and configure gpsd
# - copy this plugin to custom plugin
#
# Config.toml:
# main.plugins.gpsd.enabled = false
# main.plugins.gpsd.gpsdhost = "127.0.0.1"
# main.plugins.gpsd.gpsdport = 2947
# main.plugins.gpsd.compact_view = true
# main.plugins.gpsd.position = "127,64"


import threading
import json
import logging
import re
import time
from datetime import datetime, UTC
import gps

import pwnagotchi.plugins as plugins
import pwnagotchi.ui.fonts as fonts
from pwnagotchi.ui.components import LabeledValue
from pwnagotchi.ui.view import BLACK


class GPSD(threading.Thread):
    FIXES = {0: "No value", 1: "No fix", 2: "2D fix", 3: "3D fix"}
    DATE_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"

    def __init__(self, gpsdhost, gpsdport):
        super().__init__()
        self.gpsdhost = gpsdhost
        self.gpsdport = gpsdport
        self.session = None
        self.devices = dict()
        self.last_position = None
        self.last_clean = datetime.now(tz=UTC)
        self.lock = threading.Lock()
        self.running = True
        self.connect()

    def connect(self):
        with self.lock:
            logging.info(f"[GPSD-ng] Trying to connect")
            try:
                self.session = gps.gps(
                    host=self.gpsdhost,
                    port=self.gpsdport,
                    mode=gps.WATCH_ENABLE | gps.WATCH_NEWSTYLE,
                )
            except Exception as e:
                logging.error(f"[GPSD-ng] Error updating GPS: {e}")
                self.session = None

    def is_old(self, date, max_seconds=90):
        try:
            d_time = datetime.strptime(date, self.DATE_FORMAT)
            d_time = d_time.replace(tzinfo=UTC)
        except TypeError:
            return None
        delta = datetime.now(tz=UTC) - d_time
        return delta.total_seconds() > max_seconds

    def clean(self):
        if (datetime.now(tz=UTC) - self.last_clean).total_seconds() < 10:
            return
        self.last_clean = datetime.now(tz=UTC)
        logging.debug(f"[GPSD-ng] Start cleaning")
        with self.lock:
            devices_to_clean = []
            for device in filter(lambda x: self.devices[x], self.devices):
                if self.is_old(self.devices[device]["Date"]):
                    devices_to_clean.append(device)
            for device in devices_to_clean:
                self.devices[device] = None
                logging.debug(f"[GPSD-ng] Cleaning {device}")

            if self.last_position and self.is_old(self.last_position["Date"], 120):
                self.last_position = None
                logging.debug(f"[GPSD-ng] Cleaning last position")

    def update(self):
        with self.lock:
            if (
                not self.session.device or self.session.fix.mode < 2
            ):  # Remove positions without fix
                return
            logging.debug(f"[GPSD-ng] Updating data {self.session.device}")
            self.devices[self.session.device] = dict(
                Latitude=self.session.fix.latitude,
                Longitude=self.session.fix.longitude,
                Altitude=(
                    self.session.fix.altMSL if self.session.fix.mode > 2 else None
                ),
                Speed=(
                    self.session.fix.speed * 0.514444
                ),  # speed in knots converted in m/s
                Date=self.session.fix.time,
                Updated=self.session.fix.time,  # Wigle plugin
                Mode=self.session.fix.mode,
                Fix=self.FIXES.get(self.session.fix.mode, "Mode error"),
                Sats=len(self.session.satellites),
                Sats_Valid=self.session.satellites_used,
                Device=self.session.device,
                Accuracy=self.session.fix.sep,  # Wigle plugin, we use GPS EPE
            )

    def run(self):
        logging.info(f"[GPSD-ng] Starting GPSD reading loop")
        while self.running:
            self.clean()
            if not self.session:
                self.connect()
            elif self.session.read() == 0:
                self.update()
            else:
                logging.info("[GPSD-ng] Closing connection")
                self.session.close()
                self.session = None
                time.sleep(1)

    def join(self, timeout=None):
        self.running = False
        super().join(timeout)

    def get_position(self):
        with self.lock:
            # Filter devices without coords
            devices = filter(lambda x: x[1], self.devices.items())
            # Sort by best positionning and most recent
            devices = sorted(
                devices,
                key=lambda x: (
                    -x[1]["Mode"],
                    -datetime.strptime(x[1]["Date"], self.DATE_FORMAT).timestamp(),
                ),
            )
            try:
                coords = devices[0][1]  # Get first and best element
                self.last_position = coords
                return coords
            except IndexError:
                logging.info(
                    f"[GPSD-ng] No data, using last position: {self.last_position}"
                )
            return self.last_position


class GPSD_ng(plugins.Plugin):
    __author__ = "@fmatray"
    __version__ = "1.1.0"
    __license__ = "GPL3"
    __description__ = "Use GPSD server to save coordinates on handshake. Can use mutiple gps device (gps modules, USB dongle, phone, etc.)"
    LINE_SPACING = 10
    LABEL_SPACING = 0

    def __init__(self):
        self.gpsd = None
        self.options = dict()
        self.ui_counter = 0
        self.running = False

    @staticmethod
    def check_coords(coords):
        return coords and all(  # avoid 0.000... measurements
            [coords["Latitude"], coords["Longitude"]]
        )

    def on_loaded(self):
        if not self.options["gpsdhost"]:
            logging.warning("no GPS detected")
            return
        try:
            self.gpsd = GPSD(self.options["gpsdhost"], self.options["gpsdport"])
            self.gpsd.start()
            logging.info("[GPSD-ng] plugin loaded")
        except Exception as e:
            logging.error(f"[GPSD-ng] Error on loading. Trying later...")
        self.running = True

    def on_unload(self, ui):
        self.gpsd.join()
        with ui._lock:
            for element in ["latitude", "longitude", "altitude", "coordinates"]:
                try:
                    ui.remove_element(element)
                except KeyError:
                    pass

    def on_ready(self, agent):
        if not self.running:
            return
        try:
            logging.info(f"[GPSD-ng] Disabling bettercap's gps module")
            agent.run("gps off")
        except Exception as e:
            logging.info(f"[GPSD-ng] Bettercap gps was already off.")

    # on_internet_available() is used to update GPS to bettercap.
    # Not ideal but I can't find another function to do it.
    def on_internet_available(self, agent):
        coords = self.gpsd.get_position()
        if not self.check_coords(coords):
            return
        try:
            agent.run(f"set gps.set {coords['Latitude']} {coords['Longitude']}")
        except Exception as e:
            logging.error(f"[GPSD-ng] Cannot set bettercap GPS: {e}")

    def on_handshake(self, agent, filename, access_point, client_station):
        if not self.running:
            return
        coords = self.gpsd.get_position()
        logging.info(f"[GPSD-ng] Coordinates: {coords}")
        if not self.check_coords(coords):
            logging.info("[GPSD-ng] not saving GPS: no fix")
            return

        try:
            agent.run(f"set gps.set {coords['Latitude']} {coords['Longitude']}")
        except Exception as e:
            logging.error(f"[GPSD-ng] Cannot set bettercap GPS: {e}")

        gps_filename = filename.replace(".pcap", ".gps.json")
        logging.info(f"[GPSD-ng] saving GPS to {gps_filename} ({coords})")
        try:
            with open(gps_filename, "w+t") as fp:
                json.dump(coords, fp)
        except Exception as e:
            logging.error(f"[GPSD-ng] Error on saving gps coordinates: {e}")

    def on_ui_setup(self, ui):
        line_spacing = int(self.options.get("linespacing", self.LINE_SPACING))
        try:
            pos = self.options["position"].split(",")
            pos = [int(x.strip()) for x in pos]
            lat_pos = (pos[0] + 5, pos[1])
            lon_pos = (pos[0], pos[1] + line_spacing)
            alt_pos = (pos[0] + 5, pos[1] + (2 * line_spacing))
            spe_pos = (pos[0] + 5, pos[1] + (3 * line_spacing))
        except KeyError:
            if ui.is_waveshare_v2():
                lat_pos = (127, 64)
                lon_pos = (122, 74)
                alt_pos = (127, 84)
                spe_pos = (127, 94)
            elif ui.is_waveshare_v1():
                lat_pos = (130, 60)
                lon_pos = (130, 70)
                alt_pos = (130, 80)
                spe_pos = (130, 90)
            elif ui.is_inky():
                lat_pos = (127, 50)
                lon_pos = (122, 60)
                alt_pos = (127, 70)
                spe_pos = (127, 80)
            elif ui.is_waveshare144lcd():
                lat_pos = (67, 63)
                lon_pos = (67, 73)
                alt_pos = (67, 83)
                spe_pos = (67, 93)
            elif ui.is_dfrobot_v2():
                lat_pos = (127, 64)
                lon_pos = (122, 74)
                alt_pos = (127, 84)
                spe_pos = (127, 94)
            else:
                lat_pos = (127, 41)
                lon_pos = (122, 51)
                alt_pos = (127, 61)
                spe_pos = (127, 71)

        if self.options["compact_view"]:
            ui.add_element(
                "coordinates",
                LabeledValue(
                    color=BLACK,
                    label="coords",
                    value="-",
                    position=lat_pos,
                    label_font=fonts.Small,
                    text_font=fonts.Small,
                    label_spacing=0,
                ),
            )
            return
        for key, label, label_pos in [
            ("latitude", "lat:", lat_pos),
            ("longitude", "long:", lon_pos),
            ("altitude", "alt:", alt_pos),
            ("speed", "spe:", spe_pos),
        ]:
            ui.add_element(
                key,
                LabeledValue(
                    color=BLACK,
                    label=label,
                    value="-",
                    position=label_pos,
                    label_font=fonts.Small,
                    text_font=fonts.Small,
                    label_spacing=self.LABEL_SPACING,
                ),
            )

    def lost_mode(self, ui, coords):
        with ui._lock:
            ui.set("status", "Where am I???")
            if self.ui_counter == 1:
                ui.set("face", "(O_o )")
            elif self.ui_counter == 2:
                ui.set("face", "( o_O)")

            if self.options["compact_view"]:
                ui.set("coordinates", "No Data")
            else:
                for i in ["latitude", "longitude", "altitude", "speed"]:
                    ui.set(i, "-")

    @staticmethod
    def calculate_position(coords):
        if coords["Latitude"] < 0:
            lat = f"{-coords['Latitude']:4.6f}S"
        else:
            lat = f"{coords['Latitude']:4.6f}N"
        if coords["Longitude"] < 0:
            long = f"{-coords['Longitude']:4.6f}W"
        else:
            long = f"{coords['Longitude']:4.6f}E"

        alt, spd = "", ""
        if coords["Altitude"] != None:
            alt = f"{int(coords['Altitude'])}m"
        if coords["Speed"] != None:
            spd = f"{coords['Speed']:.1f}m/s"
        return lat, long, alt, spd

    def display_face(self, ui):
        with ui._lock:
            if self.ui_counter == 1:
                ui.set("face", "(•_• )")
            elif self.ui_counter == 2:
                ui.set("face", "( •_•)")

    def compact_view(self, ui, coords):
        with ui._lock:
            if self.ui_counter == 1:
                msg = f"{coords['Fix']} ({coords['Sats_Valid']}/{coords['Sats']} Sats)"
                ui.set("coordinates", msg)
                return
            if self.ui_counter == 2:
                dev = re.search(r"(^tcp|^udp|tty.*)", coords["Device"], re.IGNORECASE)
                dev = dev[0] if dev else "No dev"
                ui.set("coordinates", f"Dev:{dev}")
                return
            lat, long, alt, spd = self.calculate_position(coords)
            if self.ui_counter == 3:
                ui.set("coordinates", f"Speed:{spd} Alt:{alt}")
                return
            ui.set("coordinates", f"{lat},{long}")

    def full_view(self, ui, coords):
        with ui._lock:
            lat, long, alt, spd = self.calculate_position(coords)
            # last char is sometimes not completely drawn ¯\_(ツ)_/¯
            # using an ending-whitespace as workaround on each line
            ui.set("latitude", f"{lat} ")
            ui.set("longitude", f"{long} ")
            ui.set("altitude", f"{alt} ")
            ui.set("speed", f"{spd} ")

    def on_ui_update(self, ui):
        if not self.running:
            return

        self.ui_counter = (self.ui_counter + 1) % 5
        coords = self.gpsd.get_position()

        if not self.check_coords(coords):
            self.lost_mode(ui, coords)
            return

        self.display_face(ui)
        if self.options["compact_view"]:
            self.compact_view(ui, coords)
        else:
            self.full_view(ui, coords)

    def on_webhook(self, path, request):
        from flask import make_response, redirect

        coords = self.gpsd.get_position()
        if not self.check_coords(coords):
            return "<html><head><title>GPSD-ng: Error</title></head><body><code>No Data</code></body></html>"
        url = f"https://www.openstreetmap.org/?mlat={coords['Latitude']}&mlon={coords['Longitude']}&zoom=18"
        response = make_response(redirect(url, code=302))
        return response
