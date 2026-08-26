#!/usr/bin/env python3
"""
AutoTimelapse CM4 Agent - Solar Charging Fan Controller (GPIO 19)
------------------------------------------------------------------
Điều khiển quạt tản nhiệt sạc qua GPIO 19 dựa trên:
1. Kênh ADS1115 số 2 (AIN2): Điện áp 0 - 6V (> 4.5V chứng tỏ đang sạc)
2. Điện áp tấm pin Solar (> 15.0V)
3. Khung giờ ban ngày: 07:00 -> 16:00 (7 <= hour < 16)
4. Ngoại lệ: Nếu ban đêm nhưng đồng thời Kênh 2 > 4.5V VÀ Solar > 15.0V -> Vẫn BẬT QUẠT.
"""

import os
import time
import logging
from datetime import datetime

log = logging.getLogger("cm4_solar_fan")

HAS_GPIO = False
try:
    import RPi.GPIO as GPIO
    HAS_GPIO = True
except (ImportError, RuntimeError):
    GPIO = None


class SolarChargingFanController:
    """Quản lý quạt tản nhiệt sạc pin qua GPIO 19."""

    def __init__(self, pin: int = 19, active_high: bool = True):
        self.pin = pin
        self.active_high = active_high
        self.is_fan_on = False
        self.has_gpio = HAS_GPIO

        self._init_gpio()

    def _init_gpio(self):
        if self.has_gpio:
            try:
                GPIO.setmode(GPIO.BCM)
                GPIO.setwarnings(False)
                GPIO.setup(self.pin, GPIO.OUT)
                off_state = GPIO.LOW if self.active_high else GPIO.HIGH
                GPIO.output(self.pin, off_state)
                log.info("🌬️ [SOLAR FAN] Khởi tạo thành công GPIO %d điều khiển quạt tản nhiệt sạc", self.pin)
            except Exception as e:
                log.warning("⚠️ Không thể cấu hình GPIO %d cho quạt sạc: %s", self.pin, e)
                self.has_gpio = False
        else:
            log.info("ℹ️ Chạy quạt sạc GPIO %d ở chế độ Giả lập (Simulated).", self.pin)

    def evaluate(self, v_ads_ch2: float, solar_voltage: float, custom_hour: int = None) -> tuple:
        """
        Đánh giá logic điều khiển quạt:
        - Ban ngày (07:00 -> 16:00): Bật nếu Kênh 2 > 4.5V HOẶC Solar > 15.0V.
        - Ban đêm (ngoài 07:00 - 16:00): Vẫn BẬT nếu đồng thời Kênh 2 > 4.5V VÀ Solar > 15.0V.
        Trả về: (should_run_bool, reason_str, debug_dict)
        """
        hour = custom_hour if custom_hour is not None else datetime.now().hour

        is_daytime = (7 <= hour < 16)
        ch2_high = (v_ads_ch2 is not None and v_ads_ch2 > 4.5)
        solar_high = (solar_voltage is not None and solar_voltage > 15.0)

        # 1. Ngoại lệ: Ban đêm nhưng cả 2 điều kiện đều cao (đang sạc thực tế ban đêm)
        if not is_daytime and (ch2_high and solar_high):
            should_run = True
            reason = f"NGOẠI LỆ BAN ĐÊM: Kênh 2={v_ads_ch2:.2f}V (>4.5V) & Solar={solar_voltage:.1f}V (>15V) -> Đang sạc ban đêm"
        # 2. Ban ngày: Bật khi có tín hiệu sạc (Kênh 2 > 4.5V hoặc Solar > 15V)
        elif is_daytime and (ch2_high or solar_high):
            should_run = True
            reason = f"BAN NGÀY ({hour:02d}:00): Kênh 2={v_ads_ch2 if v_ads_ch2 is not None else 0.0:.2f}V, Solar={solar_voltage if solar_voltage is not None else 0.0:.1f}V -> Bật quạt tản nhiệt sạc"
        else:
            should_run = False
            reason = f"TẮT: Giờ={hour:02d}:00 (Day={is_daytime}), Kênh 2={v_ads_ch2 if v_ads_ch2 is not None else 0.0:.2f}V, Solar={solar_voltage if solar_voltage is not None else 0.0:.1f}V"

        debug = {
            "gpio_pin": self.pin,
            "fan_running": should_run,
            "hour": hour,
            "is_daytime": is_daytime,
            "ads_ch2_voltage": v_ads_ch2,
            "solar_voltage": solar_voltage,
            "ch2_high": ch2_high,
            "solar_high": solar_high,
            "reason": reason,
        }
        return should_run, reason, debug

    def update(self, v_ads_ch2: float, solar_voltage: float, custom_hour: int = None) -> dict:
        """Cập nhật trạng thái phần cứng GPIO 19 theo điều kiện đo được."""
        should_run, reason, debug = self.evaluate(v_ads_ch2, solar_voltage, custom_hour=custom_hour)

        if should_run != self.is_fan_on:
            self.is_fan_on = should_run
            if self.has_gpio:
                try:
                    on_state = GPIO.HIGH if self.active_high else GPIO.LOW
                    off_state = GPIO.LOW if self.active_high else GPIO.HIGH
                    state = on_state if self.is_fan_on else off_state
                    GPIO.output(self.pin, state)
                except Exception as e:
                    log.warning("Lỗi ghi GPIO %d: %s", self.pin, e)

            log.info("🌬️ [SOLAR FAN GPIO %d] %s -> %s", self.pin, "BẬT QUẠT 🟢" if self.is_fan_on else "TẮT QUẠT ⚪", reason)

        return debug

    def cleanup(self):
        if self.has_gpio:
            try:
                off_state = GPIO.LOW if self.active_high else GPIO.HIGH
                GPIO.output(self.pin, off_state)
                log.info("🧹 Đã tắt quạt sạc GPIO %d.", self.pin)
            except Exception:
                pass


# Singleton
_solar_fan_ctrl = None

def get_solar_fan_controller(pin: int = 19, active_high: bool = True) -> SolarChargingFanController:
    global _solar_fan_ctrl
    if _solar_fan_ctrl is None:
        _solar_fan_ctrl = SolarChargingFanController(pin=pin, active_high=active_high)
    return _solar_fan_ctrl
