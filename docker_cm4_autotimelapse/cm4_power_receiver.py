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
import urllib.request
import urllib.error
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

    def __init__(self, code, password, broker="mqtt.congnghetimelapse.com", port=1883,
                 telemetry_interval=30, server_base="https://cloud.congnghetimelapse.com",
                 state_file="/app/offline_queue/ec25_state.json"):
        self.code = code
        self.password = password
        self.broker = broker
        self.port = port
        self.telemetry_interval = telemetry_interval
        self.server_base = server_base.rstrip("/")
        self.state_file = state_file

        # MQTT Topics
        self.t_cmd    = f"camera/{self.code}/cmd"
        self.t_ack    = f"camera/{self.code}/ack"
        self.t_data   = f"camera/{self.code}/data"
        self.t_status = f"camera/{self.code}/status"

        # Trạng thái nguồn CM4 ('running' | 'off')
        self.cm4_power_state = "running"
        self.running = False
        self.mqtt_client = None

        # ── Trạng thái đồng bộ Cưỡng Bức vs. Chu Kỳ ──────────────────────────
        # force_power_on: True khi user bật cưỡng bức từ Web UI
        # → EC25 KHÔNG được cắt nguồn CM4 sau chụp
        self.force_power_on = False
        self._load_state()

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

    # ── EC25 State File (đồng bộ trạng thái với CM4 Agent) ──────────────────

    def _load_state(self):
        """Đọc trạng thái được chia sẻ giữa EC25 và CM4 từ disk."""
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, "r", encoding="utf-8") as f:
                    state = json.load(f)
                self.force_power_on = bool(state.get("force_power_on", False))
                log.info("📂 [EC25 STATE] Đã đọc state từ disk: force_power_on=%s",
                         self.force_power_on)
        except Exception as e:
            log.warning("⚠️ Không đọc được state file: %s", e)

    def _save_state(self, **kwargs):
        """Lưu trạng thái xuống disk (merge với state hiện có)."""
        try:
            state = {}
            if os.path.exists(self.state_file):
                try:
                    with open(self.state_file, "r", encoding="utf-8") as f:
                        state = json.load(f)
                except Exception:
                    pass
            state.update(kwargs)
            state["force_power_on"] = self.force_power_on
            state["last_updated_by"] = "ec25_agent"
            state["last_updated_ts"] = datetime.now(timezone.utc).isoformat()
            os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            log.warning("⚠️ Không lưu được state file: %s", e)

    def pull_server_config(self):
        """Kéo trạng thái force_power_on từ Server và lưu xuống disk.

        Returns:
            (ok: bool, force_on: bool)
        """
        try:
            url = f"{self.server_base}/api/device/config/"
            req = urllib.request.Request(
                url, method="GET",
                headers={
                    "X-Device-Key": self.code,
                    "X-Device-Secret": self.password,
                    "User-Agent": "AutoTimelapse-EC25-Agent/2.0",
                },
            )
            with urllib.request.urlopen(req, timeout=15) as r:
                data = json.loads(r.read().decode() or "{}")
                if data.get("ok"):
                    force_on = bool(data.get("force_power_on", False))
                    self.force_power_on = force_on
                    self._save_state()
                    log.info("📥 [EC25 CONFIG SYNC] force_power_on=%s (từ server)", force_on)
                    return True, force_on
        except Exception as e:
            log.warning("⚠️ EC25 không pull được config từ server: %s. Dùng state local.", e)
        # Fallback: dùng giá trị đã cache trong disk
        log.info("📂 [EC25 CONFIG] Fallback state local: force_power_on=%s", self.force_power_on)
        return False, self.force_power_on

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
            # Subscribe thêm topic status để nhận sự kiện từ CM4 agent
            # (ví dụ: cycle_capture_done khi CM4 chụp xong chu kỳ)
            client.subscribe(self.t_status, qos=0)
            log.info("👂 Đang lắng nghe lệnh tại: %s | status tại: %s", self.t_cmd, self.t_status)

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
            # ── Xử lý event từ CM4 agent gửi lên topic status ───────────────
            if msg.topic == self.t_status:
                event = payload.get("event", "")
                if event == "cycle_capture_done":
                    taken_at = payload.get("taken_at", "")
                    media_count = payload.get("media_count", 0)
                    log.info("📷 [EC25] Nhận câu lệnh cycle_capture_done: %d ảnh lúc %s",
                             media_count, taken_at)
                    # Cập nhật state: chu kỳ đã hoàn tất
                    self._save_state(
                        last_capture_ts=taken_at,
                        last_cycle_capture_done=True,
                    )
                    # Nếu đang force_on: bỏ qua (CM4 sẽ không tự shutdown)
                    # Nếu không force_on: lóg biết CM4 sắp shutdown để EC25 ngắt nguồn
                    if self.force_power_on:
                        log.info("🎮 [EC25] force_on=True → CM4 GIỮ ONLINE, không ngắt nguồn theo chu kỳ.")
                    else:
                        log.info("🌙 [EC25] force_on=False → CM4 sắp shutdown. EC25 chờ ngắt nguồn.")
                return  # Không xử lý status message như lệnh

            # ── Xử lý lệnh thông thường từ Web / Backend ───────────────────
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
        if cmd in ("power_on_cm4", "power_on", "set_interactive_mode"):
            log.info("⚡ [FORCE-ON] Thực thi lệnh BẬT CM4 (cưỡng bức)...")
            self.cm4_power_state = "running"
            # Đánh dấu force_on=True: EC25 biết CM4 đang giữ online liên tục
            self.force_power_on = True
            self._save_state()
            resp_data = {
                "cm4_power_state": "running",
                "camera_power": "on",
                "force_power_on": True,
                "message": "CM4 is now RUNNING (force-on mode)",
            }
            self.send_telemetry(node="cm4")
            log.info("🟢 [FORCE-ON] CM4 đã BẬT → force_power_on=True (không cắt nguồn theo chu kỳ)")

        # ── 2. LỆNH TẮT NGUỒN CM4 ─────────────────────────────────────────────
        elif cmd in ("power_off_cm4", "power_off"):
            log.info("💤 Thực thi lệnh TẮT CM4...")
            self.cm4_power_state = "off"
            # Reset force_on=False: CM4 đã tắt, EC25 trở lại chế độ chu kỳ
            self.force_power_on = False
            self._save_state()
            resp_data = {
                "cm4_power_state": "off",
                "camera_power": "off",
                "force_power_on": False,
                "message": "CM4 is now OFF",
            }
            self.send_telemetry(node="esp32")
            log.info("🔴 [CYCLE-EC25] CM4 đã TẮT → force_power_on=False (trở lại chế độ chu kỳ)")

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
                "force_power_on": self.force_power_on,
                "camera_power": "on" if self.cm4_power_state == "running" else "off",
                "firmware_version": "cm4-power-agent-v2.0",
                "sim": self.sim_info,
                "settings": self.settings,
            }
            log.info("ℹ️ [GET_STATUS] Báo cáo trạng thái CM4: %s | force_on=%s",
                     self.cm4_power_state, self.force_power_on)

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
            active_node = node or ("cm4" if self.cm4_power_state == "running" else "ec25")

            # ── EC25 chỉ có thể đo được sóng 4G qua AT+CSQ ──
            # Không có I2C nên KHÔNG gửi: battery_voltage, solar_voltage,
            # temperature_c, humidity_percent — đó là cảm biến của CM4.
            self._read_real_sim_if_available()
            sim_dbm = self.sim_info.get("signal_dbm", -75) + random.choice([-2, -1, 0, 1, 2])

            telemetry_data = {
                "camera_code": self.code,
                "node": active_node,
                "cm4_power_state": self.cm4_power_state,
                "force_power_on": self.force_power_on,
                "sim_active_node": active_node,
                "sim_signal_dbm": max(-105, min(-55, sim_dbm)),
                "firmware_version": "cm4-power-agent-v2.0",
                "timestamp": now_dt.isoformat(),
            }

            self.mqtt_client.publish(self.t_data, json.dumps(telemetry_data), qos=1)
            log.info("📡 [TELEMETRY EC25] Node: %s | cm4=%s | force_on=%s | Signal: %ddBm",
                     active_node, self.cm4_power_state,
                     self.force_power_on, telemetry_data["sim_signal_dbm"])
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
        log.info("  Server Base: %s", self.server_base)
        log.info("  Chu kỳ Telemetry: %ds", self.telemetry_interval)
        log.info("  State file: %s", self.state_file)
        log.info("=" * 65)

        # ── Kéo trạng thái force_power_on từ server ngay khi khởi động ──
        # Điều này đảm bảo EC25 biết được người dùng đã tắt hay bật cưỡng bức,
        # tránh EC25 ngắt nguồn CM4 nhong lúc CM4 đang được bật cưỡng bức
        # mà chưa kịp đồng bộ state.
        threading.Thread(
            target=self.pull_server_config,
            name="init_config_pull",
            daemon=True
        ).start()

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
    parser.add_argument("--server", default=os.getenv("SERVER_BASE", "https://cloud.congnghetimelapse.com"), help="Server Base URL")
    parser.add_argument("--state-file", default=os.getenv("EC25_STATE_FILE", "/app/offline_queue/ec25_state.json"), help="Đường dẫn file state EC25")

    args = parser.parse_args()
    agent = CM4PowerAgent(
        args.code, args.secret, args.broker, args.port, args.interval,
        server_base=args.server,
        state_file=args.state_file,
    )

    def _sig_handler(sig, frame):
        agent.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _sig_handler)
    signal.signal(signal.SIGTERM, _sig_handler)
    agent.start()


if __name__ == "__main__":
    main()
