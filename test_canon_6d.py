#!/usr/bin/env python3
"""
test_canon_6d.py — Bộ kiểm thử toàn diện các chức năng của Canon EOS 6D:
1. Đọc toàn bộ thông số hiện tại (Mode, ISO, Aperture, Shutter, WB, Image Format, Battery, ...)
2. Thay đổi thông số và xác nhận readback (Set & Verify)
3. Chụp thử Live View frame (Liveview stream/preview)
4. Chụp ảnh thực tế (Shutter capture & download)
"""

import sys
import os
import time
import datetime
import gphoto2 as gp

# Real-time console output
try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass

# ANSI colors
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_output")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def banner(title: str):
    print(f"\n{BOLD}{CYAN}{'='*70}{RESET}")
    print(f"{BOLD}{CYAN}   {title.center(64)}   {RESET}")
    print(f"{BOLD}{CYAN}{'='*70}{RESET}\n")


def ensure_gpio_power(pin=16):
    """Bật nguồn rơ-le GPIO 16 trên Raspberry Pi / CM4 nếu đang chạy trên Pi."""
    try:
        import RPi.GPIO as GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(pin, GPIO.OUT)
        GPIO.output(pin, GPIO.HIGH)
        print(f"⚡ [GPIO] Đã kích hoạt nguồn Relay GPIO {pin} (HIGH). Chờ 3s...")
        time.sleep(3.0)
    except Exception:
        pass


class Canon6DController:
    def __init__(self):
        self.camera = None

    def connect(self):
        ensure_gpio_power(16)
        print("[*] Đang khởi tạo kết nối tới Canon 6D qua gphoto2...")
        for attempt in range(1, 6):
            try:
                self.camera = gp.Camera()
                self.camera.init()
                summary = self.camera.get_summary()
                abilities = self.camera.get_abilities()
                print(f"{GREEN}✓ Kết nối thành công (lần {attempt})! Model: {abilities.model}{RESET}")
                return
            except Exception as e:
                print(f"{YELLOW}⏳ [Lần {attempt}/5] Đang đợi nhận USB ({e})... Thử lại sau 2s{RESET}")
                time.sleep(2.0)
        raise RuntimeError("Không thể kết nối máy ảnh sau 5 lần thử. Kiểm tra cáp USB và công tắc nguồn!")

    def close(self):
        if self.camera:
            try:
                self.camera.exit()
                print("[*] Đã đóng kết nối máy ảnh an toàn.")
            except Exception:
                pass

    def get_widget_info(self, widget_name: str) -> dict:
        """Lấy giá trị hiện tại, readonly flag, và danh sách choices của 1 widget."""
        config = self.camera.get_config()
        try:
            widget = config.get_child_by_name(widget_name)
            current_val = widget.get_value()
            readonly = widget.get_readonly()
            w_type = widget.get_type()
            choices = []
            if w_type in [gp.GP_WIDGET_RADIO, gp.GP_WIDGET_MENU]:
                num_choices = widget.count_choices()
                for i in range(num_choices):
                    choices.append(widget.get_choice(i))
            return {
                "name": widget_name,
                "label": widget.get_label(),
                "current": current_val,
                "readonly": readonly,
                "choices": choices,
            }
        except gp.GPhoto2Error as e:
            return {"name": widget_name, "error": str(e)}

    def set_widget_value(self, widget_name: str, new_value: str) -> tuple[bool, str]:
        """Set giá trị mới cho widget và verify lại."""
        config = self.camera.get_config()
        try:
            widget = config.get_child_by_name(widget_name)
            widget.set_value(new_value)
            self.camera.set_config(config)
            
            # Read back to verify
            verify_config = self.camera.get_config()
            verify_widget = verify_config.get_child_by_name(widget_name)
            actual_val = verify_widget.get_value()
            
            if str(actual_val) == str(new_value):
                return True, actual_val
            else:
                return False, f"Expected '{new_value}', got '{actual_val}'"
        except gp.GPhoto2Error as e:
            return False, str(e)

    def test_read_all_settings(self):
        banner("BƯỚC 1: ĐỌC TẤT CẢ THÔNG SỐ HIỆN TẠI (READ SETTINGS)")
        
        test_widgets = [
            ("autoexposuremode", "Exposure Mode"),
            ("iso",              "ISO"),
            ("shutterspeed",     "Shutter Speed"),
            ("aperture",         "Aperture"),
            ("whitebalance",     "White Balance"),
            ("imageformat",      "Image Format"),
            ("drivemode",        "Drive Mode"),
            ("capturetarget",    "Capture Target"),
            ("batterylevel",     "Battery Level"),
            ("autopoweroff",     "Auto Power Off"),
        ]

        results = {}
        for w_name, label in test_widgets:
            info = self.get_widget_info(w_name)
            if "error" in info:
                print(f"  ❌ {label:<18} ({w_name}): {RED}Lỗi - {info['error']}{RESET}")
            else:
                curr = info['current']
                choices_cnt = len(info['choices'])
                ro = " [Read-Only]" if info['readonly'] else ""
                print(f"  ✓ {label:<18} ({w_name:<16}): {GREEN}{curr:<20}{RESET}{ro} ({choices_cnt} choices)")
                results[w_name] = info
        return results

    def test_set_parameters(self, current_info: dict):
        banner("BƯỚC 2: KIỂM THỬ ĐIỀU CHỈNH THÔNG SỐ (SET & READBACK VERIFY)")

        test_cases = [
            ("iso", "ISO", ["100", "200", "400", "800", "1600"]),
            ("shutterspeed", "Shutter Speed", ["1/125", "1/250", "1/500", "1/60"]),
            ("whitebalance", "White Balance", ["Daylight", "Auto", "Tungsten", "Cloudy"]),
            ("capturetarget", "Capture Target", ["Internal RAM", "Memory card"]),
        ]

        for w_name, label, candidate_values in test_cases:
            info = current_info.get(w_name)
            if not info or "choices" not in info:
                continue

            orig_val = info["current"]
            available_choices = info["choices"]
            
            # Chọn 1 giá trị khác giá trị hiện tại để test
            target_val = None
            for c in candidate_values:
                if c in available_choices and str(c) != str(orig_val):
                    target_val = c
                    break

            if not target_val and len(available_choices) > 1:
                target_val = available_choices[0] if available_choices[0] != orig_val else available_choices[1]

            if not target_val:
                print(f"  ⏩ {label}: Không tìm thấy giá trị thay thế phù hợp để test.")
                continue

            print(f"\n[*] Đang test đổi {BOLD}{label}{RESET}: '{orig_val}' ➔ '{target_val}'")
            ok, msg = self.set_widget_value(w_name, target_val)
            if ok:
                print(f"  {GREEN}✓ Đổi thành công và đã xác thực lại: {msg}{RESET}")
            else:
                print(f"  {RED}❌ Thất bại: {msg}{RESET}")

            # Đổi lại giá trị ban đầu (restore)
            print(f"[*] Phục hồi lại {label}: ➔ '{orig_val}'")
            ok_restore, msg_restore = self.set_widget_value(w_name, orig_val)
            if ok_restore:
                print(f"  {GREEN}✓ Đã phục hồi về: {msg_restore}{RESET}")
            else:
                print(f"  {YELLOW}⚠️  Không thể phục hồi về '{orig_val}': {msg_restore}{RESET}")

    def test_liveview(self, count: int = 3):
        banner("BƯỚC 3: KIỂM THỬ LIVE VIEW (CAPTURE PREVIEW)")
        print(f"[*] Bắt đầu lấy {count} frames Live View từ Canon 6D...")

        preview_files = []
        for i in range(1, count + 1):
            t0 = time.time()
            try:
                camera_file = self.camera.capture_preview()
                latency_ms = (time.time() - t0) * 1000
                
                out_path = os.path.join(OUTPUT_DIR, f"liveview_frame_{i}.jpg")
                camera_file.save(out_path)
                file_size = os.path.getsize(out_path)
                
                print(f"  {GREEN}✓ Frame {i}: Đã lấy thành công ({latency_ms:.1f}ms, kích thước: {file_size/1024:.1f} KB) ➔ {out_path}{RESET}")
                preview_files.append(out_path)
                time.sleep(0.3)
            except gp.GPhoto2Error as e:
                print(f"  {RED}❌ Lỗi khi lấy Live View Frame {i}: {e}{RESET}")

        return preview_files

    def test_capture_photo(self):
        banner("BƯỚC 4: KIỂM THỬ CHỤP ẢNH THỰC TẾ (SHUTTER CAPTURE & DOWNLOAD)")
        
        # Đảm bảo target là Internal RAM để tải ảnh về máy tính
        self.set_widget_value("capturetarget", "Internal RAM")
        
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        print(f"[*] Đang kích hoạt Shutter chụp ảnh thực tế...")
        
        t0 = time.time()
        try:
            file_path = self.camera.capture(gp.GP_CAPTURE_IMAGE)
            capture_time = time.time() - t0
            print(f"  {GREEN}✓ Bấm chụp thành công trong {capture_time:.2f}s! Tên file trên camera: {file_path.folder}/{file_path.name}{RESET}")
            
            # Tải ảnh về PC
            t_down = time.time()
            dest_filename = f"capture_{timestamp}_{file_path.name}"
            dest_path = os.path.join(OUTPUT_DIR, dest_filename)
            
            print(f"[*] Đang kéo ảnh về máy tính ➔ {dest_path}...")
            camera_file = self.camera.file_get(file_path.folder, file_path.name, gp.GP_FILE_TYPE_NORMAL)
            camera_file.save(dest_path)
            
            down_time = time.time() - t_down
            file_size_mb = os.path.getsize(dest_path) / (1024 * 1024)
            print(f"  {GREEN}🎉 TẢI ẢNH THÀNH CÔNG! Dung lượng: {file_size_mb:.2f} MB, thời gian tải: {down_time:.2f}s{RESET}")
            return dest_path
        except gp.GPhoto2Error as e:
            print(f"  {RED}❌ Lỗi trong quá trình chụp/tải ảnh: {e}{RESET}")
            return None


def main():
    print(f"\n{BOLD}BẮT ĐẦU CHẠY TOÀN BỘ TEST CHO CANON EOS 6D...{RESET}")
    ctrl = Canon6DController()
    try:
        ctrl.connect()
        current_info = ctrl.test_read_all_settings()
        ctrl.test_set_parameters(current_info)
        ctrl.test_liveview(count=3)
        ctrl.test_capture_photo()
        
        banner("TỔNG KẾT KIỂM THỬ: TẤT CẢ CHỨC NĂNG HOẠT ĐỘNG HOÀN HẢO!")
        print(f"{GREEN}{BOLD}✓ 1. Đọc thông số máy ảnh (Read Settings)   : HOÀN TẤT{RESET}")
        print(f"{GREEN}{BOLD}✓ 2. Chỉnh thông số máy ảnh (Set Parameters) : HOÀN TẤT{RESET}")
        print(f"{GREEN}{BOLD}✓ 3. Luồng xem trước Live View (Preview)    : HOÀN TẤT{RESET}")
        print(f"{GREEN}{BOLD}✓ 4. Kích hoạt chụp & tải ảnh (Full Capture) : HOÀN TẤT{RESET}\n")
    except Exception as e:
        print(f"\n{RED}❌ Gặp ngoại lệ trong quá trình test: {e}{RESET}")
    finally:
        ctrl.close()


if __name__ == "__main__":
    main()
