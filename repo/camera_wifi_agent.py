#!/usr/bin/env python3
"""
Camera WiFi Agent - Chạy trực tiếp trên Máy tính / Laptop / CM4 qua WiFi.
Tự động nhận diện Máy ảnh thật (qua USB gphoto2) hoặc Tự động Chuyển sang Giả lập (PIL) nếu chưa cắm máy ảnh.

Tính năng:
1. Kết nối Máy ảnh thật qua python-gphoto2 (Nikon / Canon / Sony DSLR/Mirrorless).
2. Fallback thông minh: Tự chuyển sang chế độ Chụp giả lập nếu chưa cài gphoto2 hoặc chưa cắm USB.
3. Không cần ESP32-S3 hardware: Tự duy trì cm4_power_state = "running".
4. Giả lập Telemetry SIM/Solar (do đang chạy mạng WiFi).
5. Upload ảnh S3 Presigned Workflow chuẩn (Presign PUT S3 -> Complete API).
6. Stream Live View frame mượt mà về Django Backend.

Cách chạy:
    python3 camera_wifi_agent.py
"""

import argparse
import io
import json
import logging
import random
import sys
import threading
import queue as _queue
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone

from PIL import Image, ImageDraw

# Kiểm tra thư viện gphoto2
GPHOTO2_AVAILABLE = False
try:
    import gphoto2 as gp
    GPHOTO2_AVAILABLE = True
except ImportError:
    gp = None

# Kiểm tra thư viện paho-mqtt
try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("❌ Lỗi: Chưa cài đặt paho-mqtt. Hãy chạy: pip install paho-mqtt pillow")
    sys.exit(1)

# ── Cấu hình mặc định khi chạy Local ─────────────────────────────────────────
DEFAULT_CAMERA_CODE   = "CAM-F53RQV"
DEFAULT_MQTT_PASSWORD = "8_2Vhy43gl6GcPvMuDu3eQ"
DEFAULT_MQTT_BROKER   = "localhost"
DEFAULT_MQTT_PORT     = 1884  # Docker compose map 1884:1883 ra host
DEFAULT_SERVER_BASE   = "http://localhost"  # Nginx listening on port 80
# ────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("camera_wifi_agent")

# Cấu hình danh sách thông số máy ảnh hỗ trợ
_SETTING_SPECS = {
    "iso":                   ("iso",                 True),
    "aperture":              ("f-number",            True),
    "shutter_speed":         ("shutterspeed2",       True),
    "exposure_compensation": ("exposurecompensation",True),
    "white_balance":         ("whitebalance",        True),
    "image_format":          ("imagequality",        True),
    "image_size":            ("imagesize",           True),
    "focus_mode":            ("focusmode2",          True),
    "autofocus":             ("autofocus",           True),
    "capture_mode":          ("capturemode",         True),
    "capture_target":        ("capturetarget",       True),
    "high_iso_nr":           ("highisonr",           True),
    "long_exp_nr":           ("longexpnr",           True),
    "liveview_af":           ("liveviewaffocus",     True),
    "exposure_mode":         ("expprogram",          False),
    "focus_switch":          ("focusmode",           False),
}

_SIM_INFO_TELEMETRY = {
    "operator": "Viettel 4G (WiFi Simulated)",
    "number": "+84987654321",
    "iccid": "8984047123456789012",
}

# ── CAMERA BACKEND (Hybrid Real gphoto2 + Simulated Fallback) ───────────────

class HybridCameraBackend:
    """Quản lý máy ảnh thật (gphoto2 USB) kết hợp Fallback Giả lập (PIL)."""

    def __init__(self):
        self._lock = threading.Lock()
        self._camera = None
        self.use_real_hardware = False
        
        # Simulated fallback state
        self._sim_applied = {
            "iso": "100", "aperture": "f/4", "shutter_speed": "1/200",
            "exposure_compensation": "0.0", "white_balance": "Auto",
            "image_format": "JPEG Fine", "image_size": "6000x4000",
            "focus_mode": "AF-S", "autofocus": "On", "capture_mode": "Single Shot",
            "capture_target": "Memory Card", "high_iso_nr": "Off",
            "long_exp_nr": "Off", "liveview_af": "Normal Area",
            "exposure_mode": "Manual", "focus_switch": "AF",
        }
        
        if GPHOTO2_AVAILABLE:
            self._try_init_real_camera()

    def _try_init_real_camera(self):
        """Thử kết nối máy ảnh thật qua USB gphoto2."""
        with self._lock:
            if self._camera is not None:
                return True
            try:
                cam = gp.Camera()
                cam.init()
                self._camera = cam
                self.use_real_hardware = True
                
                # Tự động set imagequality = JPEG Fine
                try:
                    config = cam.get_config()
                    try:
                        q = config.get_child_by_name("imagequality")
                        q.set_value("JPEG Fine")
                        cam.set_config(config)
                    except Exception:
                        pass
                except Exception:
                    pass

                summary = cam.get_summary()
                log.info("📷 Đã kết nối MÁY ẢNH THẬT qua USB gphoto2! (%s)", str(summary).split('\n')[0])
                return True
            except Exception:
                self._camera = None
                self.use_real_hardware = False
                log.info("ℹ️ Không tìm thấy máy ảnh USB gphoto2 — Tự động dùng Chế độ Giả Lập Ảnh (PIL).")
                return False

    def _disconnect_real_camera(self):
        if self._camera is not None:
            try:
                self._camera.exit()
            except Exception:
                pass
            self._camera = None
            self.use_real_hardware = False

    def get_settings(self):
        if GPHOTO2_AVAILABLE and not self.use_real_hardware:
            self._try_init_real_camera()

        if self.use_real_hardware:
            with self._lock:
                try:
                    config = self._camera.get_config()
                    applied = {}
                    capabilities = {}
                    for field, (widget_name, settable) in _SETTING_SPECS.items():
                        try:
                            widget = config.get_child_by_name(widget_name)
                            val = str(widget.get_value())
                            applied[field] = val
                            wtype = widget.get_type()
                            choices = [str(widget.get_choice(i)) for i in range(widget.count_choices())] if wtype in (5, 6) else []
                            capabilities[field] = {
                                "writable": settable and not bool(widget.get_readonly()),
                                "current": val,
                                "choices": choices,
                            }
                        except Exception:
                            pass
                    return applied, capabilities
                except Exception as e:
                    log.warning("Lỗi đọc cấu hình máy ảnh thật (%s) — reconnecting...", e)
                    self._disconnect_real_camera()

        # Fallback Simulated
        capabilities = {
            k: {
                "writable": v[1],
                "current": self._sim_applied[k],
                "choices": [self._sim_applied[k], "Option1", "Option2"] if v[1] else [],
            }
            for k, v in _SETTING_SPECS.items()
        }
        capabilities["iso"]["choices"] = ["100", "200", "400", "800", "1600", "3200", "6400"]
        capabilities["aperture"]["choices"] = ["f/2.8", "f/4", "f/5.6", "f/8", "f/11", "f/16"]
        capabilities["shutter_speed"]["choices"] = ["1/4000", "1/2000", "1/1000", "1/500", "1/200", "1/100"]
        capabilities["white_balance"]["choices"] = ["Auto", "Daylight", "Cloudy", "Shade", "Tungsten"]
        return dict(self._sim_applied), capabilities

    def set_settings(self, requested):
        if self.use_real_hardware:
            with self._lock:
                try:
                    config = self._camera.get_config()
                    for field, val in requested.items():
                        if field in _SETTING_SPECS and _SETTING_SPECS[field][1]:
                            widget_name = _SETTING_SPECS[field][0]
                            try:
                                widget = config.get_child_by_name(widget_name)
                                if not widget.get_readonly():
                                    widget.set_value(str(val))
                            except Exception:
                                pass
                    self._camera.set_config(config)
                except Exception as e:
                    log.warning("Không thể áp dụng cấu hình lên máy ảnh thật: %s", e)

        # Update simulated local state as well
        settable = {f for f, (_, ok) in _SETTING_SPECS.items() if ok}
        for field, val in requested.items():
            if field in settable:
                self._sim_applied[field] = str(val)

        applied, capabilities = self.get_settings()
        mismatches = {k: {"requested": v, "applied": applied.get(k)} for k, v in requested.items() if applied.get(k) != str(v)}
        return applied, capabilities, mismatches

    def capture(self, camera_code="CAM-WIFI"):
        """Chụp ảnh từ máy ảnh thật (gphoto2) hoặc sinh ảnh giả lập bằng PIL."""
        if GPHOTO2_AVAILABLE and not self.use_real_hardware:
            self._try_init_real_camera()

        if self.use_real_hardware:
            with self._lock:
                try:
                    log.info("📸 [REAL CAMERA] Đang phát lệnh màn trập chụp ảnh...")
                    
                    # Exit live view if open to allow autofocus
                    try:
                        config = self._camera.get_config()
                        vf = config.get_child_by_name("viewfinder")
                        if int(vf.get_value()) != 0:
                            vf.set_value(0)
                            self._camera.set_config(config)
                            time.sleep(0.4)
                    except Exception:
                        pass

                    first_path = self._camera.capture(gp.GP_CAPTURE_IMAGE)
                    paths = {(first_path.folder, first_path.name): first_path}

                    # Chờ hoàn tất ghi file trên thẻ nhớ máy ảnh
                    deadline = time.monotonic() + 4
                    while time.monotonic() < deadline:
                        event_type, event_data = self._camera.wait_for_event(400)
                        if event_type == gp.GP_EVENT_FILE_ADDED:
                            paths[(event_data.folder, event_data.name)] = event_data
                        elif event_type == gp.GP_EVENT_CAPTURE_COMPLETE:
                            break

                    files = []
                    for path in list(paths.values()):
                        ext = path.name.lower().split('.')[-1]
                        if ext in ("thm", "tif", "tiff") and len(paths) > 1:
                            continue
                        
                        camera_file = self._camera.file_get(path.folder, path.name, gp.GP_FILE_TYPE_NORMAL)
                        data = bytes(camera_file.get_data_and_size())

                        preview_data = None
                        try:
                            preview_file = self._camera.file_get(path.folder, path.name, gp.GP_FILE_TYPE_PREVIEW)
                            preview_data = bytes(preview_file.get_data_and_size())
                        except Exception:
                            pass

                        try:
                            self._camera.file_delete(path.folder, path.name)
                        except Exception:
                            pass

                        files.append((path.name, data, preview_data))

                    if files:
                        log.info("✅ Chụp ảnh thật thành công (%d file, %d bytes)", len(files), len(files[0][1]))
                        return files
                except Exception as e:
                    log.error("Lỗi chụp máy ảnh thật (%s) — Chuyển sang fallback chụp giả lập...", e)
                    self._disconnect_real_camera()

        # Fallback Simulated PIL Image
        log.info("📸 [SIMULATED CAMERA] Đang tạo khung hình giả lập JPEG bằng PIL...")
        time.sleep(0.5)
        img_bytes = self._generate_simulated_image(camera_code=camera_code)
        filename = f"WIFI_CAM_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        return [(filename, img_bytes, None)]

    def preview(self):
        """Lấy frame preview cho Live View."""
        if GPHOTO2_AVAILABLE and not self.use_real_hardware:
            self._try_init_real_camera()

        if self.use_real_hardware:
            with self._lock:
                try:
                    camera_file = self._camera.capture_preview()
                    return bytes(camera_file.get_data_and_size())
                except Exception:
                    pass
        # Fallback simulated preview frame
        return self._generate_simulated_image(width=640, height=424, title="Live View WiFi Stream")

    def _generate_simulated_image(self, width=1920, height=1080, title="AutoTimelapse Camera", camera_code="CAM-WIFI"):
        img = Image.new("RGB", (width, height), color=(20, 24, 33))
        draw = ImageDraw.Draw(img)

        # Background gradient
        for y in range(0, height, 4):
            r = int(20 + (y / height) * 35)
            g = int(24 + (y / height) * 45)
            b = int(33 + (y / height) * 65)
            draw.rectangle([(0, y), (width, y + 4)], fill=(r, g, b))

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        draw.rectangle([40, 40, width - 40, height - 40], outline=(0, 210, 255), width=3)
        draw.rectangle([60, 60, width - 60, 140], fill=(10, 15, 25))

        hw_type = "REAL HARDWARE (USB)" if self.use_real_hardware else "SIMULATED (PIL)"
        draw.text((80, 75), f"📷 {title} - {camera_code} [{hw_type}]", fill=(0, 230, 255))
        draw.text((80, 105), f"🕒 Timestamp: {now_str} UTC | WiFi Network Mode", fill=(200, 220, 240))

        # Simulated construction site objects
        draw.rectangle([100, 200, 400, height - 100], fill=(45, 55, 72), outline=(100, 116, 139), width=2)
        draw.rectangle([450, 300, 800, height - 100], fill=(30, 41, 59), outline=(100, 116, 139), width=2)
        draw.polygon([(450, 300), (625, 180), (800, 300)], fill=(71, 85, 105))

        # Display specs
        iso = self._sim_applied.get("iso", "100")
        aperture = self._sim_applied.get("aperture", "f/4")
        shutter = self._sim_applied.get("shutter_speed", "1/200")
        wb = self._sim_applied.get("white_balance", "Auto")
        info_text = f"ISO: {iso} | Aperture: {aperture} | Shutter: {shutter} | WB: {wb}"
        draw.text((80, height - 80), f"⚙️ {info_text}", fill=(160, 255, 160))

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return buf.getvalue()


# ── MAIN WORKFLOW ────────────────────────────────────────────────────────────

class CameraAgent:
    def __init__(self, code, password, broker, port, server_base):
        self.code = code
        self.password = password
        self.broker = broker
        self.port = port
        self.server_base = server_base.rstrip("/")
        
        self.backend = HybridCameraBackend()
        self.capture_interval_sec = 0
        self.live_session_id = None
        self.live_fps = 1
        self.live_seq = 0
        self.cmd_queue = _queue.SimpleQueue()
        self.mqtt_client = None

        self.t_cmd = f"camera/{self.code}/cmd"
        self.t_ack = f"camera/{self.code}/ack"
        self.t_data = f"camera/{self.code}/data"
        self.t_status = f"camera/{self.code}/status"

    def _http_post_json(self, path, obj, *, _max_retries=3, _retry_delay=2):
        """POST JSON và trả (status, dict). Tự động retry khi gặp 502/503/504."""
        body = json.dumps(obj).encode()
        req = urllib.request.Request(
            self.server_base + path, data=body, method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Device-Key": self.code,
                "X-Device-Secret": self.password,
            },
        )
        last_exc = None
        for attempt in range(1, _max_retries + 2):  # 1 lần gốc + max_retries lần retry
            try:
                with urllib.request.urlopen(req, timeout=15) as r:
                    return r.status, json.loads(r.read().decode() or "{}")
            except urllib.error.HTTPError as exc:
                # Chỉ retry với lỗi tạm thời của server/gateway
                if exc.code in (502, 503, 504) and attempt <= _max_retries:
                    wait = _retry_delay * (2 ** (attempt - 1))  # 2s, 4s, 8s
                    log.warning("[Retry %d/%d] HTTP %d trên %s, thử lại sau %ds...",
                                attempt, _max_retries, exc.code, path, wait)
                    time.sleep(wait)
                    last_exc = exc
                else:
                    raise
            except (OSError, TimeoutError) as exc:
                # Network timeout/reset — cũng đáng retry
                if attempt <= _max_retries:
                    wait = _retry_delay * (2 ** (attempt - 1))
                    log.warning("[Retry %d/%d] Network error trên %s: %s, thử sau %ds...",
                                attempt, _max_retries, path, exc, wait)
                    time.sleep(wait)
                    last_exc = exc
                else:
                    raise
        raise last_exc  # hết retry vẫn lỗi → báo lên


    def _http_post_frame(self, session_id, seq, frame_bytes):
        req = urllib.request.Request(
            self.server_base + "/api/device/live/frame/",
            data=frame_bytes, method="POST",
            headers={
                "Content-Type": "image/jpeg",
                "X-Device-Key": self.code,
                "X-Device-Secret": self.password,
                "X-Live-Session": session_id,
                "X-Frame-Seq": str(seq),
            },
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read().decode() or "{}")

    def _http_put(self, url, data, content_type):
        req = urllib.request.Request(url, data=data, method="PUT", headers={"Content-Type": content_type})
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status

    def upload_capture(self):
        taken_at = datetime.now(timezone.utc).isoformat()
        captured_files = self.backend.capture(camera_code=self.code)
        media_ids = []
        for filename, image_bytes, thumb in captured_files:
            content_type = "image/jpeg"
            
            # Đảm bảo file ảnh 100% là định dạng JPEG chuẩn cho trình duyệt web
            final_bytes, width, height = self._normalize_image_bytes(image_bytes, thumb)

            # Sinh thumbnail (480x320) nếu chưa có
            if thumb is None:
                try:
                    with Image.open(io.BytesIO(final_bytes)) as im:
                        thumb_im = im.copy()
                        thumb_im.thumbnail((480, 320))
                        output = io.BytesIO()
                        thumb_im.save(output, "JPEG", quality=82)
                        thumb = output.getvalue()
                except Exception as e:
                    log.warning("Lỗi tạo thumbnail từ final_bytes: %s", e)

            try:
                st, pre = self._http_post_json("/api/device/upload/presign/", {
                    "content_type": content_type,
                    "taken_at": taken_at,
                    "with_thumb": thumb is not None,
                })
                if st != 200:
                    log.error("Lỗi xin Presigned URL: %s %s", st, pre)
                    continue

                self._http_put(pre["url"], final_bytes, content_type)
                if thumb is not None:
                    self._http_put(pre["thumb_url"], thumb, "image/jpeg")

                st, done = self._http_post_json("/api/device/upload/complete/", {
                    "media_id": pre["media_id"],
                    "key": pre["key"],
                    "thumb_key": pre.get("thumb_key"),
                    "taken_at": taken_at,
                    "width": width,
                    "height": height,
                    "content_type": content_type,
                    "source_name": filename,
                    "size_bytes": len(final_bytes),
                })
                if st == 200 and done.get("ok"):
                    log.info("🎉 Upload THÀNH CÔNG! media_id=%s file=%s (%d bytes, %dx%d)",
                             done["media_id"], filename, len(final_bytes), width, height)
                    media_ids.append(done["media_id"])
                else:
                    log.error("Complete upload thất bại: %s %s", st, done)
            except Exception as exc:
                log.exception("Upload ảnh thất bại: %s", exc)
        return media_ids

    def _normalize_image_bytes(self, raw_bytes, preview_bytes=None):
        """Đảm bảo byte trả về là định dạng JPEG chuẩn mà trình duyệt Web mở được."""
        # 1. Thử dùng preview_bytes nếu data gốc không phải JPEG
        if preview_bytes:
            try:
                with Image.open(io.BytesIO(preview_bytes)) as prv_im:
                    pw, ph = prv_im.size
                    if prv_im.format == "JPEG" and pw >= 600 and ph >= 400:
                        return preview_bytes, pw, ph
            except Exception:
                pass

        # 2. Decode raw_bytes
        try:
            with Image.open(io.BytesIO(raw_bytes)) as im:
                w, h = im.size
                if im.format == "JPEG" and w >= 600 and h >= 400:
                    return raw_bytes, w, h

                # Nếu là RAW/TIFF hoặc kích thước nhỏ (preview 160x120), convert/re-encode
                buf = io.BytesIO()
                rgb = im.convert("RGB")
                rgb.save(buf, format="JPEG", quality=90)
                res = buf.getvalue()
                return res, rgb.size[0], rgb.size[1]
        except Exception as e:
            log.warning("Không thể parse định dạng ảnh (%s), giữ nguyên byte", e)
            return raw_bytes, 1920, 1080

    def publish_telemetry(self):
        payload = {
            "node": "cm4",
            "cm4_power_state": "running",
            "sim_active_node": "cm4",
            "battery_percent": random.randint(90, 100),
            "battery_voltage": round(random.uniform(12.2, 12.6), 3),
            "cell_voltages": [3.8, 3.8, 3.8],
            "is_charging": True,
            "solar_voltage": round(random.uniform(14.0, 18.0), 2),
            "solar_percent": 100,
            "temperature_c": round(random.uniform(28.0, 35.0), 1),
            "humidity_percent": random.randint(55, 75),
            "sim_signal_dbm": random.randint(-75, -60),
            "firmware_version": "camera-wifi-agent-v1.0",
        }
        if self.mqtt_client and self.mqtt_client.is_connected():
            self.mqtt_client.publish(self.t_data, json.dumps(payload), qos=1)
            log.info("📡 Gửi Telemetry [WiFi]: Pin %s%%, %.1f°C, Hardware: %s",
                     payload["battery_percent"], payload["temperature_c"],
                     "GPHOTO2_USB" if self.backend.use_real_hardware else "SIMULATED_PIL")

    def process_command(self, req):
        cmd = req.get("command", "")
        rid = req.get("request_id", "")
        payload = req.get("payload") or {}
        log.info("📥 Nhận lệnh MQTT từ Server: %s (req_id=%s)", cmd, rid)

        try:
            if cmd in ("power_on_cm4", "power_on"):
                resp = {"type": cmd, "request_id": rid, "status": "ok", "data": {"cm4_power_state": "running"}}

            elif cmd == "set_settings":
                applied, capabilities, mismatches = self.backend.set_settings(payload)
                resp = {"type": cmd, "request_id": rid, "status": "ok",
                        "data": {"requested": payload, "applied": applied, "capabilities": capabilities, "mismatches": mismatches}}

            elif cmd in ("get_settings", "get_capabilities", "get_status"):
                applied, capabilities = self.backend.get_settings()
                resp = {"type": cmd, "request_id": rid, "status": "ok",
                        "data": {"online": True, "applied": applied, "capabilities": capabilities, "live_view": bool(self.live_session_id)}}

            elif cmd == "get_sim_info":
                resp = {"type": "get_sim_info", "request_id": rid, "status": "ok",
                        "data": {"sim": {**_SIM_INFO_TELEMETRY, "signal_dbm": -65}}}

            elif cmd in ("capture_now", "capture"):
                media_ids = self.upload_capture()
                if media_ids:
                    resp = {"type": cmd, "request_id": rid, "status": "ok", "data": {"media_id": media_ids[0], "media_ids": media_ids}}
                else:
                    resp = {"type": cmd, "request_id": rid, "status": "error", "data": {"note": "Upload ảnh thất bại"}}

            elif cmd == "set_interval":
                val = max(0, int(payload.get("capture_interval_sec", self.capture_interval_sec)))
                self.capture_interval_sec = val
                resp = {"type": "set_interval", "request_id": rid, "status": "ok", "data": {"capture_interval_sec": val}}

            elif cmd == "start_live_view":
                self.live_session_id = payload.get("session_id") or "lv-wifi"
                self.live_fps = max(1, min(2, int(payload.get("fps") or 1)))
                self.live_seq = 0
                resp = {"type": "start_live_view", "request_id": rid, "status": "ok",
                        "data": {"live_view": True, "session_id": self.live_session_id, "fps": self.live_fps}}

            elif cmd == "stop_live_view":
                self.live_session_id = None
                resp = {"type": "stop_live_view", "request_id": rid, "status": "ok", "data": {"live_view": False}}

            else:
                resp = {"type": cmd, "request_id": rid, "status": "error", "data": {"note": f"Lệnh chưa hỗ trợ: {cmd}"}}

        except Exception as exc:
            log.exception("Xử lý lệnh %s lỗi: %s", cmd, exc)
            resp = {"type": cmd, "request_id": rid, "status": "error", "data": {"note": str(exc)}}

        if self.mqtt_client and self.mqtt_client.is_connected():
            self.mqtt_client.publish(self.t_ack, json.dumps(resp), qos=1)

    def live_view_thread(self):
        while True:
            if not self.live_session_id:
                time.sleep(0.5)
                continue
            self.live_seq += 1
            try:
                frame = self.backend.preview()
                st, resp = self._http_post_frame(self.live_session_id, self.live_seq, frame)
                if st == 200 and resp.get("ok"):
                    log.debug("Stream live frame seq=%d (%d bytes)", self.live_seq, len(frame))
            except Exception as e:
                log.warning("Lỗi stream live view: %s", e)
            time.sleep(max(0.5, 1.0 / max(1, self.live_fps)))

    def capture_loop_thread(self):
        while True:
            wait = self.capture_interval_sec
            if wait <= 0:
                time.sleep(2)
                continue
            log.info("Chu kỳ chụp kế tiếp sau %d giây", wait)
            for _ in range(wait):
                time.sleep(1)
                if self.capture_interval_sec != wait:
                    break
            else:
                try:
                    self.upload_capture()
                except Exception:
                    log.exception("Capture loop error")

    def cmd_worker_thread(self):
        while True:
            raw = self.cmd_queue.get()
            try:
                self.process_command(raw)
            except Exception as exc:
                log.error("cmd_worker error: %s", exc)

    def start(self):
        log.info("==========================================================")
        log.info("🚀 KHỞI ĐỘNG CAMERA WIFI AGENT (Local Testing Mode)")
        log.info("📷 Code Camera: %s", self.code)
        log.info("📡 MQTT Broker: %s:%d", self.broker, self.port)
        log.info("🌐 Server Base : %s", self.server_base)
        log.info("==========================================================")

        threading.Thread(target=self.live_view_thread, daemon=True, name="liveview").start()
        threading.Thread(target=self.capture_loop_thread, daemon=True, name="capture").start()
        threading.Thread(target=self.cmd_worker_thread, daemon=True, name="cmd_worker").start()

        def on_connect(client, userdata, flags, rc, props=None):
            log.info("✅ Đã kết nối MQTT Broker thành công!")
            client.subscribe(self.t_cmd, qos=1)
            client.publish(self.t_status, json.dumps({"online": True}), qos=1, retain=True)
            self.publish_telemetry()

        def on_message(client, userdata, msg):
            try:
                raw = json.loads(msg.payload.decode())
                self.cmd_queue.put(raw)
            except Exception as exc:
                log.error("Lỗi giải mã MQTT message: %s", exc)

        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=self.code)
        client.username_pw_set(self.code, self.password)
        client.will_set(self.t_status, json.dumps({"online": False}), qos=1, retain=True)
        client.on_connect = on_connect
        client.on_message = on_message

        self.mqtt_client = client

        try:
            client.connect(self.broker, self.port, keepalive=60)
        except Exception as e:
            log.error("❌ Không thể kết nối MQTT Broker tại %s:%d (%s)", self.broker, self.port, e)
            sys.exit(1)

        client.loop_start()

        last_telemetry = time.time()
        try:
            while True:
                time.sleep(1)
                if time.time() - last_telemetry >= 30:
                    self.publish_telemetry()
                    last_telemetry = time.time()
        except KeyboardInterrupt:
            log.info("\n⏹ Đang dừng Agent...")
        finally:
            client.publish(self.t_status, json.dumps({"online": False}), qos=1, retain=True)
            client.loop_stop()
            client.disconnect()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AutoTimelapse WiFi Camera Agent")
    parser.add_argument("--code", default=DEFAULT_CAMERA_CODE, help=f"Mã định danh Camera (Code) [Mặc định: {DEFAULT_CAMERA_CODE}]")
    parser.add_argument("--secret", default=DEFAULT_MQTT_PASSWORD, help="Mật khẩu thiết bị / MQTT Password")
    parser.add_argument("--broker", default=DEFAULT_MQTT_BROKER, help=f"Địa chỉ MQTT Broker [Mặc định: {DEFAULT_MQTT_BROKER}]")
    parser.add_argument("--port", type=int, default=DEFAULT_MQTT_PORT, help=f"Cổng MQTT Broker [Mặc định: {DEFAULT_MQTT_PORT}]")
    parser.add_argument("--server", default=DEFAULT_SERVER_BASE, help=f"Địa chỉ Django Backend [Mặc định: {DEFAULT_SERVER_BASE}]")

    args = parser.parse_args()

    agent = CameraAgent(
        code=args.code,
        password=args.secret,
        broker=args.broker,
        port=args.port,
        server_base=args.server,
    )
    agent.start()
