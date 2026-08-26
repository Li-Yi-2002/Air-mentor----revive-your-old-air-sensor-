# Air Mentor 8099-AP BLE CSV Logger

A lightweight Python logger for receiving BLE advertisements from an **Air Mentor 8099-AP**, decoding selected Manufacturer Specific Data fields, keeping the latest sensor values in memory, and appending a snapshot to a daily CSV file every 30 seconds.

> **AI-generated / AI-assisted documentation notice**  
> This README and the English comments in `airmentor_ble_logger.py` were generated with assistance from **OpenAI ChatGPT**. The program logic, device observations, and hardware-specific behavior should be verified against your own Air Mentor unit. AI-generated documentation may contain mistakes.

## What this script does

The script:

- scans BLE advertisements continuously with [`bleak`](https://github.com/hbldh/bleak);
- filters devices whose advertised name contains `8099-AP`;
- reads BLE Manufacturer Specific Data;
- decodes selected Air Mentor fields from the observed packet layouts;
- stores the most recently received value for each sensor;
- records a snapshot at every `:00` and `:30` second boundary;
- creates one CSV file per day.

The current CSV columns are:

```text
time,co2,pm25,pm10,tvoc,temperature,humidity,aqi,rssi
```

## Requirements

- Python 3
- Linux / Raspberry Pi with working Bluetooth LE
- Python package:
  - `bleak`

Install Bleak with:

```bash
python3 -m pip install bleak
```

Depending on your Raspberry Pi OS / Python installation, package-management restrictions may require a different installation method.

## Configuration

The target BLE name is set near the top of the script:

```python
DEVICE_NAME = "8099-AP"
```

The CSV directory is currently hard-coded as:

```text
/home/pi5/Desktop/Synology/Air_pi5/data
```

Change `csv_dir` in `save_latest_to_csv()` if your storage location is different.

## Running

```bash
python3 airmentor_ble_logger.py
```

Stop the logger with:

```text
Ctrl+C
```

## Logging behavior

BLE scanning runs continuously.

The script writes one row at the next exact 30-second boundary, for example:

```text
10:24:30
10:25:00
10:25:30
10:26:00
```

The file name is based on the local date:

```text
2026-08-26.csv
```

If a sensor value has not been received yet, the corresponding CSV cell is left empty.

If the CSV file is temporarily locked and Python raises `PermissionError`, that record is skipped.

## Observed packet decoding

This project is based on **reverse-engineered / experimentally observed BLE advertisements**, not an official Air Mentor protocol specification.

### Packet type `0x11` / `0x21`

The script currently interprets the first 6 payload bytes as:

| Bytes | Field | Format |
|---|---|---|
| 0-1 | CO2 | big-endian unsigned 16-bit integer |
| 2-3 | PM2.5 | big-endian unsigned 16-bit integer |
| 4-5 | PM10 | big-endian unsigned 16-bit integer |

Additional bytes are currently preserved internally as undecoded extra data.

### Packet type `0x12` / `0x22`

The script currently interprets the first 8 payload bytes as:

| Bytes | Field | Interpretation |
|---|---|---|
| 0-1 | TVOC | big-endian unsigned 16-bit integer |
| 2-3 | Raw temperature | converted with `(raw - 4000) * 0.01` |
| 4 | Temperature calibration/configuration byte | retained as raw value only |
| 5 | Humidity | currently used directly as `%RH` |
| 6-7 | AQI / IAQ | Air Mentor-specific air-quality index |

The value labeled `AQI` / `IAQ` here should **not** automatically be treated as equivalent to an official outdoor AQI system such as the U.S. EPA AQI.

## Difference from the legacy community decoder

The historical Air Mentor Pro 2 community implementation by Philippe Portes was used as an important reference for understanding the BLE payload layout and the raw-temperature conversion.

That legacy implementation also applied:

- a temperature calibration offset; and
- a Magnus-type humidity compensation.

This logger **does not currently apply those two corrections** because direct use of the legacy correction on the tested 8099-AP unit produced implausible ambient values. Instead, byte 4 is retained as a raw calibration/configuration value and byte 5 is used directly as the current humidity value.

The manufacturer IDs and packet behavior observed on this 8099-AP should therefore be treated as **device-specific experimental observations**, not a guaranteed protocol definition for every Air Mentor model or firmware version.

## Reference / Attribution

The BLE field interpretation and temperature conversion were informed in part by the following open-source project:

> Philippe Portes, **AirMentorPro2_SmartThings**, GitHub repository.  
> https://github.com/philippeportesppo/AirMentorPro2_SmartThings  
> Specific legacy decoder:  
> https://github.com/philippeportesppo/AirMentorPro2_SmartThings/blob/master/airmentorpro2.py  
> Accessed: 2026-08-26.

The referenced `airmentorpro2.py` source file contains an **Apache License 2.0** notice. If you directly copy or adapt code from that upstream source, retain any attribution and license notices required by the upstream license.

## AI disclosure

Documentation work for this version was AI-assisted:

- English code comments: generated/revised with OpenAI ChatGPT.
- This README: generated with OpenAI ChatGPT.
- Device decoding claims: based on the program's existing logic, observed device behavior, and the cited community decoder; they are not presented as an official manufacturer specification.

## Notes

- `latest` stores the most recently received value from each packet type, so a CSV row can combine values that arrived in separate BLE advertisements.
- RSSI is measured from the advertisement received by the Raspberry Pi and is stored in dBm.
- The script currently ignores unsupported packet types.
- Undecoded extra bytes are intentionally not assigned physical meanings until their definitions are verified.

## Disclaimer

This is an experimental data logger for reverse-engineering and personal instrumentation. Validate sensor values independently before using the data for safety-critical, regulatory, medical, or environmental-compliance decisions.
