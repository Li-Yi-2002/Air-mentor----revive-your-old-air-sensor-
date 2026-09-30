import asyncio
import math
import struct
from unicodedata import name

from bleak import BleakScanner


# ============================================================
# 使用者設定
# ============================================================

# 只處理 BLE 廣播名稱中包含此字串的裝置。
DEVICE_NAME = "8099-AP"


# ============================================================
# 最新感測值
# ============================================================

# 兩種 Air Mentor 廣播封包會分開更新不同感測值，
# 因此使用同一個 dictionary 保存各欄位「最近一次收到的值」。
# 尚未收到的欄位以 None 表示。
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
# 顯示目前已取得的全部感測值
# ============================================================

def print_values():

    print()
    print("======================================")
    print("       Air Mentor 8099-AP")
    print("======================================")

    # 只有欄位已經被某個 BLE 封包更新過時才顯示，
    # 避免程式剛啟動時印出 None。
    if latest["co2"] is not None:
        print(
            f"CO2               : "
            f"{latest['co2']} ppm"
        )

    if latest["pm25"] is not None:
        print(
            f"PM2.5             : "
            f"{latest['pm25']} ug/m3"
        )

    if latest["pm10"] is not None:
        print(
            f"PM10              : "
            f"{latest['pm10']} ug/m3"
        )

    if latest["tvoc"] is not None:
        print(
            f"TVOC              : "
            f"{latest['tvoc']}"
        )

    if latest["temperature"] is not None:
        print(
            f"Temperature       : "
            f"{latest['temperature']:.2f} C"
        )

    if latest["humidity"] is not None:
        print(
            f"Humidity          : "
            f"{latest['humidity']:.1f} %"
        )

    if latest["aqi"] is not None:
        print(
            f"AQI               : "
            f"{latest['aqi']}"
        )

    if latest["rssi"] is not None:
        print(
            f"RSSI              : "
            f"{latest['rssi']} dBm"
        )

    print("======================================")
    print()


# ============================================================
# 解碼 Air Mentor 的 Manufacturer Specific Data
# ============================================================

def decode_airmentor(company_id: int,payload: bytes):

    # Bleak 將 BLE Manufacturer Specific Data 拆成：
    #   company_id : 16-bit 整數
    #   payload    : 對應的 bytes 資料
    #
    # 在目前觀察到的 8099-AP 封包中：
    #   company_id = 0x5111 -> packet type 0x11
    #   company_id = 0x5112 -> packet type 0x12
    #
    # 「& 0xFF」不是把十進位轉成十六進位，
    # 而是利用 bit mask 只保留 company_id 的最低 8 bits，
    # 因此可從 0x5111 / 0x5112 取得 0x11 / 0x12。
    packet_type = company_id & 0xFF


    # 顯示原始 Manufacturer ID、封包類型與 payload，
    # 方便檢查 BLE 封包及進一步 reverse engineering。
    print(
        f"Company ID: 0x{company_id:04X} "
        f"| Packet type: 0x{packet_type:02X} "
        f"| Payload: {payload.hex()}"
    )


    # ========================================================
    # Packet type 0x11 / 0x21
    #
    # 目前程式解析 payload 前 6 bytes：
    #   byte 0-1 : CO2
    #   byte 2-3 : PM2.5
    #   byte 4-5 : PM10
    #
    # 每個欄位都是 big-endian unsigned 16-bit integer。
    # 8099-AP 實際可收到 12-byte payload；
    # 後續 bytes 目前保留為 Extra，不在此處指定物理意義。
    # ========================================================

    if packet_type in (0x11, 0x21):

        # >HHH 需要剛好 6 bytes，因此長度不足時不能解碼。
        if len(payload) < 6:

            print(
                "Warning: particle packet "
                "is too short."
            )

            return


        # payload[:6] 只取已知格式的前 6 bytes。
        # struct 格式字串：
        #   > : big-endian
        #   H : unsigned short，2 bytes
        #   HHH : 三個 16-bit 無號整數，共 6 bytes
        co2, pm25, pm10 = struct.unpack(">HHH",payload[:6])


        # 將此封包取得的數值更新到 latest；
        # 其他感測欄位則保留前一次接收到的值。
        latest["co2"] = co2
        latest["pm25"] = pm25
        latest["pm10"] = pm10


        print()
        print("--- CO2 / Particle packet ---")
        print(f"CO2   : {co2} ppm")
        print(f"PM2.5 : {pm25} ug/m3")
        print(f"PM10  : {pm10} ug/m3")


        # 保存並顯示尚未在此版本程式中解析的後續 bytes。
        # 這些 bytes 不是被丟棄，而是暫時以十六進位原始資料保留。
        if len(payload) > 6:

            extra = payload[6:]

            print(f"Extra : {extra.hex()}")

        print_values()


    # ========================================================
    # Packet type 0x12 / 0x22
    #
    # 目前程式解析 payload 前 8 bytes：
    #   byte 0-1 : TVOC
    #   byte 2-3 : raw temperature
    #   byte 4   : temperature calibration/configuration byte
    #   byte 5   : humidity
    #   byte 6-7 : Air Mentor AQI / IAQ index
    #
    # 8099-AP 實際可收到 12-byte payload；
    # byte 8 之後目前保留為 Extra。
    # ========================================================

    elif packet_type in (0x12, 0x22):

        # 已知欄位至少需要前 8 bytes。
        if len(payload) < 8:

            print(
                "Warning: environment packet "
                "is too short."
            )

            return


        # TVOC：取 byte 0-1，依 big-endian 讀成 16-bit 無號整數。
        tvoc = int.from_bytes(
            payload[0:2],
            byteorder="big",
            signed=False
        )


        # Raw temperature：取 byte 2-3。
        # 目前沿用 Air Mentor 社群 decoder 的換算：
        #   T [°C] = (raw - 4000) * 0.01
        temp_raw = int.from_bytes(payload[2:4],byteorder="big",signed=False)

        temperature = (
            temp_raw - 4000
        ) * 0.01

        # byte 4 在舊版 decoder 中曾被當作溫度校正量使用。
        # 但對目前這台 8099-AP，實測若直接套用舊公式會得到
        # 明顯不合理的環境溫度，因此此程式只保留並顯示 raw value，
        # 不使用它修改 temperature 或 humidity。
        temp_delta_raw = payload[4]

        # Humidity：byte 5 直接作為目前的 %RH 數值。
        # 這個版本不套用舊版 Air Mentor 的 Magnus 濕度補償公式。
        humidity_raw = payload[5]

        # AQI / IAQ index：byte 6-7，以 big-endian 16-bit 整數讀取。
        # 目前將它視為 Air Mentor 自己的空氣品質指標，
        # 不直接等同於 EPA 等官方戶外 AQI 定義。
        aqi = int.from_bytes(payload[6:8],byteorder="big",signed=False)

        # 更新此環境封包所提供的最新感測值。
        latest["tvoc"] = tvoc

        latest["temperature"] = (temperature)


        latest["humidity"] = humidity_raw

        latest["aqi"] = aqi


        # 顯示本次 0x12 / 0x22 封包的解碼結果。
        print()
        print("--- Environment packet ---")

        print(
            f"TVOC        : {tvoc}"
        )

        print(
            f"Temp raw    : "
            f"0x{temp_raw:04X}"
        )

        print(
            f"Temperature : "
            f"{temperature:.2f} C"
        )

        # 目前僅顯示此 byte 的十進位 raw value，
        # 不將它換算成「校正後環境溫度」。
        print(
            f"Temp delta  : "
            f"{temp_delta_raw}"
        )


        print(
            f"Humidity    : "
            f"{humidity_raw:.1f} %"
        )

        print(
            f"AQI         : "
            f"{aqi}"
        )


        # 保存並顯示 byte 8 之後尚未確認定義的資料。
        if len(payload) > 8:

            extra = payload[8:]

            print(
                f"Extra       : "
                f"{extra.hex()}"
            )


        print_values()


    # company_id 的低 8 bits 若不是目前支援的 packet type，
    # 則不嘗試按照已知格式解碼。
    else:

        print(
            f"Unknown Air Mentor packet type: "
            f"0x{packet_type:02X}"
        )


# ============================================================
# BLE advertisement callback
# ============================================================

def detection_callback(device,advertisement_data):

    # callback 會在 Bleak 掃描到 BLE advertisement 時被呼叫；
    # 掃到的不一定是 8099-AP，也可能是附近其他 BLE 裝置。
    #
    # local_name 優先取 advertisement 本身攜帶的裝置名稱；
    # 若該次廣播沒有 local_name，則嘗試使用 device.name；
    # 兩者都沒有時使用空字串，避免後續字串判斷遇到 None。
    name = (advertisement_data.local_name or device.name or "")


    # 只處理名稱包含 DEVICE_NAME 的裝置。
    # 其他 BLE 裝置直接 return，結束這一次 callback。
    if DEVICE_NAME not in name:
        return


    # RSSI = Received Signal Strength Indicator，
    # 表示 Raspberry Pi 收到此 BLE 廣播時的訊號強度，單位為 dBm。
    # 數值通常為負值，越接近 0 代表接收訊號越強。
    latest["rssi"] = (advertisement_data.rssi)


    print()
    print(
        f"Found {name} "
        f"| RSSI = "
        f"{advertisement_data.rssi} dBm"
    )


    # advertisement_data.manufacturer_data 是 dictionary：
    #
    # {
    #     company_id: payload,
    #     ...
    # }
    #
    # 例如：
    # {
    #     20753: b'...'
    # }
    #
    # items() 每次取出一組 (company_id, payload)，
    # 再交給 decode_airmentor() 判斷封包類型並解碼。
    for (company_id,payload) in advertisement_data.manufacturer_data.items():
        decode_airmentor(company_id,payload)


# ============================================================
# 主 BLE 掃描流程
# ============================================================

async def main():

    print()
    print(
        "Scanning for Air Mentor "
        "8099-AP..."
    )

    print(
        "Press Ctrl+C to stop."
    )

    print()


    # 建立 BleakScanner，並註冊 detection_callback。
    # 這裡只是把 callback 函式交給 scanner；
    # 並不會在建立 scanner 的當下直接執行 callback。
    scanner = BleakScanner(
        detection_callback=
        detection_callback
    )


    # 啟動持續 BLE 掃描。
    # 之後每當 Bleak 收到 advertisement，
    # 就可能觸發前面註冊的 detection_callback。
    await scanner.start()


    try:

        # main() 本身沒有其他工作時持續讓 event loop 運行。
        # await asyncio.sleep(1) 並不是「每秒掃描一次」；
        # scanner 在背景持續掃描，而 await 讓出控制權，
        # 使 asyncio / Bleak 可以處理收到的 BLE 事件。
        while True:

            await asyncio.sleep(1)


    finally:

        # 不論程式正常離開或發生例外，都嘗試停止 BLE scanner。
        await scanner.stop()


# ============================================================
# 程式進入點
# ============================================================

if __name__ == "__main__":

    try:

        # 建立並執行 asyncio event loop，從 main() 開始運作。
        asyncio.run(
            main()
        )


    except KeyboardInterrupt:

        # 使用 Ctrl+C 中止程式時顯示結束訊息。
        print()
        print(
            "Air Mentor scanner stopped."
        )
