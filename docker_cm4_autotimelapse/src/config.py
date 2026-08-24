#!/usr/bin/env python3
"""
AutoTimelapse CM4 Agent - Module Cấu Hình (Config)
------------------------------------------------------------------
Đọc biến môi trường (Environment Variables) và cấu hình hệ thống.
"""

import os

# Cấu hình Camera & MQTT Server
CAMERA_CODE        = os.getenv("CAMERA_CODE", "")
MQTT_PASSWORD      = os.getenv("MQTT_PASSWORD", os.getenv("DEVICE_SECRET", ""))
MQTT_BROKER        = os.getenv("MQTT_BROKER", "mqtt.congnghetimelapse.com")
MQTT_PORT          = int(os.getenv("MQTT_PORT", "1883"))
SERVER_BASE        = os.getenv("SERVER_BASE", "https://cloud.congnghetimelapse.com")

# Cấu hình Quản lý Nguồn GPIO trên CM4
POWER_GPIO_PIN     = int(os.getenv("POWER_GPIO_PIN", "16"))
POWER_ACTIVE_HIGH  = os.getenv("POWER_ACTIVE_HIGH", "true").lower() in ("true", "1", "yes")
WARMUP_DELAY_SEC   = float(os.getenv("WARMUP_DELAY_SEC", "10.0"))
ALWAYS_KEEP_POWER  = os.getenv("ALWAYS_KEEP_POWER", "false").lower() in ("true", "1", "yes")

# Cấu hình I2C Bus & Cảm biến (SHT20, ADS1115, EMC2301 Fan Controller)
I2C_BUS_ID             = int(os.getenv("I2C_BUS_ID", "1"))
EMC2301_I2C_ADDR       = int(os.getenv("EMC2301_I2C_ADDR", "0x2F"), 16) if os.getenv("EMC2301_I2C_ADDR") else 0x2F
ADS1115_I2C_ADDR       = int(os.getenv("ADS1115_I2C_ADDR", "0x49"), 16) if os.getenv("ADS1115_I2C_ADDR") else 0x49
ADS1115_SOLAR_CHANNEL  = int(os.getenv("ADS1115_SOLAR_CHANNEL", "2"))    # Kênh 3 (Chân A2 - Solar)
ADS1115_BATTERY_CHANNEL= int(os.getenv("ADS1115_BATTERY_CHANNEL", "3"))  # Kênh 4 (Chân A3 - Pin)
BATTERY_VOLTAGE_SCALE  = float(os.getenv("BATTERY_VOLTAGE_SCALE", "5.545"))  # Trở 22k/100k -> (100+22)/22 = 5.545
SOLAR_VOLTAGE_SCALE    = float(os.getenv("SOLAR_VOLTAGE_SCALE", "5.545"))    # Trở 22k/100k -> (100+22)/22 = 5.545

# Cấu hình Ngưỡng Nhiệt độ CPU điều khiển Quạt EMC2301
FAN_TEMP_OFF           = float(os.getenv("FAN_TEMP_OFF", "48.0"))    # < 48°C: Quạt TẮT (0%)
FAN_TEMP_MID           = float(os.getenv("FAN_TEMP_MID", "55.0"))    # 48°C - 55°C: Chạy êm (40%)
FAN_TEMP_HIGH          = float(os.getenv("FAN_TEMP_HIGH", "65.0"))   # 55°C - 65°C: Chạy vừa (70%), >= 65°C: 100%

# Cấu hình Số lần Thử lại (Retry Rules)
MAX_CAMERA_RETRIES = int(os.getenv("MAX_CAMERA_RETRIES", "3"))
MAX_UPLOAD_RETRIES = int(os.getenv("MAX_UPLOAD_RETRIES", "3"))
UPLOAD_RETRY_DELAY = float(os.getenv("UPLOAD_RETRY_DELAY", "2.0"))

# Cấu hình Telemetry & Hàng Đợi Offline
TELEMETRY_INTERVAL     = int(os.getenv("TELEMETRY_INTERVAL", "30"))
OFFLINE_QUEUE_DIR      = os.getenv("OFFLINE_QUEUE_DIR", "/app/offline_queue")
OFFLINE_RETRY_INTERVAL = int(os.getenv("OFFLINE_RETRY_INTERVAL", "60"))

# Cấu hình Tự động chụp & Tắt nguồn CM4 (Chế độ tiết kiệm năng lượng EC25)
AUTO_SHUTDOWN_AFTER_CAPTURE = os.getenv("AUTO_SHUTDOWN_AFTER_CAPTURE", "false").lower() in ("true", "1", "yes")
AUTO_CAPTURE_ON_BOOT        = os.getenv("AUTO_CAPTURE_ON_BOOT", "false").lower() in ("true", "1", "yes")
SHUTDOWN_DELAY_SEC          = float(os.getenv("SHUTDOWN_DELAY_SEC", "3.0"))

# File state dùng chung giữa EC25 và CM4 Agent để đồng bộ trạng thái.
# Lưu: force_power_on, missed_capture_flag, last_capture_ts
EC25_STATE_FILE = os.getenv("EC25_STATE_FILE", "/app/offline_queue/ec25_state.json")

# Danh sách thông số máy ảnh hỗ trợ - Đa dòng máy (Canon EOS, Nikon, Sony, v.v.)
# Format: field_name -> (candidate_widget_names_tuple_or_list, is_writable)
SETTING_SPECS = {
    "iso":                   (["iso"], True),
    "aperture":              (["aperture", "f-number", "fnumber"], True),
    "shutter_speed":         (["shutterspeed", "shutterspeed2"], True),
    "exposure_compensation": (["exposurecompensation"], True),
    "white_balance":         (["whitebalance"], True),
    "image_format":          (["imageformat", "imagequality", "imageformatsd", "imageformatcf"], True),
    "image_size":            (["imagesize"], True),
    "focus_mode":            (["focusmode", "focusmode2"], True),
    "autofocus":             (["autofocus"], True),
    "capture_mode":          (["capturemode"], True),
    "capture_target":        (["capturetarget"], True),
    "high_iso_nr":           (["highisonr"], True),
    "long_exp_nr":           (["longexpnr"], True),
    "liveview_af":           (["liveviewaffocus"], True),
    "exposure_mode":         (["autoexposuremode", "expprogram"], False),
    "focus_switch":          (["focusmode", "focusmode2"], False),
}

SIM_INFO_TELEMETRY = {
    "operator": "CM4 4G/WiFi Gateway",
    "number": "+84987654321",
    "iccid": "8984047123456789012",
}

