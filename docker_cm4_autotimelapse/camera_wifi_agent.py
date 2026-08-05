#!/usr/bin/env python3
"""
AutoTimelapse CM4 Camera Agent
------------------------------------------------------------------
Agent điều khiển Máy ảnh (Nikon/Canon/Sony/DSLR/Mirrorless) chạy trên
Raspberry Pi CM4 (hoặc PC/Docker) qua WiFi / Ethernet.

Tính năng nổi bật:
1. Đưa tất cả biến cấu hình Server/MQTT/GPIO ra ngoài (Env vars & Args).
2. Quản lý Nguồn máy ảnh qua GPIO 16 (Bật nguồn trước khi chụp/LiveView, Tắt sau khi xong).
3. Hỗ trợ máy ảnh thật qua gphoto2 (USB) & Tự động Fallback sang Giả lập PIL nếu không phát hiện phần cứng.
4. Cơ chế Hàng Đợi Offline (Offline Queue Buffer): Tự động lưu ảnh xuống đĩa (/app/offline_queue) khi mất mạng/lỗi server và thử gửi lại định kỳ.
5. Upload ảnh S3 Presigned Workflow chuẩn (Presigned PUT -> Complete API).
6. Stream Live View frame về Server qua HTTP POST.
7. Tương thích Docker container chạy trên Raspberry Pi CM4 với passthrough USB, GPIO (/dev/gpiomem, /dev/bus/usb).
"""

import os
import sys
import io
import json
import time
import random
import logging
import argparse
import signal
import threading
import queue as _queue
import urllib.request
import urllib.error
from datetime import datetime, timezone

from PIL import Image, ImageDraw

# ── Kiểm tra thư viện gphoto2 ────────────────────────────────────────────────
GPHOTO2_AVAILABLE = False
try:
    import gphoto2 as gp
    GPHOTO2_AVAILABLE = True
except ImportError:
    gp = None

# ── Kiểm tra thư viện paho-mqtt ──────────────────────────────────────────────
try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("❌ Lỗi: Chưa cài đặt paho-mqtt. Hãy chạy: pip install paho-mqtt pillow")
    sys.exit(1)

# ── Kiểm tra RPi.GPIO cho CM4 Hardware ───────────────────────────────────────
HAS_GPIO = False
try:
    import RPi.GPIO as GPIO
    HAS_GPIO = True
except (ImportError, RuntimeError):
    GPIO = None

# ── CẤU HÌNH TỪ BIẾN MÔI TRƯỜNG (ENVIRONMENT VARIABLES) ──────────────────────
CAMERA_CODE            = os.getenv("CAMERA_CODE", "CAM-4YZ8X6")
MQTT_PASSWORD          = os.getenv("MQTT_PASSWORD", os.getenv("DEVICE_SECRET", "o2hs_IojnvqSXlF1b9M-sg"))
MQTT_BROKER            = os.getenv("MQTT_BROKER", "cloud.congnghetimelapse.com")
MQTT_PORT              = int(os.getenv("MQTT_PORT", "1884"))
SERVER_BASE            = os.getenv("SERVER_BASE", "http://cloud.congnghetimelapse.com")

POWER_GPIO_PIN         = int(os.getenv("POWER_GPIO_PIN", "16"))
POWER_ACTIVE_HIGH      = os.getenv("POWER_ACTIVE_HIGH", "true").lower() in ("true", "1", "yes")
WARMUP_DELAY_SEC       = float(os.getenv("WARMUP_DELAY_SEC", "3.0"))
ALWAYS_KEEP_POWER      = os.getenv("ALWAYS_KEEP_POWER", "false").lower() in ("true", "1", "yes")
TELEMETRY_INTERVAL     = int(os.getenv("TELEMETRY_INTERVAL", "30"))

OFFLINE_QUEUE_DIR      = os.getenv("OFFLINE_QUEUE_DIR", "/app/offline_queue")
OFFLINE_RETRY_INTERVAL = int(os.getenv("OFFLINE_RETRY_INTERVAL", "60"))

# Logging format setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(threadName)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("cm4_camera_agent")


# ── OFFLINE QUEUE MANAGER (LƯU VÀ GỬI LẠI ĐỊNH KỲ KHI MẤT MẠNG) ─────────────

class OfflineQueueManager:
    """Quản lý hàng đợi ảnh lưu tạm dưới đĩa khi mất mạng hoặc server lỗi."""

    def __init__(self, queue_dir="/app/offline_queue"):
        self.queue_dir = queue_dir
        self._lock = threading.Lock()
        os.makedirs(self.queue_dir, exist_ok=True)
        log.info("📁 [OFFLINE QUEUE] Đã khởi tạo thư mục lưu trữ đệm: %s", self.queue_dir)

    def save_pending_capture(self, image_bytes, thumb_bytes, metadata):
        """Lưu ảnh và metadata xuống đĩa khi không thể gửi server."""
        with self._lock:
            ts_str = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            base_name = f"pending_{ts_str}"
            img_path = os.path.join(self.queue_dir, f"{base_name}.jpg")
            json_path = os.path.join(self.queue_dir, f"{base_name}.json")
            thumb_path = os.path.join(self.queue_dir, f"{base_name}_thumb.jpg") if thumb_bytes else None

            try:
                with open(img_path, "wb") as f:
                    f.write(image_bytes)

                if thumb_bytes and thumb_path:
                    with open(thumb_path, "wb") as f:
                        f.write(thumb_bytes)
                    metadata["thumb_filename"] = f"{base_name}_thumb.jpg"

                metadata["image_filename"] = f"{base_name}.jpg"

                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(metadata, f, indent=2)

                log.warning("💾 [OFFLINE QUEUE] Đã lưu tạm 1 ảnh lỗi/mất mạng vào %s", json_path)
            except Exception as e:
                log.error("❌ Không thể lưu ảnh vào hàng đợi offline: %s", e)

    def process_pending_queue(self, upload_fn):
        """Duyệt các ảnh pending và thử gửi lại server."""
        with self._lock:
            try:
                json_files = sorted([f for f in os.listdir(self.queue_dir) if f.endswith(".json") and f.startswith("pending_")])
            except Exception as e:
                log.error("Lỗi đọc thư mục offline queue: %s", e)
                return

            if not json_files:
                return

            log.info("🔄 [OFFLINE QUEUE] Phát hiện %d ảnh chờ upload lại...", len(json_files))
            for json_file in json_files:
                json_path = os.path.join(self.queue_dir, json_file)
                try:
                    with open(json_path, "r", encoding="utf-8") as f:
                        meta = json.load(f)

                    img_filename = meta.get("image_filename")
                    img_path = os.path.join(self.queue_dir, img_filename) if img_filename else None
                    if not img_path or not os.path.exists(img_path):
                        log.warning("Xóa metadata mồ côi: %s", json_file)
                        os.remove(json_path)
                        continue

                    with open(img_path, "rb") as f:
                        image_bytes = f.read()

                    thumb_bytes = None
                    thumb_filename = meta.get("thumb_filename")
                    if thumb_filename:
                        t_path = os.path.join(self.queue_dir, thumb_filename)
                        if os.path.exists(t_path):
                            with open(t_path, "rb") as f:
                                thumb_bytes = f.read()

                    # Thử upload lại
                    ok, media_id = upload_fn(image_bytes, thumb_bytes, meta)
                    if ok:
                        log.info("🎉 [OFFLINE QUEUE SUCCESS] Đã gửi lại ảnh offline thành công! media_id=%s", media_id)
                        try:
                            os.remove(json_path)
                            os.remove(img_path)
                            if thumb_filename:
                                t_path = os.path.join(self.queue_dir, thumb_filename)
                                if os.path.exists(t_path):
                                    os.remove(t_path)
                        except Exception as e:
                            log.warning("Lỗi dọn dẹp file offline: %s", e)
                    else:
                        log.warning("⚠️ Upload lại ảnh offline %s chưa thành công. Sẽ thử lại lần sau...", json_file)
                        break  # Dừng batch đợt này để tránh spam server nếu server vẫn chưa sẵn sàng
                except Exception as e:
                    log.error("Lỗi xử lý file offline %s: %s", json_file, e)


# ── CAMERA POWER MANAGER (GPIO 16 CONTROL) ───────────────────────────────────

class CameraPowerManager:
    """Quản lý nguồn cấp điện cho máy ảnh qua GPIO 16 trên Raspberry Pi CM4."""

    def __init__(self, pin=16, active_high=True, warmup_delay=3.0):
        self.pin = pin
        self.active_high = active_high
        self.warmup_delay = warmup_delay
        self.is_powered = False
        self.has_hardware_gpio = HAS_GPIO
        self._lock = threading.Lock()

        self._init_gpio()

    def _init_gpio(self):
        if self.has_hardware_gpio:
            try:
                GPIO.setmode(GPIO.BCM)
                GPIO.setwarnings(False)
                GPIO.setup(self.pin, GPIO.OUT)
                off_state = GPIO.HIGH if not self.active_high else GPIO.LOW
                GPIO.output(self.pin, off_state)
                log.info("⚡ [GPIO] Đã khởi tạo thành công GPIO Pin %d điều khiển nguồn Máy ảnh", self.pin)
            except Exception as e:
                log.warning("⚠️ Không thể cấu hình GPIO Pin %d: %s. Chuyển sang Giả lập GPIO.", self.pin, e)
                self.has_hardware_gpio = False
        else:
            log.info("ℹ️ Không tìm thấy phần cứng RPi.GPIO. Quản lý nguồn chạy ở chế độ GIẢ LẬP (Simulated GPIO %d).", self.pin)

    def power_on(self):
        """Bật nguồn máy ảnh và chờ phần cứng khởi động (warmup delay)."""
        with self._lock:
            if not self.is_powered:
                log.info("🔌 [POWER ON] Đang BẬT NGUỒN máy ảnh qua GPIO %d...", self.pin)
                if self.has_hardware_gpio:
                    on_state = GPIO.HIGH if self.active_high else GPIO.LOW
                    GPIO.output(self.pin, on_state)
                self.is_powered = True
                
                if self.warmup_delay > 0:
                    log.info("⏳ Chờ %.1f giây để máy ảnh khởi động & nhận USB...", self.warmup_delay)
                    time.sleep(self.warmup_delay)
                return True
            else:
                log.debug("🔌 Nguồn máy ảnh hiện đã đang BẬT.")
                return False

    def power_off(self):
        """Tắt nguồn máy ảnh để tiết kiệm điện trên CM4."""
        with self._lock:
            if self.is_powered:
                log.info("🔌 [POWER OFF] Đang TẮT NGUỒN máy ảnh qua GPIO %d...", self.pin)
                if self.has_hardware_gpio:
                    off_state = GPIO.LOW if self.active_high else GPIO.HIGH
                    GPIO.output(self.pin, off_state)
                self.is_powered = False
                return True
            return False

    def cleanup(self):
        if self.has_hardware_gpio:
            try:
                self.power_off()
                GPIO.cleanup()
                log.info("🧹 Giải phóng tài nguyên GPIO hoàn tất.")
            except Exception as e:
                log.warning("Lỗi cleanup GPIO: %s", e)


# ── SPECS CÁC THÔNG SÓ MÁY ẢNH HỖ TRỢ ─────────────────────────────────────────

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
    "operator": "CM4 4G/WiFi Gateway",
    "number": "+84987654321",
    "iccid": "8984047123456789012",
}


# ── HYBRID CAMERA BACKEND (gphoto2 USB + Fallback PIL) ───────────────────────

class HybridCameraBackend:
    """Quản lý kết nối máy ảnh thật qua USB gphoto2 kết hợp Fallback Giả lập PIL."""

    def __init__(self, power_manager: CameraPowerManager):
        self._lock = threading.Lock()
        self._camera = None
        self.use_real_hardware = False
        self.power_manager = power_manager

        # Trạng thái thông số giả lập local
        self._sim_applied = {
            "iso": "100", "aperture": "f/4", "shutter_speed": "1/200",
            "exposure_compensation": "0.0", "white_balance": "Auto",
            "image_format": "JPEG Fine", "image_size": "6000x4000",
            "focus_mode": "AF-S", "autofocus": "On", "capture_mode": "Single Shot",
            "capture_target": "Memory Card", "high_iso_nr": "Off",
            "long_exp_nr": "Off", "liveview_af": "Normal Area",
            "exposure_mode": "Manual", "focus_switch": "AF",
        }

    def _try_init_real_camera(self):
        """Kết nối máy ảnh thật qua USB gphoto2."""
        with self._lock:
            if self._camera is not None:
                return True

            if not GPHOTO2_AVAILABLE:
                self.use_real_hardware = False
                return False

            try:
                cam = gp.Camera()
                cam.init()
                self._camera = cam
                self.use_real_hardware = True

                # Đảm bảo thiết lập định dạng ảnh chất lượng cao nếu hỗ trợ
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
                first_line = str(summary).split('\n')[0] if summary else "gphoto2 Device"
                log.info("📷 [USB] Kết nối MÁY ẢNH THẬT thành công! (%s)", first_line)
                return True
            except Exception as e:
                self._camera = None
                self.use_real_hardware = False
                log.info("ℹ️ Chưa nhận máy ảnh USB gphoto2 (%s) — Tự động dùng Chế độ Giả Lập (PIL).", e)
                return False

    def disconnect_real_camera(self):
        with self._lock:
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
                    log.warning("Lỗi đọc cấu hình máy ảnh thật (%s) — Tái kết nối...", e)
                    self.disconnect_real_camera()

        # Fallback Simulated Settings
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
                    log.warning("Không thể ghi cấu hình lên máy ảnh thật: %s", e)

        # Cập nhật trạng thái giả lập local
        settable = {f for f, (_, ok) in _SETTING_SPECS.items() if ok}
        for field, val in requested.items():
            if field in settable:
                self._sim_applied[field] = str(val)

        applied, capabilities = self.get_settings()
        mismatches = {k: {"requested": v, "applied": applied.get(k)} for k, v in requested.items() if applied.get(k) != str(v)}
        return applied, capabilities, mismatches

    def capture(self, camera_code="CAM-CM4"):
        """Chụp ảnh từ máy ảnh thật (USB gphoto2) hoặc sinh ảnh giả lập PIL."""
        if GPHOTO2_AVAILABLE and not self.use_real_hardware:
            self._try_init_real_camera()

        if self.use_real_hardware:
            with self._lock:
                try:
                    log.info("📸 [REAL CAMERA] Phát lệnh màn trập chụp ảnh...")
                    
                    # Tắt live view nếu đang mở để lấy nét autofocus chính xác
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

                    # Chờ hoàn thành ghi file trên thẻ nhớ máy ảnh
                    deadline = time.monotonic() + 5
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
                        log.info("✅ [REAL CAMERA] Chụp ảnh thật thành công (%d file, %d bytes)", len(files), len(files[0][1]))
                        return files
                except Exception as e:
                    log.error("Lỗi chụp trên máy ảnh thật: %s — Chuyển sang Giả lập...", e)
                    self.disconnect_real_camera()

        # Fallback Simulated PIL Image
        log.info("📸 [SIMULATED CAMERA] Đang tạo khung hình giả lập JPEG bằng PIL...")
        time.sleep(0.5)
        img_bytes = self._generate_simulated_image(camera_code=camera_code)
        filename = f"CM4_CAM_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        return [(filename, img_bytes, None)]

    def preview(self):
        """Lấy khung hình xem trực tiếp (Live View)."""
        if GPHOTO2_AVAILABLE and not self.use_real_hardware:
            self._try_init_real_camera()

        if self.use_real_hardware:
            with self._lock:
                try:
                    camera_file = self._camera.capture_preview()
                    return bytes(camera_file.get_data_and_size())
                except Exception:
                    pass
        # Fallback simulated frame
        return self._generate_simulated_image(width=640, height=424, title="CM4 Live View Stream")

    def _generate_simulated_image(self, width=1920, height=1080, title="AutoTimelapse CM4 Camera", camera_code="CAM-CM4"):
        img = Image.new("RGB", (width, height), color=(20, 24, 33))
        draw = ImageDraw.Draw(img)

        # Visual gradient background
        for y in range(0, height, 4):
            r = int(20 + (y / height) * 35)
            g = int(24 + (y / height) * 45)
            b = int(33 + (y / height) * 65)
            draw.rectangle([(0, y), (width, y + 4)], fill=(r, g, b))

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        draw.rectangle([40, 40, width - 40, height - 40], outline=(0, 210, 255), width=3)
        draw.rectangle([60, 60, width - 60, 140], fill=(10, 15, 25))

        hw_type = "REAL HARDWARE (USB)" if self.use_real_hardware else "SIMULATED (PIL)"
        pwr_type = f"GPIO {self.power_manager.pin} {'ON' if self.power_manager.is_powered else 'OFF'}"
        draw.text((80, 75), f"📷 {title} - {camera_code} [{hw_type}]", fill=(0, 230, 255))
        draw.text((80, 105), f"🕒 Timestamp: {now_str} UTC | Power: {pwr_type}", fill=(200, 220, 240))

        # Construction scene graphics
        draw.rectangle([100, 200, 400, height - 100], fill=(45, 55, 72), outline=(100, 116, 139), width=2)
        draw.rectangle([450, 300, 800, height - 100], fill=(30, 41, 59), outline=(100, 116, 139), width=2)
        draw.polygon([(450, 300), (625, 180), (800, 300)], fill=(71, 85, 105))

        iso = self._sim_applied.get("iso", "100")
        aperture = self._sim_applied.get("aperture", "f/4")
        shutter = self._sim_applied.get("shutter_speed", "1/200")
        wb = self._sim_applied.get("white_balance", "Auto")
        info_text = f"ISO: {iso} | Aperture: {aperture} | Shutter: {shutter} | WB: {wb}"
        draw.text((80, height - 80), f"⚙️ {info_text}", fill=(160, 255, 160))

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return buf.getvalue()


# ── MAIN CAMERA AGENT CLASS ──────────────────────────────────────────────────

class CameraAgent:
    """Quản lý luồng hoạt động chính của Camera Agent trên CM4."""

    def __init__(self, code, password, broker, port, server_base,
                 power_pin=16, power_active_high=True, warmup_delay=3.0,
                 always_keep_power=False, telemetry_interval=30,
                 offline_dir="/app/offline_queue", offline_retry_interval=60):
        self.code = code
        self.password = password
        self.broker = broker
        self.port = port
        self.server_base = server_base.rstrip("/")
        self.always_keep_power = always_keep_power
        self.telemetry_interval = telemetry_interval
        self.offline_retry_interval = offline_retry_interval

        # Khởi tạo Power Manager (GPIO 16)
        self.power_manager = CameraPowerManager(
            pin=power_pin,
            active_high=power_active_high,
            warmup_delay=warmup_delay
        )

        # Quản lý Offline Queue
        self.offline_queue = OfflineQueueManager(queue_dir=offline_dir)

        # Backend máy ảnh
        self.backend = HybridCameraBackend(self.power_manager)

        # Quản lý trạng thái luồng
        self.running = False
        self.capture_interval_sec = 0
        self.live_session_id = None
        self.live_fps = 1
        self.live_seq = 0
        self.cmd_queue = _queue.SimpleQueue()
        self.mqtt_client = None

        # MQTT Topics
        self.t_cmd = f"camera/{self.code}/cmd"
        self.t_ack = f"camera/{self.code}/ack"
        self.t_data = f"camera/{self.code}/data"
        self.t_status = f"camera/{self.code}/status"

    def _http_post_json(self, path, obj):
        body = json.dumps(obj).encode()
        req = urllib.request.Request(
            self.server_base + path, data=body, method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Device-Key": self.code,
                "X-Device-Secret": self.password,
            },
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read().decode() or "{}")

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

    def _do_upload_to_server(self, final_bytes, thumb_bytes, metadata):
        """Thực hiện trực tiếp các bước Upload S3 Presigned URL & Complete API."""
        try:
            content_type = metadata.get("content_type", "image/jpeg")
            taken_at = metadata.get("taken_at") or datetime.now(timezone.utc).isoformat()
            
            # 1. Xin Presigned URL
            st, pre = self._http_post_json("/api/device/upload/presign/", {
                "content_type": content_type,
                "taken_at": taken_at,
                "with_thumb": thumb_bytes is not None,
            })
            if st != 200:
                log.error("Lỗi xin Presigned URL từ server: status=%s resp=%s", st, pre)
                return False, None

            # 2. Upload file ảnh chính & thumbnail lên S3 / SeaweedFS
            self._http_put(pre["url"], final_bytes, content_type)
            if thumb_bytes is not None and "thumb_url" in pre:
                self._http_put(pre["thumb_url"], thumb_bytes, "image/jpeg")

            # 3. Hoàn tất đăng ký dữ liệu ảnh
            st, done = self._http_post_json("/api/device/upload/complete/", {
                "media_id": pre["media_id"],
                "key": pre["key"],
                "thumb_key": pre.get("thumb_key"),
                "taken_at": taken_at,
                "width": metadata.get("width", 1920),
                "height": metadata.get("height", 1080),
                "content_type": content_type,
                "source_name": metadata.get("source_name", "CM4_CAM.jpg"),
                "size_bytes": len(final_bytes),
            })

            if st == 200 and done.get("ok"):
                return True, done["media_id"]
            else:
                log.error("Lỗi Complete Upload từ server: status=%s resp=%s", st, done)
                return False, None
        except Exception as exc:
            log.warning("Upload lên Server thất bại: %s", exc)
            return False, None

    def upload_capture(self):
        """Thực hiện chu trình chụp ảnh: GPIO 16 ON -> Chụp -> Upload (hoặc Offline Queue) -> Power Management."""
        # 1. Bật nguồn máy ảnh
        self.power_manager.power_on()

        taken_at = datetime.now(timezone.utc).isoformat()
        captured_files = self.backend.capture(camera_code=self.code)
        media_ids = []

        for filename, image_bytes, thumb in captured_files:
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
                    log.warning("Lỗi sinh thumbnail: %s", e)

            metadata = {
                "content_type": "image/jpeg",
                "taken_at": taken_at,
                "source_name": filename,
                "width": width,
                "height": height,
                "camera_code": self.code,
            }

            # Thử Upload trực tiếp
            ok, media_id = self._do_upload_to_server(final_bytes, thumb, metadata)
            if ok and media_id:
                log.info("🎉 Upload THÀNH CÔNG! media_id=%s file=%s (%d bytes, %dx%d)",
                         media_id, filename, len(final_bytes), width, height)
                media_ids.append(media_id)
            else:
                # Nếu upload thất bại (mất mạng/server down) -> Lưu vào Offline Queue Buffer
                self.offline_queue.save_pending_capture(final_bytes, thumb, metadata)

        # 2. Tắt nguồn máy ảnh nếu không chạy LiveView và không giữ nguồn cố định
        if not self.live_session_id and not self.always_keep_power:
            if self.capture_interval_sec == 0 or self.capture_interval_sec > 15:
                self.power_manager.power_off()

        return media_ids

    def _normalize_image_bytes(self, raw_bytes, preview_bytes=None):
        """Đảm bảo byte ảnh trả về luôn là JPEG hợp lệ cho trình duyệt."""
        if preview_bytes:
            try:
                with Image.open(io.BytesIO(preview_bytes)) as prv_im:
                    pw, ph = prv_im.size
                    if prv_im.format == "JPEG" and pw >= 600 and ph >= 400:
                        return preview_bytes, pw, ph
            except Exception:
                pass

        try:
            with Image.open(io.BytesIO(raw_bytes)) as im:
                w, h = im.size
                if im.format == "JPEG" and w >= 600 and h >= 400:
                    return raw_bytes, w, h

                buf = io.BytesIO()
                rgb = im.convert("RGB")
                rgb.save(buf, format="JPEG", quality=90)
                res = buf.getvalue()
                return res, rgb.size[0], rgb.size[1]
        except Exception as e:
            log.warning("Không thể decode định dạng ảnh (%s), giữ nguyên raw byte", e)
            return raw_bytes, 1920, 1080

    def publish_telemetry(self):
        """Gửi thông tin trạng thái telemetry lên MQTT Server."""
        payload = {
            "node": "cm4",
            "cm4_power_state": "running",
            "camera_gpio_power": "ON" if self.power_manager.is_powered else "OFF",
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
            "firmware_version": "cm4-autotimelapse-v1.0",
        }
        if self.mqtt_client and self.mqtt_client.is_connected():
            self.mqtt_client.publish(self.t_data, json.dumps(payload), qos=1)
            log.info("📡 Telemetry [CM4]: Pin %s%%, %.1f°C, CamPower: %s, Mode: %s",
                     payload["battery_percent"], payload["temperature_c"],
                     payload["camera_gpio_power"],
                     "GPHOTO2_USB" if self.backend.use_real_hardware else "SIMULATED_PIL")

    def process_command(self, req):
        """Xử lý lệnh từ Server qua MQTT."""
        cmd = req.get("command", "")
        rid = req.get("request_id", "")
        payload = req.get("payload") or {}
        log.info("📥 Nhận lệnh từ Server: %s (req_id=%s)", cmd, rid)

        try:
            if cmd in ("power_on_cm4", "power_on"):
                self.power_manager.power_on()
                resp = {"type": cmd, "request_id": rid, "status": "ok", "data": {"cm4_power_state": "running", "camera_power": "on"}}

            elif cmd in ("power_off_camera", "power_off"):
                self.power_manager.power_off()
                resp = {"type": cmd, "request_id": rid, "status": "ok", "data": {"camera_power": "off"}}

            elif cmd == "set_settings":
                if not self.power_manager.is_powered:
                    self.power_manager.power_on()
                applied, capabilities, mismatches = self.backend.set_settings(payload)
                resp = {"type": cmd, "request_id": rid, "status": "ok",
                        "data": {"requested": payload, "applied": applied, "capabilities": capabilities, "mismatches": mismatches}}

            elif cmd in ("get_settings", "get_capabilities", "get_status"):
                applied, capabilities = self.backend.get_settings()
                resp = {"type": cmd, "request_id": rid, "status": "ok",
                        "data": {"online": True, "applied": applied, "capabilities": capabilities,
                                 "live_view": bool(self.live_session_id),
                                 "camera_power": "on" if self.power_manager.is_powered else "off"}}

            elif cmd == "get_sim_info":
                resp = {"type": "get_sim_info", "request_id": rid, "status": "ok",
                        "data": {"sim": {**_SIM_INFO_TELEMETRY, "signal_dbm": -65}}}

            elif cmd in ("capture_now", "capture"):
                media_ids = self.upload_capture()
                if media_ids:
                    resp = {"type": cmd, "request_id": rid, "status": "ok", "data": {"media_id": media_ids[0], "media_ids": media_ids}}
                else:
                    resp = {"type": cmd, "request_id": rid, "status": "ok", "data": {"note": "Đã lưu ảnh vào Offline Queue (Mất mạng/Server error)"}}

            elif cmd == "set_interval":
                val = max(0, int(payload.get("capture_interval_sec", self.capture_interval_sec)))
                self.capture_interval_sec = val
                log.info("⏱ Cập nhật chu kỳ chụp tự động: %d giây", val)
                resp = {"type": "set_interval", "request_id": rid, "status": "ok", "data": {"capture_interval_sec": val}}

            elif cmd == "start_live_view":
                self.power_manager.power_on()
                self.live_session_id = payload.get("session_id") or "lv-cm4"
                self.live_fps = max(1, min(2, int(payload.get("fps") or 1)))
                self.live_seq = 0
                resp = {"type": "start_live_view", "request_id": rid, "status": "ok",
                        "data": {"live_view": True, "session_id": self.live_session_id, "fps": self.live_fps}}

            elif cmd == "stop_live_view":
                self.live_session_id = None
                if not self.always_keep_power and self.capture_interval_sec == 0:
                    self.power_manager.power_off()
                resp = {"type": "stop_live_view", "request_id": rid, "status": "ok", "data": {"live_view": False}}

            else:
                resp = {"type": cmd, "request_id": rid, "status": "error", "data": {"note": f"Lệnh chưa hỗ trợ: {cmd}"}}

        except Exception as exc:
            log.exception("Xử lý lệnh %s lỗi: %s", cmd, exc)
            resp = {"type": cmd, "request_id": rid, "status": "error", "data": {"note": str(exc)}}

        if self.mqtt_client and self.mqtt_client.is_connected():
            self.mqtt_client.publish(self.t_ack, json.dumps(resp), qos=1)

    # ── THREAD CONTROL LOOPS ─────────────────────────────────────────────────

    def live_view_thread(self):
        """Luồng phát Live View Frame về Server."""
        while self.running:
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
        """Luồng điều khiển chu kỳ chụp tự động (Interval Capture Loop)."""
        log.info("🔄 Capture Loop thread started.")
        while self.running:
            wait = self.capture_interval_sec
            if wait <= 0:
                time.sleep(1)
                continue

            log.info("⏱ Chu kỳ chụp kế tiếp sau %d giây", wait)
            elapsed = 0
            while elapsed < wait and self.running:
                time.sleep(1)
                elapsed += 1
                if self.capture_interval_sec != wait:
                    break

            if self.running and self.capture_interval_sec == wait:
                try:
                    log.info("🔔 Kích hoạt chu kỳ chụp tự động...")
                    self.upload_capture()
                except Exception:
                    log.exception("Lỗi trong chu kỳ chụp tự động")

    def offline_retry_thread(self):
        """Luồng tự động duyệt và gửi lại ảnh lưu tạm khi có kết nối mạng."""
        log.info("🔄 Offline Retry Thread started (Chu kỳ: %ds).", self.offline_retry_interval)
        while self.running:
            time.sleep(self.offline_retry_interval)
            if self.running:
                try:
                    self.offline_queue.process_pending_queue(self._do_upload_to_server)
                except Exception as e:
                    log.error("Lỗi trong luồng retry offline queue: %s", e)

    def cmd_worker_thread(self):
        """Luồng xử lý hàng đợi lệnh MQTT."""
        while self.running:
            try:
                raw = self.cmd_queue.get(timeout=1)
                self.process_command(raw)
            except _queue.Empty:
                continue
            except Exception as exc:
                log.error("cmd_worker error: %s", exc)

    def start(self):
        """Khởi động toàn bộ Agent & các luồng dịch vụ."""
        self.running = True
        log.info("==========================================================")
        log.info("🚀 KHỞI ĐỘNG AUTOTIMELAPSE CM4 CAMERA AGENT")
        log.info("📷 Code Camera: %s", self.code)
        log.info("📡 MQTT Broker: %s:%d", self.broker, self.port)
        log.info("🌐 Server Base : %s", self.server_base)
        log.info("⚡ GPIO Power  : Pin %d (Active %s, Warmup: %.1fs)",
                 self.power_manager.pin,
                 "HIGH" if self.power_manager.active_high else "LOW",
                 self.power_manager.warmup_delay)
        log.info("📁 Offline Dir : %s (Retry Interval: %ds)",
                 self.offline_queue.queue_dir, self.offline_retry_interval)
        log.info("==========================================================")

        # Khởi chạy các Worker Threads
        threading.Thread(target=self.live_view_thread, daemon=True, name="liveview").start()
        threading.Thread(target=self.capture_loop_thread, daemon=True, name="capture_loop").start()
        threading.Thread(target=self.offline_retry_thread, daemon=True, name="offline_retry").start()
        threading.Thread(target=self.cmd_worker_thread, daemon=True, name="cmd_worker").start()

        # Callbacks MQTT
        def on_connect(client, userdata, flags, rc, props=None):
            if rc == 0:
                log.info("✅ Kết nối MQTT Broker thành công!")
                client.subscribe(self.t_cmd, qos=1)
                client.publish(self.t_status, json.dumps({"online": True}), qos=1, retain=True)
                self.publish_telemetry()
                # Kích hoạt thử gửi lại ảnh offline ngay khi kết nối lại MQTT
                threading.Thread(target=self.offline_queue.process_pending_queue,
                                 args=(self._do_upload_to_server,),
                                 daemon=True).start()
            else:
                log.error("❌ Kết nối MQTT thất bại với mã return code: %s", rc)

        def on_message(client, userdata, msg):
            try:
                raw = json.loads(msg.payload.decode())
                self.cmd_queue.put(raw)
            except Exception as exc:
                log.error("Lỗi giải mã thông điệp MQTT: %s", exc)

        # Tạo MQTT Client (hỗ trợ Paho MQTT v2 API)
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=self.code)
        client.username_pw_set(self.code, self.password)
        client.will_set(self.t_status, json.dumps({"online": False}), qos=1, retain=True)
        client.on_connect = on_connect
        client.on_message = on_message
        self.mqtt_client = client

        try:
            client.connect(self.broker, self.port, keepalive=60)
        except Exception as e:
            log.error("❌ Không thể kết nối MQTT Broker tại %s:%d (%s). Agent vẫn hoạt động ở chế độ Offline Queue.", self.broker, self.port, e)

        if self.mqtt_client:
            try:
                client.loop_start()
            except Exception:
                pass

        # Vòng lặp chính phát Telemetry
        last_telemetry = time.time()
        try:
            while self.running:
                time.sleep(1)
                if time.time() - last_telemetry >= self.telemetry_interval:
                    self.publish_telemetry()
                    last_telemetry = time.time()
        except KeyboardInterrupt:
            log.info("\n⏹ Đã nhận tín hiệu dừng (KeyboardInterrupt)...")
        finally:
            self.stop()

    def stop(self):
        """Dừng Agent và dọn dẹp tài nguyên."""
        if not self.running:
            return
        log.info("🛑 Đang dừng Agent & dọn dẹp tài nguyên...")
        self.running = False

        if self.mqtt_client:
            try:
                self.mqtt_client.publish(self.t_status, json.dumps({"online": False}), qos=1, retain=True)
                self.mqtt_client.loop_stop()
                self.mqtt_client.disconnect()
            except Exception:
                pass

        self.power_manager.cleanup()
        log.info("👋 Agent đã dừng hoàn toàn.")


# ── MAIN ENTRY POINT ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AutoTimelapse CM4 Camera Agent")
    parser.add_argument("--code", default=CAMERA_CODE, help=f"Mã định danh Camera [Mặc định: {CAMERA_CODE}]")
    parser.add_argument("--secret", default=MQTT_PASSWORD, help="Mật khẩu thiết bị / MQTT Password")
    parser.add_argument("--broker", default=MQTT_BROKER, help=f"MQTT Broker host [Mặc định: {MQTT_BROKER}]")
    parser.add_argument("--port", type=int, default=MQTT_PORT, help=f"MQTT Broker port [Mặc định: {MQTT_PORT}]")
    parser.add_argument("--server", default=SERVER_BASE, help=f"Server Base URL [Mặc định: {SERVER_BASE}]")
    parser.add_argument("--power-gpio", type=int, default=POWER_GPIO_PIN, help=f"GPIO Pin điều khiển nguồn [Mặc định: {POWER_GPIO_PIN}]")
    parser.add_argument("--warmup", type=float, default=WARMUP_DELAY_SEC, help=f"Thời gian chờ máy ảnh khởi động (s) [Mặc định: {WARMUP_DELAY_SEC}]")
    parser.add_argument("--offline-dir", default=OFFLINE_QUEUE_DIR, help=f"Thư mục lưu đệm offline [Mặc định: {OFFLINE_QUEUE_DIR}]")

    args = parser.parse_args()

    agent = CameraAgent(
        code=args.code,
        password=args.secret,
        broker=args.broker,
        port=args.port,
        server_base=args.server,
        power_pin=args.power_gpio,
        power_active_high=POWER_ACTIVE_HIGH,
        warmup_delay=args.warmup,
        always_keep_power=ALWAYS_KEEP_POWER,
        telemetry_interval=TELEMETRY_INTERVAL,
        offline_dir=args.offline_dir,
        offline_retry_interval=OFFLINE_RETRY_INTERVAL,
    )

    # Đăng ký Signal handler cho Ctrl+C và Docker SIGTERM
    def _sig_handler(sig, frame):
        agent.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _sig_handler)
    signal.signal(signal.SIGTERM, _sig_handler)

    agent.start()
