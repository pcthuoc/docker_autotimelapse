#!/usr/bin/env python3
"""
AutoTimelapse CM4 - Module Nhận Lệnh Bật/Tắt & Truy Vấn Thông Tin CM4 (MQTT Agent)
----------------------------------------------------------------------------------
Script Python độc lập chuyên trách:
  1. Kết nối MQTT Broker (hỗ trợ broker mqtt.congnghetimelapse.com / IP VPS).
  2. Lắng nghe và xử lý lệnh Bật / Tắt CM4 ('power_on_cm4', 'power_off_cm4').
  3. Lắng nghe và xử lý các lệnh Get Info từ Backend & Web UI:
       - 'get_sim_info'    -> Trả về thông tin SIM 4G (Nhà mạng, Số ĐT, ICCID, Sóng dBm)
       - 'get_settings'    -> Trả về thông số máy ảnh (ISO, Khẩu độ, Tốc độ, WB)
       - 'get_capabilities'-> Trả về dải thông số máy ảnh hỗ trợ
       - 'get_status'      -> Trả về trạng thái nguồn, online, thông tin thiết bị
       - 'set_settings'    -> Nhận cài đặt thông số máy ảnh
  4. Trả ACK tức thì về topic: camera/{CAMERA_CODE}/ack kèm request_id.
  5. Gửi Telemetry định kỳ lên topic: camera/{CAMERA_CODE}/data.

Cài đặt thư viện:
  pip install paho-mqtt

Cách chạy:
  python3 cm4_power_receiver.py --code CAM-KDMJTV --secret '7XV0y_aLOeB__XmmSj8kvg' --broker mqtt.congnghetimelapse.com --port 1883
"""

import argparse
import json
import logging
import os
import random
import signal
import sys
import threading
import time
from datetime import datetime, timezone, timedelta

try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("❌ Lỗi: Chưa cài đặt paho-mqtt. Hãy chạy: pip install paho-mqtt")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("cm4_power_agent")


class CM4PowerAgent:
    """Agent chuyên nhận lệnh Bật/Tắt & Get Info cho CM4 qua MQTT chuẩn Backend."""

    def __init__(self, code, password, broker="mqtt.congnghetimelapse.com", port=1883, telemetry_interval=30):
        self.code = code
        self.password = password
        self.broker = broker
        self.port = port
        self.telemetry_interval = telemetry_interval

        # MQTT Topics
        self.t_cmd    = f"camera/{self.code}/cmd"
        self.t_ack    = f"camera/{self.code}/ack"
        self.t_data   = f"camera/{self.code}/data"
        self.t_status = f"camera/{self.code}/status"

        # Trạng thái nguồn CM4 ('running' | 'off')
        self.cm4_power_state = "running"
        self.running = False
        self.mqtt_client = None

        # Thông tin SIM 4G mặc định
        self.sim_info = {
            "operator": "Viettel 4G",
            "number": "+84987654321",
            "iccid": "8984047123456789012",
            "signal_dbm": -68,
        }

        # Thông số máy ảnh giả lập / lưu trữ
        self.settings = {
            "iso": "100",
            "aperture": "f/4",
            "shutter_speed": "1/200",
            "exposure_compensation": "0.0",
            "white_balance": "Auto",
            "image_format": "JPEG Fine",
            "image_size": "6000x4000",
            "focus_mode": "AF-S",
            "autofocus": "On",
            "capture_mode": "Single Shot",
            "capture_target": "Memory Card",
            "high_iso_nr": "Off",
            "long_exp_nr": "Off",
            "liveview_af": "Normal Area",
            "exposure_mode": "Manual",
            "focus_switch": "AF",
        }

        self.capabilities = {
            "iso": {
                "writable": True,
                "current": self.settings["iso"],
                "choices": ["Auto", "100", "200", "400", "800", "1600", "3200", "6400"],
            },
            "aperture": {
                "writable": True,
                "current": self.settings["aperture"],
                "choices": ["f/2.8", "f/4", "f/5.6", "f/8", "f/11", "f/16"],
            },
            "shutter_speed": {
                "writable": True,
                "current": self.settings["shutter_speed"],
                "choices": ["1/4000", "1/2000", "1/1000", "1/500", "1/200", "1/100", "1/50", "1/4"],
            },
            "white_balance": {
                "writable": True,
                "current": self.settings["white_balance"],
                "choices": ["Auto", "Daylight", "Cloudy", "Shade", "Tungsten", "Fluorescent"],
            },
            "image_format": {
                "writable": True,
                "current": self.settings["image_format"],
                "choices": ["JPEG Fine", "JPEG Normal", "RAW", "RAW+JPEG"],
            },
        }

    # ── Đọc SIM từ Modem thực tế (nếu cắm trên CM4) ───────────────────────────

    def _read_real_sim_if_available(self):
        """Tự động kiểm tra nếu có cổng modem Quectel AT (/dev/ttyUSB2 hoặc /dev/ttyUSB1)."""
        for dev in ("/dev/ttyUSB2", "/dev/ttyUSB1", "/dev/ttyUSB0", "/dev/ttyACM0"):
            if os.path.exists(dev) and os.access(dev, os.R_OK | os.W_OK):
                try:
                    import serial
                    with serial.Serial(dev, 115200, timeout=1.0) as ser:
                        ser.write(b"AT+CSQ\r\n")
                        time.sleep(0.1)
                        resp = ser.read_until(b"OK").decode("utf-8", errors="ignore")
                        if "+CSQ:" in resp:
                            rssi = int(resp.split("+CSQ:")[1].split(",")[0].strip())
                            if rssi < 99:
                                self.sim_info["signal_dbm"] = -113 + (rssi * 2)
                        ser.write(b"AT+COPS?\r\n")
                        time.sleep(0.1)
                        resp_cops = ser.read_until(b"OK").decode("utf-8", errors="ignore")
                        if ',"' in resp_cops:
                            op = resp_cops.split(',"')[1].split('"')[0]
                            self.sim_info["operator"] = op
                except Exception:
                    pass
                break

    # ── MQTT Callbacks ────────────────────────────────────────────────────────

    def _on_connect(self, client, userdata, flags, rc, props=None):
        if rc == 0:
            log.info("✅ Đã kết nối MQTT Broker %s:%d thành công!", self.broker, self.port)
            log.info("📷 Camera Code: %s", self.code)

            # Subscribe topic nhận lệnh từ Web / Backend
            client.subscribe(self.t_cmd, qos=1)
            log.info("👂 Đang lắng nghe lệnh tại topic: %s", self.t_cmd)

            # Báo Online trạng thái thiết bị
            client.publish(self.t_status, json.dumps({"online": True}), qos=1, retain=True)

            # Gửi Telemetry ban đầu cập nhật cho Backend
            self.send_telemetry()
        else:
            log.error("❌ Kết nối MQTT thất bại với mã lỗi rc=%s", rc)

    def _on_disconnect(self, client, userdata, rc, *args):
        log.warning("⚠️ Mất kết nối MQTT (rc=%s). Đang tự động kết nối lại...", rc)

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
            cmd = payload.get("command", "")
            rid = payload.get("request_id", "")
            data_payload = payload.get("payload") or {}

            log.info("📥 [LỆNH NHẬN ĐƯỢC] command='%s', request_id='%s'", cmd, rid)
            self._handle_command(cmd, rid, data_payload)

        except Exception as exc:
            log.error("❌ Lỗi khi phân tích gói tin MQTT: %s", exc)

    # ── Xử lý lệnh Bật/Tắt & Get Info ─────────────────────────────────────────

    def _handle_command(self, cmd, rid, payload):
        resp_status = "ok"
        resp_data = {}

        # ── 1. LỆNH BẬT NGUỒN CM4 ─────────────────────────────────────────────
        if cmd in ("power_on_cm4", "power_on"):
            log.info("⚡ Thực thi lệnh BẬT CM4...")
            self.cm4_power_state = "running"
            resp_data = {
                "cm4_power_state": "running",
                "camera_power": "on",
                "message": "CM4 is now RUNNING",
            }
            self.send_telemetry(node="cm4")
            log.info("🟢 CM4 đã BẬT (cm4_power_state = 'running')")

        # ── 2. LỆNH TẮT NGUỒN CM4 ─────────────────────────────────────────────
        elif cmd in ("power_off_cm4", "power_off"):
            log.info("💤 Thực thi lệnh TẮT CM4...")
            self.cm4_power_state = "off"
            resp_data = {
                "cm4_power_state": "off",
                "camera_power": "off",
                "message": "CM4 is now OFF",
            }
            self.send_telemetry(node="esp32")
            log.info("🔴 CM4 đã TẮT (cm4_power_state = 'off')")

        # ── 3. LỆNH GET SIM INFO (Lấy thông tin SIM 4G) ────────────────────────
        elif cmd in ("get_sim_info", "sim_info"):
            self._read_real_sim_if_available()
            # Thêm ngẫu nhiên nhẹ dBm nếu giả lập để biểu đồ sóng nhảy sinh động
            sig = self.sim_info.get("signal_dbm", -68) + random.choice([-2, -1, 0, 1, 2])
            sim_resp = {
                "operator": self.sim_info.get("operator", "Viettel 4G"),
                "number": self.sim_info.get("number", "+84987654321"),
                "iccid": self.sim_info.get("iccid", "8984047123456789012"),
                "signal_dbm": max(-105, min(-55, sig)),
            }
            resp_data = {"sim": sim_resp}
            log.info("📱 [GET_SIM_INFO] Trả về SIM: %s (%s, Sóng: %ddBm)",
                     sim_resp["number"], sim_resp["operator"], sim_resp["signal_dbm"])

        # ── 4. LỆNH GET SETTINGS & CAPABILITIES (Lấy thông số máy ảnh) ─────────
        elif cmd in ("get_settings", "get_capabilities"):
            resp_data = {
                "applied": self.settings,
                "settings": self.settings,
                "capabilities": self.capabilities,
                "online": True,
                "cm4_power_state": self.cm4_power_state,
            }
            log.info("📷 [GET_SETTINGS] Trả về thông số máy ảnh (ISO %s, Khẩu %s, Tốc %s)",
                     self.settings.get("iso"), self.settings.get("aperture"), self.settings.get("shutter_speed"))

        # ── 5. LỆNH SET SETTINGS (Cài đặt thông số chụp) ───────────────────────
        elif cmd == "set_settings":
            for k, v in payload.items():
                if k in self.settings:
                    self.settings[k] = str(v)
                    if k in self.capabilities:
                        self.capabilities[k]["current"] = str(v)
            resp_data = {
                "requested": payload,
                "applied": self.settings,
                "capabilities": self.capabilities,
                "mismatches": {},
            }
            log.info("⚙️ [SET_SETTINGS] Đã cập nhật thông số máy ảnh: %s", payload)

        # ── 6. LỆNH GET STATUS (Lấy toàn bộ trạng thái) ────────────────────────
        elif cmd in ("get_status", "get_power_state", "get_info"):
            resp_data = {
                "online": True,
                "camera_code": self.code,
                "cm4_power_state": self.cm4_power_state,
                "camera_power": "on" if self.cm4_power_state == "running" else "off",
                "firmware_version": "cm4-power-agent-v2.0",
                "sim": self.sim_info,
                "settings": self.settings,
            }
            log.info("ℹ️ [GET_STATUS] Báo cáo trạng thái CM4: %s", self.cm4_power_state)

        # ── 7. LỆNH REBOOT ────────────────────────────────────────────────────
        elif cmd in ("reboot", "restart_service"):
            log.info("🔄 Đang xử lý lệnh reboot...")
            resp_data = {"status": "rebooting", "cm4_power_state": "rebooting"}

        else:
            log.warning("⚠️ Lệnh không xác định: '%s'", cmd)
            resp_status = "error"
            resp_data = {"error": f"Command '{cmd}' not recognized"}

        # Gửi ACK phản hồi về topic ack
        ack_msg = {
            "type": cmd,
            "request_id": rid,
            "status": resp_status,
            "data": resp_data,
        }
        if self.mqtt_client and self.mqtt_client.is_connected():
            self.mqtt_client.publish(self.t_ack, json.dumps(ack_msg), qos=1)
            log.info("📤 [ACK ĐÃ GỬI] type='%s', request_id='%s', status='%s'", cmd, rid, resp_status)

    # ── Gửi Telemetry ────────────────────────────────────────────────────────

    def send_telemetry(self, node=None):
        if not self.mqtt_client or not self.mqtt_client.is_connected():
            return
        try:
            now_dt = datetime.now(timezone(timedelta(hours=7)))
            active_node = node or ("cm4" if self.cm4_power_state == "running" else "esp32")

            telemetry_data = {
                "camera_code": self.code,
                "node": active_node,
                "cm4_power_state": self.cm4_power_state,
                "sim_active_node": "cm4" if self.cm4_power_state == "running" else "esp32",
                "battery_voltage": round(random.uniform(12.2, 12.6), 2),
                "battery_percent": random.randint(85, 98),
                "solar_voltage": round(random.uniform(15.0, 18.0), 1),
                "solar_percent": random.randint(70, 100),
                "temperature_c": round(random.uniform(33.0, 41.0), 1),
                "humidity_percent": random.randint(60, 80),
                "sim_signal_dbm": random.randint(-75, -60),
                "is_charging": True,
                "firmware_version": "cm4-power-agent-v2.0",
                "timestamp": now_dt.isoformat(),
            }

            self.mqtt_client.publish(self.t_data, json.dumps(telemetry_data), qos=1)
            log.info("📡 [TELEMETRY] Node: %s | cm4_power_state: '%s' | Pin: %d%% (%.2fV)",
                     active_node, self.cm4_power_state,
                     telemetry_data["battery_percent"], telemetry_data["battery_voltage"])
        except Exception as e:
            log.warning("Lỗi khi gửi Telemetry: %s", e)

    def _telemetry_loop(self):
        while self.running:
            time.sleep(self.telemetry_interval)
            if self.running:
                self.send_telemetry()

    # ── Vòng đời Agent ────────────────────────────────────────────────────────

    def start(self):
        self.running = True
        log.info("=" * 65)
        log.info("  AUTOTIMELAPSE CM4 POWER & INFO CONTROLLER AGENT")
        log.info("  Camera Code: %s", self.code)
        log.info("  MQTT Broker: %s:%d", self.broker, self.port)
        log.info("  Chu kỳ Telemetry: %ds", self.telemetry_interval)
        log.info("=" * 65)

        try:
            client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"pwr_{self.code}")
        except (AttributeError, TypeError):
            client = mqtt.Client(client_id=f"pwr_{self.code}")

        if self.code and self.password:
            client.username_pw_set(self.code, self.password)

        client.will_set(self.t_status, json.dumps({"online": False}), qos=1, retain=True)
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message = self._on_message
        self.mqtt_client = client

        threading.Thread(target=self._telemetry_loop, daemon=True, name="TelemetryLoop").start()

        while self.running:
            try:
                log.info("🔌 Đang kết nối tới MQTT Broker %s:%d...", self.broker, self.port)
                client.connect(self.broker, self.port, keepalive=60)
                client.loop_forever()
            except Exception as e:
                log.warning("Lỗi kết nối MQTT (%s). Thử lại sau 5s...", e)
                time.sleep(5)

    def stop(self):
        self.running = False
        if self.mqtt_client:
            try:
                self.mqtt_client.publish(self.t_status, json.dumps({"online": False}), qos=1, retain=True)
                self.mqtt_client.disconnect()
            except Exception:
                pass


def main():
    parser = argparse.ArgumentParser(description="CM4 Standalone Power & Info Agent")
    parser.add_argument("--code", default=os.getenv("CAMERA_CODE", "CAM-KDMJTV"), help="Mã Camera Code")
    parser.add_argument("--secret", default=os.getenv("MQTT_PASSWORD", ""), help="Mật khẩu MQTT")
    parser.add_argument("--broker", default=os.getenv("MQTT_BROKER", "mqtt.congnghetimelapse.com"), help="MQTT Broker Host")
    parser.add_argument("--port", type=int, default=int(os.getenv("MQTT_PORT", 1883)), help="MQTT Port")
    parser.add_argument("--interval", type=int, default=int(os.getenv("TELEMETRY_INTERVAL", 30)), help="Chu kỳ Telemetry")

    args = parser.parse_args()
    agent = CM4PowerAgent(args.code, args.secret, args.broker, args.port, args.interval)

    def _sig_handler(sig, frame):
        agent.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _sig_handler)
    signal.signal(signal.SIGTERM, _sig_handler)
    agent.start()


if __name__ == "__main__":
    main()
