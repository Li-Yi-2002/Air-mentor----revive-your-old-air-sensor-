# Documentation note:
# English comments in this file were generated with AI assistance (OpenAI ChatGPT).
# Air Mentor packet interpretation was informed in part by:
# https://github.com/philippeportesppo/AirMentorPro2_SmartThings
# See README.md for attribution and protocol caveats.

import asyncio
import csv
import math
import os
import struct
from datetime import datetime
from unicodedata import name

from bleak import BleakScanner


# ============================================================
# User configuration
# ============================================================

# Process only BLE devices whose advertised name contains this string.
DEVICE_NAME = "8099-AP"


# ============================================================
# Latest sensor values
# ============================================================

# The two Air Mentor advertisement packet types update different sensor values,
# so a single dictionary stores the most recently received value for each field.
# Fields that have not been received yet are represented by None.
latest = {
    "co2": None,
    "pm25": None,
    "pm10": None,
    "tvoc": None,
    "temperature": None,
    "humidity": None,
    "aqi": None,
    "rssi": None
}




# ============================================================
# Decode Air Mentor Manufacturer Specific Data
# ============================================================

def decode_airmentor(company_id: int,payload: bytes):

    # Bleak exposes BLE Manufacturer Specific Data as:
    #   company_id : 16-bit integer
    #   payload    : corresponding bytes payload
    #
    # In the currently observed 8099-AP packets:
    #   company_id = 0x5111 -> packet type 0x11
    #   company_id = 0x5112 -> packet type 0x12
    #
    # "& 0xFF" does not convert decimal to hexadecimal.
    # It applies a bit mask that keeps only the lowest 8 bits of company_id,
    # so 0x5111 / 0x5112 become packet types 0x11 / 0x12.
    packet_type = company_id & 0xFF


    # Raw Manufacturer ID, packet type, and payload can be inspected here
    # for BLE packet validation and further reverse engineering.


    # ========================================================
    # Packet type 0x11 / 0x21
    #
    # This program currently decodes the first 6 bytes of the payload:
    #   byte 0-1 : CO2
    #   byte 2-3 : PM2.5
    #   byte 4-5 : PM10
    #
    # Each field is a big-endian unsigned 16-bit integer.
    # The 8099-AP has been observed to transmit a 12-byte payload;
    # the remaining bytes are kept as Extra without assigning a physical meaning here.
    # ========================================================

    if packet_type in (0x11, 0x21):

        # ">HHH" requires exactly 6 bytes, so shorter payloads cannot be decoded.
        if len(payload) < 6:


            return


        # payload[:6] selects only the first 6 bytes of the known layout.
        # struct format string:
        #   > : big-endian
        #   H : unsigned short, 2 bytes
        #   HHH : three unsigned 16-bit integers, 6 bytes total
        co2, pm25, pm10 = struct.unpack(">HHH",payload[:6])


        # Update latest with the values decoded from this packet;
        # sensor fields not present in this packet keep their previously received values.
        latest["co2"] = co2
        latest["pm25"] = pm25
        latest["pm10"] = pm10




        # Preserve the remaining bytes that are not decoded by this version.
        # These bytes are not discarded; they are temporarily kept as raw data.
        if len(payload) > 6:

            extra = payload[6:]




    # ========================================================
    # Packet type 0x12 / 0x22
    #
    # This program currently decodes the first 8 bytes of the payload:
    #   byte 0-1 : TVOC
    #   byte 2-3 : raw temperature
    #   byte 4   : temperature calibration/configuration byte
    #   byte 5   : humidity
    #   byte 6-7 : Air Mentor AQI / IAQ index
    #
    # The 8099-AP has been observed to transmit a 12-byte payload;
    # Bytes after byte 7 are currently kept as Extra.
    # ========================================================

    elif packet_type in (0x12, 0x22):

        # At least 8 bytes are required for the known fields.
        if len(payload) < 8:


            return


        # TVOC: read bytes 0-1 as a big-endian unsigned 16-bit integer.
        tvoc = int.from_bytes(
            payload[0:2],
            byteorder="big",
            signed=False
        )


        # Raw temperature: read bytes 2-3.
        # The conversion currently follows the Air Mentor community decoder:
        #   T [°C] = (raw - 4000) * 0.01
        temp_raw = int.from_bytes(payload[2:4],byteorder="big",signed=False)

        temperature = (
            temp_raw - 4000
        ) * 0.01

        # Byte 4 was used as a temperature calibration offset in the legacy decoder.
        # For this 8099-AP unit, directly applying the legacy formula produced
        # clearly implausible ambient temperatures, so this script keeps only the raw value
        # and does not use it to modify temperature or humidity.
        temp_delta_raw = payload[4]

        # Humidity: byte 5 is currently used directly as the %RH value.
        # This version does not apply the legacy Air Mentor Magnus humidity compensation formula.
        humidity_raw = payload[5]

        # AQI / IAQ index: read bytes 6-7 as a big-endian 16-bit integer.
        # It is currently treated as Air Mentor's own air-quality index
        # rather than being directly equated with official outdoor AQI definitions such as the EPA AQI.
        aqi = int.from_bytes(payload[6:8],byteorder="big",signed=False)

        # Update the latest sensor values provided by this environmental packet.
        latest["tvoc"] = tvoc

        latest["temperature"] = (temperature)


        latest["humidity"] = humidity_raw

        latest["aqi"] = aqi


        # The decoded 0x12 / 0x22 packet values are written directly to latest.




        # This byte is currently retained only as a decimal raw value
        # and is not converted into a calibrated ambient temperature.





        # Preserve data after byte 7 whose meaning has not yet been confirmed; it is not output currently.
        if len(payload) > 8:

            extra = payload[8:]





    # If the lowest 8 bits of company_id do not match a currently supported packet type,
    # do not attempt to decode the payload using the known layouts.
    else:
        pass



# ============================================================
# BLE advertisement callback
# ============================================================

def detection_callback(device,advertisement_data):

    # The callback is invoked whenever Bleak receives a BLE advertisement;
    # the advertisement may come from the 8099-AP or from another nearby BLE device.
    #
    # Prefer the local_name carried by the advertisement itself;
    # if that advertisement has no local_name, fall back to device.name;
    # if neither is available, use an empty string to avoid None during string checks.
    name = (advertisement_data.local_name or device.name or "")


    # Process only devices whose name contains DEVICE_NAME.
    # Return immediately for other BLE devices and end this callback invocation.
    if DEVICE_NAME not in name:
        return


    # RSSI = Received Signal Strength Indicator,
    # representing the BLE signal strength received by the Raspberry Pi, in dBm.
    # Values are usually negative; values closer to 0 indicate a stronger received signal.
    latest["rssi"] = (advertisement_data.rssi)




    # advertisement_data.manufacturer_data is a dictionary:
    #
    # {
    #     company_id: payload,
    #     ...
    # }
    #
    # for example:
    # {
    #     20753: b'...'
    # }
    #
    # items() yields each (company_id, payload) pair,
    # which is then passed to decode_airmentor() for packet-type detection and decoding.
    for (company_id,payload) in advertisement_data.manufacturer_data.items():
        decode_airmentor(company_id,payload)



# ============================================================
# Periodically write latest values to a daily CSV file
# ============================================================

def save_latest_to_csv():

    # Retrieve the current time before every write so that after midnight
    # the output filename automatically switches to the new date.
    now = datetime.now()

    # Directory containing the currently running Python script.
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # for example:2026-08-18.csv
    csv_filename = now.strftime("%Y-%m-%d") + ".csv"
    csv_dir = os.path.join('/home','pi5','Desktop','Synology','Air_pi5','data')
    try:
        os.stat(csv_dir)
    except:
        os.mkdir(csv_dir)
    csv_path = os.path.join(csv_dir, csv_filename)
    
    # Write the header if the file does not exist or exists but is empty.
    write_header = (
        not os.path.exists(csv_path)
        or os.path.getsize(csv_path) == 0
    )

    # Use append mode "a":
    # existing data is preserved and each new record is appended to the end of the CSV file.
    with open(
        csv_path,
        mode="a",
        newline="",
        encoding="utf-8"
    ) as csv_file:

        writer = csv.writer(csv_file)

        if write_header:
            writer.writerow(
                [
                    "time",
                    "co2",
                    "pm25",
                    "pm10",
                    "tvoc",
                    "temperature",
                    "humidity",
                    "aqi",
                    "rssi"
                ]
            )

        # Store only the time of day (hour, minute, second);
        # the date is already encoded in the CSV filename.
        #
        # If a latest field has not received a BLE value yet when the program starts,
        # write an empty CSV field instead of the string "None".
        writer.writerow(
            [
                now.strftime("%H:%M:%S"),
                "" if latest["co2"] is None else latest["co2"],
                "" if latest["pm25"] is None else latest["pm25"],
                "" if latest["pm10"] is None else latest["pm10"],
                "" if latest["tvoc"] is None else latest["tvoc"],
                "" if latest["temperature"] is None else latest["temperature"],
                "" if latest["humidity"] is None else latest["humidity"],
                "" if latest["aqi"] is None else latest["aqi"],
                "" if latest["rssi"] is None else latest["rssi"]
            ]
        )
    print(
            f"CSV saved: {now.strftime('%H:%M:%S')} "
            f"-> {csv_filename}"
        )



# ============================================================
# Main BLE scanning loop
# ============================================================

async def main():





    # Create a BleakScanner and register detection_callback.
    # This only passes the callback function to the scanner;
    # the callback is not executed immediately when the scanner is created.
    scanner = BleakScanner(
        detection_callback=
        detection_callback
    )


    # Start continuous BLE scanning.
    # Whenever Bleak receives an advertisement afterward,
    # the previously registered detection_callback may be invoked.
    await scanner.start()


    try:

        # The scanner continues receiving BLE advertisements in the background.
        #
        # main() only waits for the next exact 30-second boundary here,
        # for example:
        #   10:24:30
        #   10:25:00
        #   10:25:30
        #   10:26:00
        #
        # While awaiting, control is returned to asyncio,
        # so Bleak can continue invoking detection_callback(),
        # and latest continues to update without BLE scanning being blocked by CSV logging.
        while True:

            now = datetime.now()

            # Calculate the time until the next :00 or :30 second boundary.
            seconds_until_next_log = (
                30
                - (now.second % 30)
                - now.microsecond / 1_000_000
            )

            await asyncio.sleep(seconds_until_next_log)

            # Append the values currently stored in latest to today's CSV file.
            try:
                save_latest_to_csv()
                
            except PermissionError:
                print("CSV is currently locked. Skip this record.")

    finally:

        # Attempt to stop the BLE scanner whether the program exits normally or due to an exception.
        await scanner.stop()


# ============================================================
# Program entry point
# ============================================================

if __name__ == "__main__":

    try:

        # Create and run the asyncio event loop, starting from main().
        asyncio.run(
            main()
        )


    except KeyboardInterrupt:
        pass

        # Exit silently when the program is interrupted with Ctrl+C.