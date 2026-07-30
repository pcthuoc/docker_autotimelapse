"""Nikon D5300 MQTT client with simulated environment telemetry.

Run: python3 sim.py
Requires: python3-gphoto2, paho-mqtt, pillow
"""

import io
import json
import logging
import random
import threading
import queue as _queue
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone

import gphoto2 as gp
import paho.mqtt.client as mqtt
from PIL import Image

# ── Thông số kết nối MQTT & Server ──────────────────────────────────────────
CAMERA_CODE     = "CAM1"
MQTT_PASSWORD   = "O3w5ZD0tXkRcORC4o2cnrg"
MQTT_BROKER     = "localhost"
MQTT_PORT       = 1883

SERVER_BASE     = "http://localhost"
# Xác thực HTTP API dùng CAMERA_CODE và MQTT_PASSWORD
DEVICE_KEY      = CAMERA_CODE
DEVICE_SECRET   = MQTT_PASSWORD

TELEMETRY_SEC   = 60    # chu kỳ gửi telemetry (giây)
CAPTURE_SEC     = 0     # chu kỳ tự động chụp + upload (giây); 0 = tắt
LIVE_FPS_MAX    = 2     # tốc độ frame live view tối đa
# ────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
)
log = logging.getLogger("sim")

# Mapping field_name (server) → gphoto2 widget name.
# Giá trị lưu trong DB và truyền qua MQTT là chuỗi native gphoto2 (không alias).
# Chi tiết: HW/NIKON_D5300_SETTINGS.md
_SETTING_SPECS = {
    # field_name:           (gphoto2_widget,      settable)
    "iso":                  ("iso",                True),
    "aperture":             ("f-number",           True),
    "shutter_speed":        ("shutterspeed2",      True),
    "exposure_compensation":("exposurecompensation",True),
    "white_balance":        ("whitebalance",       True),
    "image_format":         ("imagequality",       True),
    "image_size":           ("imagesize",          True),
    "focus_mode":           ("focusmode2",         True),
    "autofocus":            ("autofocus",          True),
    "capture_mode":         ("capturemode",        True),
    "capture_target":       ("capturetarget",      True),
    "high_iso_nr":          ("highisonr",          True),
    "long_exp_nr":          ("longexpnr",          True),
    "liveview_af":          ("liveviewaffocus",    True),
    # Read-only (physical controls) — chỉ đọc, không set
    "exposure_mode":        ("expprogram",         False),
    "focus_switch":         ("focusmode",          False),
}

_SIM_INFO = {
    "operator": "Viettel",
    "number": "+84987654321",
    "iccid": "8984047123456789012",
}

_state = {"capture_interval_sec": CAPTURE_SEC, "upload_nef": False}
_live  = {"session_id": None, "fps": 1, "seq": 0}
_cmd_queue = _queue.SimpleQueue()  # MQTT command queue — on_message đẩy vào, _cmd_worker đọc ra

T_CMD    = f"camera/{CAMERA_CODE}/cmd"
T_ACK    = f"camera/{CAMERA_CODE}/ack"
T_DATA   = f"camera/{CAMERA_CODE}/data"
T_STATUS = f"camera/{CAMERA_CODE}/status"


# ── Nikon camera backend ────────────────────────────────────────────────────

class CameraOfflineError(RuntimeError):
    pass


class NikonCamera:
    def __init__(self):
        self._camera = None
        self._lock = threading.Lock()

    def close(self):
        with self._lock:
            self._disconnect()

    def _disconnect(self):
        if self._camera is not None:
            try:
                self._camera.exit()
            except gp.GPhoto2Error:
                pass
            self._camera = None

    def _connect(self):
        if self._camera is None:
            camera = gp.Camera()
            try:
                camera.init()
            except gp.GPhoto2Error as exc:
                raise CameraOfflineError("Nikon D5300 is not connected") from exc
            self._camera = camera
            log.info("Đã kết nối Nikon qua python-gphoto2")
        return self._camera

    def _run(self, operation):
        with self._lock:
            try:
                return operation(self._connect())
            except gp.GPhoto2Error:
                # Lần 1 lỗi → disconnect + thử kết nối lại 1 lần
                log.warning("gphoto2 lỗi — tự reconnect...")
                self._disconnect()
                try:
                    return operation(self._connect())
                except gp.GPhoto2Error as exc:
                    self._disconnect()
                    raise CameraOfflineError("Nikon D5300 is not connected") from exc

    @staticmethod
    def _widget(config, name):
        return config.get_child_by_name(name)

    @staticmethod
    def _api_value(field, camera_value):
        # Native values — không cần mapping, trả thẳng chuỗi gphoto2
        return str(camera_value)

    def get_settings(self):
        def operation(camera):
            config = camera.get_config()
            applied = {}
            capabilities = {}
            for field, (widget_name, _settable) in _SETTING_SPECS.items():
                try:
                    widget = self._widget(config, widget_name)
                    val = str(widget.get_value())
                    applied[field] = val
                    wtype = widget.get_type()
                    choices = [str(widget.get_choice(i)) for i in range(widget.count_choices())] if wtype in (5, 6) else []
                    capabilities[field] = {
                        "writable": _settable and not bool(widget.get_readonly()),
                        "current": val,
                        "choices": choices,
                    }
                except gp.GPhoto2Error:
                    log.debug("Camera không cung cấp widget %s", widget_name)
            return applied, capabilities

        return self._run(operation)

    def get_status(self):
        def operation(camera):
            config = camera.get_config()
            status = {"online": True, "model": "Nikon D5300"}
            try:
                battery = self._widget(config, "batterylevel").get_value()
                status["battery_percent"] = int(str(battery).rstrip("%"))
            except (gp.GPhoto2Error, ValueError):
                status["battery_percent"] = None
            return status

        status = self._run(operation)
        applied, capabilities = self.get_settings()
        status.update({"applied": applied, "capabilities": capabilities})
        return status

    def set_settings(self, requested):
        # Chỉ cho phép settable fields
        settable = {f for f, (_, ok) in _SETTING_SPECS.items() if ok}
        unsupported = sorted(set(requested) - set(_SETTING_SPECS))
        if unsupported:
            raise ValueError(f"Unsupported settings: {', '.join(unsupported)}")

        def operation(camera):
            import gphoto2 as gp_inner
            config = camera.get_config()
            for field, value in requested.items():
                if field not in settable:
                    log.warning("Bỏ qua field read-only: %s", field)
                    continue
                widget_name = _SETTING_SPECS[field][0]
                widget = self._widget(config, widget_name)
                if widget.get_readonly():
                    log.warning("Widget %s read-only trên máy — bỏ qua", widget_name)
                    continue
                wtype = widget.get_type()
                # Native values: tất cả là chuỗi gphoto2
                if wtype == gp_inner.GP_WIDGET_RANGE:
                    widget.set_value(float(str(value)))
                elif wtype == gp_inner.GP_WIDGET_TOGGLE:
                    widget.set_value(1 if str(value).lower() in ("on","true","1") else 0)
                else:  # RADIO, TEXT, MENU
                    widget.set_value(str(value))
            camera.set_config(config)
            # Drain events để config cache của camera được refresh,
            # tránh get_config() sau đó đọc lại giá trị cũ (stale)
            deadline = time.monotonic() + 2.5
            while time.monotonic() < deadline:
                event_type, _ = camera.wait_for_event(200)
                if event_type == gp_inner.GP_EVENT_TIMEOUT:
                    break

        self._run(operation)
        try:
            applied, capabilities = self.get_settings()
        except (CameraOfflineError, gp.GPhoto2Error):
            log.warning("Đọc lại settings sau khi set thất bại — dùng desired làm fallback")
            # Settings đã được set nhưng không đọc lại được; dùng desired làm applied
            applied, capabilities = dict(requested), {}
        mismatches = {
            field: {"requested": value, "applied": applied.get(field)}
            for field, value in requested.items()
            if applied.get(field) != value
        }
        return applied, capabilities, mismatches

    def preview(self):
        def operation(camera):
            camera_file = camera.capture_preview()
            return bytes(camera_file.get_data_and_size())

        return self._run(operation)

    def capture(self):
        def operation(camera):
            config = camera.get_config()

            # 1. Thoát Live View (nếu đang bật) để camera dùng phase-detect AF
            try:
                vf = config.get_child_by_name("viewfinder")
                if int(vf.get_value()) != 0:
                    vf.set_value(0)
                    camera.set_config(config)
                    time.sleep(0.4)   # chờ mirror hạ xuống
                    config = camera.get_config()
            except gp.GPhoto2Error:
                pass

            # 2. Trigger phase-detect AF và chờ lock
            try:
                af = config.get_child_by_name("autofocusdrive")
                af.set_value(1)
                camera.set_config(config)
                time.sleep(0.8)   # chờ AF hoàn thành
            except gp.GPhoto2Error:
                pass

            first_path = camera.capture(gp.GP_CAPTURE_IMAGE)
            paths = {(first_path.folder, first_path.name): first_path}
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                event_type, event_data = camera.wait_for_event(500)
                if event_type == gp.GP_EVENT_FILE_ADDED:
                    paths[(event_data.folder, event_data.name)] = event_data
                elif event_type == gp.GP_EVENT_CAPTURE_COMPLETE:
                    break

            files = []
            for path in paths.values():
                camera_file = camera.file_get(
                    path.folder, path.name, gp.GP_FILE_TYPE_NORMAL)
                data = bytes(camera_file.get_data_and_size())
                preview = None
                try:
                    preview_file = camera.file_get(
                        path.folder, path.name, gp.GP_FILE_TYPE_PREVIEW)
                    preview = bytes(preview_file.get_data_and_size())
                except gp.GPhoto2Error:
                    log.warning("Không lấy được thumbnail nhúng từ %s", path.name)
                try:
                    camera.file_delete(path.folder, path.name)
                except gp.GPhoto2Error:
                    log.warning("Không xóa được %s trên camera", path.name)
                files.append((path.name, data, preview))
            return files

        return self._run(operation)


camera_backend = NikonCamera()


def _http_post_json(path, obj):
    body = json.dumps(obj).encode()
    req = urllib.request.Request(
        SERVER_BASE + path, data=body, method="POST",
        headers={"Content-Type": "application/json",
                 "X-Device-Key": DEVICE_KEY, "X-Device-Secret": DEVICE_SECRET},
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.status, json.loads(r.read().decode() or "{}")


def _http_post_frame(session_id, seq, frame_bytes):
    req = urllib.request.Request(
        SERVER_BASE + "/api/device/live/frame/",
        data=frame_bytes, method="POST",
        headers={"Content-Type": "image/jpeg",
                 "X-Device-Key": DEVICE_KEY, "X-Device-Secret": DEVICE_SECRET,
                 "X-Live-Session": session_id, "X-Frame-Seq": str(seq)},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.status, json.loads(r.read().decode() or "{}")


def _http_put(url, data, content_type):
    req = urllib.request.Request(url, data=data, method="PUT",
                                 headers={"Content-Type": content_type})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status


# ── Capture Nikon và upload ──────────────────────────────────────────────────

def capture_and_upload():
    taken_at = datetime.now(timezone.utc).isoformat()
    live_session = _live["session_id"]
    if live_session:
        _live["session_id"] = None
        log.info("Tạm dừng Live View để capture")
        time.sleep(0.5)   # chờ frame live cuối kịp flush trước khi camera capture
    try:
        captured_files = camera_backend.capture()
        media_ids = []
        for camera_name, image_bytes, thumb in captured_files:
            media_id = _upload_capture_file(
                taken_at, camera_name, image_bytes, thumb)
            if media_id:
                media_ids.append(media_id)
        return media_ids
    finally:
        if live_session and _live["session_id"] is None:
            _live["session_id"] = live_session
            log.info("Tiếp tục Live View sau capture")


def _upload_capture_file(taken_at, camera_name, image_bytes, thumb):
    suffix = camera_name.rsplit(".", 1)[-1].lower() if "." in camera_name else "jpg"
    if suffix == "nef" and not _state["upload_nef"]:
        log.debug("Bỏ qua NEF %s (upload_nef=False)", camera_name)
        return None
    content_types = {
        "jpg": "image/jpeg", "jpeg": "image/jpeg", "nef": "image/x-nikon-nef",
    }
    content_type = content_types.get(suffix, "application/octet-stream")
    width = height = None
    if content_type == "image/jpeg":
        with Image.open(io.BytesIO(image_bytes)) as image:
            width, height = image.size
            if thumb is None:
                image.thumbnail((480, 320))
                output = io.BytesIO()
                image.save(output, "JPEG", quality=78)
                thumb = output.getvalue()

    st, pre = _http_post_json("/api/device/upload/presign/", {
        "content_type": content_type,
        "taken_at": taken_at,
        "with_thumb": thumb is not None,
    })
    if st != 200:
        log.error("presign lỗi: %s %s", st, pre)
        return None

    _http_put(pre["url"], image_bytes, content_type)
    if thumb is not None:
        _http_put(pre["thumb_url"], thumb, "image/jpeg")

    st, done = _http_post_json("/api/device/upload/complete/", {
        "media_id":    pre["media_id"],
        "key":         pre["key"],
        "thumb_key":   pre.get("thumb_key"),
        "taken_at":    taken_at,
        "width":       width,
        "height":      height,
        "content_type": content_type,
        "source_name": camera_name,
        "size_bytes": len(image_bytes),
    })
    if st == 200 and done.get("ok"):
        log.info("→ upload OK  media=%s file=%s (%d bytes)",
                 done["media_id"], camera_name, len(image_bytes))
        return done["media_id"]
    log.error("complete lỗi: %s %s", st, done)
    return None


# ── Thread: gửi frame live view ─────────────────────────────────────────────

def _live_view_loop():
    while True:
        sid = _live["session_id"]
        if not sid:
            time.sleep(0.5)
            continue
        _live["seq"] += 1
        seq = _live["seq"]
        try:
            frame = camera_backend.preview()
            st, resp = _http_post_frame(sid, seq, frame)
            if st == 200 and resp.get("ok"):
                log.info("→ live frame seq=%d (%d bytes)", seq, len(frame))
        except CameraOfflineError:
            log.warning("Live View chờ camera được kết nối")
        except urllib.error.HTTPError as e:
            if e.code == 409:
                log.info("Live session kết thúc (server báo 409).")
                _live["session_id"] = None
                continue
            log.warning("live frame HTTP %s", e.code)
        except Exception:
            log.exception("live frame lỗi")
        time.sleep(max(0.2, 1.0 / max(1, _live["fps"])))


# ── Thread: chụp theo chu kỳ ────────────────────────────────────────────────

def _capture_loop():
    """Chụp định kỳ theo _state["capture_interval_sec"].

    Server điều khiển qua lệnh set_interval (MQTT). interval <= 0 = tạm dừng.
    """
    while True:
        wait = _state["capture_interval_sec"]
        if wait <= 0:
            time.sleep(2)
            continue
        log.info("Chu kỳ chụp kế tiếp sau %ds", wait)
        for _ in range(wait):
            time.sleep(1)
            if _state["capture_interval_sec"] != wait:
                break  # interval đổi giữa chừng → tính lại
        else:
            try:
                media_ids = capture_and_upload()
                if not media_ids:
                    log.error("capture tự động không upload được file nào")
            except Exception:
                log.exception("capture loop lỗi")


# ── MQTT callbacks ───────────────────────────────────────────────────────────

def on_connect(client, userdata, flags, rc, props=None):
    log.info("Đã kết nối broker (rc=%s) — %s", rc, CAMERA_CODE)
    client.subscribe(T_CMD, qos=1)
    client.publish(T_STATUS, json.dumps({"online": True}), qos=1, retain=True)
    _publish_telemetry(client)


def _publish_telemetry(client):
    payload = {
        "battery_percent":  random.randint(60, 95),
        "battery_voltage":  round(random.uniform(11.5, 12.6), 3),
        "cell_voltages":    [round(random.uniform(3.65, 3.85), 2) for _ in range(3)],
        "is_charging":      random.random() > 0.5,
        "solar_voltage":    round(random.uniform(13.0, 18.5), 2),
        "solar_percent":    random.randint(40, 100),
        "temperature_c":    round(random.uniform(26, 38), 1),
        "humidity_percent": random.randint(55, 90),
        "sim_signal_dbm":   random.randint(-95, -60),
        "firmware_version": "sim-1.0.0",
    }
    client.publish(T_DATA, json.dumps(payload), qos=1)
    log.info("→ telemetry: pin %s%%, %.1f°C", payload["battery_percent"], payload["temperature_c"])


def on_message(client, userdata, msg):
    """Nhận lệnh MQTT → đẩy vào queue để worker thread xử lý.
    KHÔNG block paho network thread — tránh delay nhận lệnh tiếp theo."""
    try:
        raw = json.loads(msg.payload.decode())
        _cmd_queue.put((client, raw))
    except ValueError:
        log.warning("payload không phải JSON")
    except Exception as exc:
        log.error("on_message error: %s", exc)


def _process_message(client, req):
    """Xử lý 1 lệnh MQTT (chạy trong worker thread)."""
    cmd = req.get("command", "")
    rid = req.get("request_id", "")
    payload = req.get("payload") or {}
    log.info("← lệnh %s (%s)", cmd, rid)
    try:
        if cmd == "set_settings":
            applied, capabilities, mismatches = camera_backend.set_settings(payload)
            status = "ok" if not mismatches else "error"
            resp = {"type": cmd, "request_id": rid, "status": status,
                    "data": {"requested": payload, "applied": applied,
                             "capabilities": capabilities, "mismatches": mismatches}}

        elif cmd == "get_status":
            status_data = camera_backend.get_status()
            status_data["live_view"] = bool(_live["session_id"])
            resp = {"type": cmd, "request_id": rid, "status": "ok",
                    "data": status_data}

        elif cmd in ("get_settings", "get_capabilities"):
            applied, capabilities = camera_backend.get_settings()
            resp = {"type": cmd, "request_id": rid, "status": "ok",
                    "data": {"online": True, "applied": applied,
                             "capabilities": capabilities,
                             "live_view": bool(_live["session_id"])}}

        elif cmd == "get_sim_info":
            resp = {"type": "get_sim_info", "request_id": rid, "status": "ok",
                    "data": {"sim": {**_SIM_INFO, "signal_dbm": random.randint(-95, -60)}}}

        elif cmd in ("capture_now", "capture"):
            media_ids = capture_and_upload()
            if media_ids:
                resp = {"type": cmd, "request_id": rid, "status": "ok",
                        "data": {"media_id": media_ids[0], "media_ids": media_ids}}
            else:
                resp = {"type": cmd, "request_id": rid, "status": "error",
                        "data": {"note": "upload thất bại"}}

        elif cmd == "set_interval":
            interval = max(1, int(payload.get(
                "capture_interval_sec", _state["capture_interval_sec"])))
            _state["capture_interval_sec"] = interval
            if "upload_nef" in payload:
                _state["upload_nef"] = bool(payload["upload_nef"])
            resp = {"type": "set_interval", "request_id": rid, "status": "ok",
                    "data": {"capture_interval_sec": interval,
                             "upload_nef": _state["upload_nef"]}}

        elif cmd == "start_live_view":
            camera_backend.get_settings()
            _live["session_id"] = payload.get("session_id") or "lv-unknown"
            _live["fps"] = max(1, min(LIVE_FPS_MAX, int(payload.get("fps") or 1)))
            _live["seq"] = 0
            resp = {"type": "start_live_view", "request_id": rid, "status": "ok",
                    "data": {"live_view": True, "session_id": _live["session_id"],
                             "fps": _live["fps"], "width": 640, "height": 424}}

        elif cmd == "stop_live_view":
            _live["session_id"] = None
            resp = {"type": "stop_live_view", "request_id": rid, "status": "ok",
                    "data": {"live_view": False}}

        else:
            resp = {"type": cmd, "request_id": rid, "status": "error",
                    "data": {"code": "unknown_command", "note": f"lệnh không nhận ra: {cmd}"}}
            log.warning("lệnh không rõ: %s", cmd)
    except CameraOfflineError as exc:
        resp = {"type": cmd, "request_id": rid, "status": "error",
                "data": {"code": "camera_offline", "note": str(exc)}}
    except (ValueError, gp.GPhoto2Error) as exc:
        log.exception("Lệnh camera %s thất bại", cmd)
        resp = {"type": cmd, "request_id": rid, "status": "error",
                "data": {"code": "camera_error", "note": str(exc)}}
    except (OSError, urllib.error.URLError) as exc:
        log.exception("Lệnh %s lỗi mạng hoặc upload", cmd)
        resp = {"type": cmd, "request_id": rid, "status": "error",
                "data": {"code": "upload_failed", "note": str(exc)}}

    except Exception as exc:
        log.exception("Lệnh %s lỗi không mong đợi", cmd)
        resp = {"type": cmd, "request_id": rid, "status": "error",
                "data": {"code": "internal_error", "note": str(exc)}}
    client.publish(T_ACK, json.dumps(resp), qos=1)


def _cmd_worker():
    """Worker thread: xử lý lệnh từ queue lần lượt."""
    while True:
        client, raw = _cmd_queue.get()
        try:
            _process_message(client, raw)
        except Exception as exc:
            log.error("_cmd_worker exception: %s", exc, exc_info=True)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print(f"Nikon client chạy cho camera {CAMERA_CODE} (Ctrl+C để dừng)…")

    def _keepalive_loop():
        """Ping camera nhẹ mỗi 60 giây để giữ gphoto2 session sống."""
        while True:
            time.sleep(60)
            try:
                def _ping(camera):
                    cfg = camera.get_config()
                    return str(cfg.get_child_by_name("batterylevel").get_value())
                batt = camera_backend._run(_ping)
                log.debug("keepalive OK battery=%s", batt)
            except (CameraOfflineError, Exception):
                log.debug("keepalive: camera offline")

    threading.Thread(target=_live_view_loop, daemon=True, name="liveview").start()
    threading.Thread(target=_capture_loop,   daemon=True, name="capture").start()
    threading.Thread(target=_keepalive_loop, daemon=True, name="keepalive").start()
    threading.Thread(target=_cmd_worker,     daemon=True, name="cmd_worker").start()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=CAMERA_CODE)
    client.username_pw_set(CAMERA_CODE, MQTT_PASSWORD)
    client.will_set(T_STATUS, json.dumps({"online": False}), qos=1, retain=True)
    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)

    # telemetry loop chạy trên main thread
    last_telemetry = time.time()
    client.loop_start()
    try:
        while True:
            time.sleep(1)
            if time.time() - last_telemetry >= TELEMETRY_SEC:
                _publish_telemetry(client)
                last_telemetry = time.time()
    except KeyboardInterrupt:
        print("\nDừng simulator.")
    finally:
        client.publish(T_STATUS, json.dumps({"online": False}), qos=1, retain=True)
        client.loop_stop()
        client.disconnect()
        camera_backend.close()


if __name__ == "__main__":
    main()
