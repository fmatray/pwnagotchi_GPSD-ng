# GPSD-ng
Use GPSD server to retreive and save coordinates on handshake. Can use mutiple gps device (gps modules, USB dongle, phone, etc.)

![Front image of pwnagotchi](pwnagotchi.jpeg)

__Advantages__:
- GPS configuration independant from pwnagotchi
- Early position polling
- No position lost on bettercap/pwnagotchi restarts
- High compatibility (device, protocol, vendor, version): NMEA/ublox modules (Serial), USB modules, Android/IPhone
- Non blocking access to GPS information, no deadlock, 
- GPS hotplugin
- Compatibility with other applications like chrony
- Compatible with NTRIP/RTK/RTCM

__Exemple__:\
GPS module/dongle and/or Phone (IOS/Android) ------> GPSD ------> GPSD-ng ------> Pwnagotchi

# Install
- Install gpsd:
  - "apt-get install gpsd gpsd-clients" or compile from gpsd repository
  - Be sure to have the native gpsd python library installed
- Configure GPSD (/etc/default/gpsd):
  - __GPS module only__
    - DEVICES="/dev/ttyS0"
    - GPSD_OPTIONS="-n -s 38400" # check your baudrate
  - __Phone only__
    - DEVICES="tcp://172.20.10.1:4352"
    - GPSD_OPTIONS="-n"
  - __GPS module and phone__
    - DEVICES="/dev/ttyS0"
    - GPSD_OPTIONS="-n -s 38400 tcp://172.20.10.1:4352" # check your baudrate
- If you use a phone:
  - Setup bt-tether and check
  - Install a GPS app:
    - __Android__(not tested):
      - BlueNMEA: https://github.com/MaxKellermann/BlueNMEA
      - gpsdRealay: https://github.com/project-kaat/gpsdRelay
    - __IOS__: GPS2IP (tested but paid app)
      - Set "operate in background mode"
      - Set "Connection Method" -> "Socket" -> "Port Number" -> 4352
      - Set "Network selection" -> "Hotspot"
- Check your gpsd configuration with gpsmon or cgps
- Copy gpsd-ng.py into your custom plugin directory and configure

# Config.toml
```
main.plugins.gpsd.enabled = false
main.plugins.gpsd.gpsdhost = "127.0.0.1"
main.plugins.gpsd.gpsdport = 2947
main.plugins.gpsd.compact_view = true
main.plugins.gpsd.position = "127,64"
```

# Usage
## Retreive GPS Position
This plugin can be used for wardriving with the wigle plugin, for example.
- __Outdoor__: GPS module/dongle works fine. 
- __Indoor__: is the GPS module/dongle doesn't work, you can use your phone.

This plugin select the most accurate (base on fix information) and most recent position.

## Improve positioning with RTCM
If you have a GPs module or dongle with RTCM capabilities, you can activate with GPSD.
Exemple with a Ublox (firmware 34.10) and GPSD 3.25:
- ublox setup:
  - ubxtool -p MON-VER | grep PROT  -> retreive ublox version XX.YY (34.10 for me)
  - export UBXOPTS="-P XX.YY -v 2"
  - ubxtool -e RTCM3
- GPSD setup:
  - Find a local (< 30km) RTK provider (https://rtkdata.online/network)
  - You need host/port and mountpoint information
  - Check with the following command. It should stream binary data.\
curl -v -H "Ntrip-Version: Ntrip/2.0" -H "User-Agent: NTRIP theSoftware/theRevision" http://[user:pwd@]host:2101/mountpoint -o -
  - Add "ntrip://[user:pwd@]host:2101/mountpoint" to GPSD configuration
  - Now GPSD command should look like with ps: 'gpsd -n ntrip://caster.centipede.fr:2101/RICE -s 38400 /dev/ttyS0'

Of course, you can still append your phone 'gpsd -N -D3 ntrip://caster.centipede.fr:2101/RICE -s 38400 /dev/ttyS0 tcp://172.20.10.1:4352'
More info on: https://gpsd.gitlab.io/gpsd/ubxtool-examples.html#_survey_in_and_rtcm

## UI
The "compact_view" option show gps informations, on one line, in rotation:
- Lat,Long
- Fix information
- Device source
- Speed, (Alt) # Speed is in metters/s and Alt is in meters

If the "compact_view" is not set, information are displayed like gps_more.

## Handshake
- Set gps position to bettercap (it's also done on internet_available)
- Saves position informations into "gps.json" (compatible with Wigle and webgpsmap)

## Bettercap
Gps option is set to off. Position is update in Bettercap everytime a handshake is captured.

# TODO
- [ ] Run around the World!
 
# Based on:
- https://github.com/evilsocket
- https://github.com/kellertk/pwnagotchi-plugin-gpsd
- https://github.com/nothingbutlucas/pwnagotchi-plugin-gpsd
- https://gpsd.gitlab.io/gpsd/index.html

Have fun !
