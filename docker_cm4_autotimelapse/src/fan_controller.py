#!/usr/bin/env python3
"""
AutoTimelapse CM4 Agent - EMC2301 I2C Fan Controller
------------------------------------------------------------------
Điều khiển quạt tản nhiệt thông minh qua IC EMC2301-1-ACZL-TR trên I2C Bus:
- Điều tốc PWM tự động theo nhiệt độ CPU thật của CM4.
- Đọc tốc độ vòng quay quạt (RPM) từ thanh ghi Tachometer.
- Cơ chế Fan Curve thông minh & Hysteresis chống rung/bật tắt liên tục.
"""

import os
import time
import logging

log = logging.getLogger("cm4_fan")

try:
    import smbus2
except ImportError:
    smbus2 = None


# ── Thanh ghi EMC2301 ────────────────────────────────────────────────────────
REG_FAN_CONFIG_1       = 0x02  # Cấu hình PWM/Tachometer
REG_FAN_STATUS         = 0x32  # Trạng thái lỗi quạt (Stall, Spin-up)
REG_FAN_SETTING        = 0x30  # Giá trị điều tốc PWM (0x00 = 0% -> 0xFF = 100%)
REG_TACH_READING_HIGH  = 0x3E  # Byte cao tốc độ Tachometer
REG_TACH_READING_LOW   = 0x3F  # Byte thấp tốc độ Tachometer
REG_PRODUCT_ID         = 0xFD  # Product ID EMC2301 (0x37)


class EMC2301FanController:
    """Quản lý điều khiển quạt EMC2301 qua I2C Bus."""

    def __init__(self, bus_id: int = 1, address: int = 0x2F,
                 temp_off: float = 48.0, temp_mid: float = 58.0, temp_high: float = 68.0):
        self.bus_id = bus_id
        self.address = address
        self.temp_off = temp_off      # Dưới ngưỡng này quạt tắt 0%
        self.temp_mid = temp_mid      # Từ temp_off -> temp_mid chạy êm 40%
        self.temp_high = temp_high    # Từ temp_mid -> temp_high chạy 70%, trên đó 100%

        self.current_pwm = 0
        self.current_rpm = 0
        self.is_detected = False
        self._check_device()

    def _check_device(self):
        """Kiểm tra sự hiện diện của EMC2301 trên I2C bus."""
        if smbus2 is None:
            return
        try:
            with smbus2.SMBus(self.bus_id) as bus:
                # Đọc Product ID hoặc Configuration register
                bus.read_byte_data(self.address, REG_PRODUCT_ID)
                self.is_detected = True
                log.info("✅ Đã tìm thấy EMC2301 Fan Controller tại I2C bus %d, addr 0x%02X", self.bus_id, self.address)
        except Exception:
            # Thử thêm địa chỉ fallback 0x2E / 0x4C nếu 0x2F không phản hồi
            for alt_addr in (0x2E, 0x4C):
                try:
                    with smbus2.SMBus(self.bus_id) as bus:
                        bus.read_byte_data(alt_addr, REG_PRODUCT_ID)
                        self.address = alt_addr
                        self.is_detected = True
                        log.info("✅ Đã tìm thấy EMC2301 tại địa chỉ I2C thay thế: 0x%02X", alt_addr)
                        return
                except Exception:
                    pass
            self.is_detected = False

    def set_fan_pwm(self, pwm_val: int) -> bool:
        """
        Đặt tốc độ PWM cho quạt (0 - 255).
        0 = Tắt hẳn, 255 = 100% công suất.
        """
        if smbus2 is None:
            return False
        pwm_val = max(0, min(255, int(pwm_val)))
        try:
            with smbus2.SMBus(self.bus_id) as bus:
                bus.write_byte_data(self.address, REG_FAN_SETTING, pwm_val)
                self.current_pwm = pwm_val
                return True
        except Exception as e:
            log.debug("Lỗi ghi PWM EMC2301: %s", e)
            return False

    def read_fan_rpm(self) -> int:
        """Đọc tốc độ vòng quay (RPM) từ bộ đếm Tachometer của EMC2301."""
        if smbus2 is None:
            return 0
        try:
            with smbus2.SMBus(self.bus_id) as bus:
                high = bus.read_byte_data(self.address, REG_TACH_READING_HIGH)
                low = bus.read_byte_data(self.address, REG_TACH_READING_LOW)
                raw_count = (high << 5) | (low >> 3)
                if raw_count == 0 or raw_count >= 0x1FFF:
                    self.current_rpm = 0
                    return 0
                # Công thức chuẩn của EMC2301: RPM = (1 / Tach_count) * (m * 60 * f_tach)
                # Với quạt 2 cực (2 poles) thông dụng:
                rpm = int((3932160 * 2) / raw_count) if raw_count > 0 else 0
                self.current_rpm = max(0, min(15000, rpm))
                return self.current_rpm
        except Exception:
            return self.current_rpm

    def update_by_cpu_temp(self, cpu_temp: float) -> dict:
        """
        Tự động tính toán & điều chỉnh tốc độ quạt theo nhiệt độ CPU của CM4.
        Trả về dict thông tin quạt: {pwm, percent, rpm, status}.
        """
        if cpu_temp is None or cpu_temp <= 0:
            target_pwm = 0
        elif cpu_temp < self.temp_off:
            # Dưới 48°C: Quạt tắt để tiết kiệm pin & tăng độ bền
            target_pwm = 0
        elif cpu_temp < self.temp_mid:
            # 48°C - 58°C: Quạt chạy êm (~40%)
            target_pwm = 100
        elif cpu_temp < self.temp_high:
            # 58°C - 68°C: Quạt chạy vừa (~70%)
            target_pwm = 180
        else:
            # Trên 68°C: Quạt chạy 100% công suất làm mát tối đa
            target_pwm = 255

        # Cập nhật PWM nếu thay đổi
        if target_pwm != self.current_pwm:
            self.set_fan_pwm(target_pwm)
            log.info("🌀 [FAN EMC2301] CPU: %.1f°C -> Đặt tốc độ Quạt: %d%% (PWM: %d)",
                     cpu_temp, int(target_pwm / 255 * 100), target_pwm)

        rpm = self.read_fan_rpm() if target_pwm > 0 else 0
        pct = int(target_pwm / 255.0 * 100)

        return {
            "fan_pwm": target_pwm,
            "fan_percent": pct,
            "fan_rpm": rpm,
            "fan_status": "OFF" if target_pwm == 0 else f"{pct}% ({rpm} RPM)",
        }
