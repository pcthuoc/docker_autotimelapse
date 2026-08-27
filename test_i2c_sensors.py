#!/usr/bin/env python3
import time
import sys

try:
    import smbus2
except ImportError:
    print("smbus2 not found, installing or testing with raw /dev/i2c-1")
    sys.exit(1)

BUS_ID = 1
SHT20_ADDR = 0x40
ADS1115_ADDR = 0x49

# Resistor divider: R_up = 100k, R_down = 22k -> Ratio = (100 + 22) / 22 = 5.5454545...
RESISTOR_SCALE = (100.0 + 22.0) / 22.0  # 5.5454545

print("=========================================================")
print(f"  I2C SENSOR TEST (Bus {BUS_ID})")
print(f"  - SHT20 Temp/Humidity Sensor @ 0x{SHT20_ADDR:02X}")
print(f"  - ADS1115 16-bit ADC @ 0x{ADS1115_ADDR:02X}")
print(f"  - Resistor divider: 22k / 100k (Ratio: {RESISTOR_SCALE:.4f})")
print("=========================================================\n")

def read_sht20(bus):
    try:
        # Trigger Temp measurement (0xF3)
        bus.i2c_rdwr(smbus2.i2c_msg.write(SHT20_ADDR, [0xF3]))
        time.sleep(0.1)
        read_t = smbus2.i2c_msg.read(SHT20_ADDR, 3)
        bus.i2c_rdwr(read_t)
        data_t = list(read_t)
        raw_t = (data_t[0] << 8) | data_t[1]
        temp_c = -46.85 + 175.72 * (raw_t / 65536.0)

        # Trigger Humidity measurement (0xF5)
        bus.i2c_rdwr(smbus2.i2c_msg.write(SHT20_ADDR, [0xF5]))
        time.sleep(0.05)
        read_h = smbus2.i2c_msg.read(SHT20_ADDR, 3)
        bus.i2c_rdwr(read_h)
        data_h = list(read_h)
        raw_h = (data_h[0] << 8) | data_h[1]
        humidity = -6.0 + 125.0 * (raw_h / 65536.0)
        humidity = max(0.0, min(100.0, humidity))

        return round(temp_c, 2), round(humidity, 2)
    except Exception as e:
        return None, str(e)

def read_ads1115_channel(bus, channel):
    """Read single-ended channel 0..3 with PGA=+/-4.096V"""
    try:
        mux = (0x4 + channel) << 12
        # OS=1 (start conversion), MUX, PGA=+/-4.096V (0x0200), MODE=Single (0x0100), DR=128SPS (0x0080), COMP_QUE=disable (0x0003)
        config = 0x8000 | mux | 0x0200 | 0x0100 | 0x0083
        bus.i2c_rdwr(smbus2.i2c_msg.write(ADS1115_ADDR, [0x01, (config >> 8) & 0xFF, config & 0xFF]))
        time.sleep(0.02)
        write_ptr = smbus2.i2c_msg.write(ADS1115_ADDR, [0x00])
        read_val = smbus2.i2c_msg.read(ADS1115_ADDR, 2)
        bus.i2c_rdwr(write_ptr, read_val)
        data = list(read_val)
        raw = (data[0] << 8) | data[1]
        if raw > 32767:
            raw -= 65536
        v_pin = (raw / 32767.0) * 4.096
        return max(0.0, v_pin), raw
    except Exception as e:
        return None, str(e)

with smbus2.SMBus(BUS_ID) as bus:
    # 1. SHT20
    temp, humi = read_sht20(bus)
    if temp is not None:
        print(f"🌡️  SHT20 [0x40]:")
        print(f"   - Temperature : {temp} °C")
        print(f"   - Humidity    : {humi} %\n")
    else:
        print(f"❌ SHT20 Error: {humi}\n")

    # 2. ADS1115
    print("⚡ ADS1115 [0x49] (16-bit ADC):")
    
    # Channel 1 (AIN0) - Not used
    v_pin0, raw0 = read_ads1115_channel(bus, 0)
    print(f"   - Kênh 1 (AIN0) [Không dùng] : Pin = {v_pin0:.4f}V (Raw={raw0})")

    # Channel 2 (AIN1) - Not used
    v_pin1, raw1 = read_ads1115_channel(bus, 1)
    print(f"   - Kênh 2 (AIN1) [Không dùng] : Pin = {v_pin1:.4f}V (Raw={raw1})")

    # Channel 3 (AIN2) - SOLAR
    v_pin2, raw2 = read_ads1115_channel(bus, 2)
    if v_pin2 is not None:
        v_solar = v_pin2 * RESISTOR_SCALE
        print(f"   - Kênh 3 (AIN2) [☀️ SOLAR]   : ADC Pin = {v_pin2:.4f}V  ==>  Điện áp Solar = {v_solar:.2f} V (Raw={raw2})")
    else:
        print(f"   - Kênh 3 (AIN2) [☀️ SOLAR]   : Error {raw2}")

    # Channel 4 (AIN3) - BATTERY / PIN
    v_pin3, raw3 = read_ads1115_channel(bus, 3)
    if v_pin3 is not None:
        v_bat = v_pin3 * RESISTOR_SCALE
        print(f"   - Kênh 4 (AIN3) [🔋 PIN/BAT] : ADC Pin = {v_pin3:.4f}V  ==>  Điện áp Pin   = {v_bat:.2f} V (Raw={raw3})")
    else:
        print(f"   - Kênh 4 (AIN3) [🔋 PIN/BAT] : Error {raw3}")

print("\n=========================================================")
