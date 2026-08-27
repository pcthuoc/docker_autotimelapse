#!/usr/bin/env python3
"""
================================================================================
SCRIPT TEST ĐIỀU KHIỂN & CHỈNH THÔNG SỐ MÁY ẢNH (CANON 6D / 5D / 7D / NIKON)
================================================================================
Chức năng:
  1. Tự động bật GPIO 16 (nguồn máy ảnh) & kiểm tra cổng USB
  2. Kết nối gphoto2 & lấy thông tin Model, Serial, Lens, Battery
  3. Đọc danh sách tất cả thông số hiện tại + các lựa chọn (choices) hỗ trợ
  4. Thử thay đổi các thông số: ISO, Shutter Speed, Aperture, White Balance
  5. Tự động TẮT Auto Power Off & đặt Drive Mode = Single
  6. Bấm chụp thử 1 ảnh & lưu về máy kiểm tra
================================================================================
Cách chạy trên CM4:
  python3 test_canon_control.py
Hoặc chạy trong Docker container:
  docker exec -it cm4_camera_agent python3 /app/src/test_canon_control.py
================================================================================
"""

import sys
import os
import time

# ── 1. KIỂM TRA & BẬT NGUỒN GPIO 16 ──────────────────────────────────────────
def ensure_gpio_power(pin=16):
    try:
        import RPi.GPIO as GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(pin, GPIO.OUT)
        GPIO.output(pin, GPIO.HIGH)
        print(f"⚡ [GPIO] Đã bật nguồn GPIO {pin} (HIGH). Chờ 4s cho máy ảnh lên nguồn...")
        time.sleep(4.0)
    except Exception as e:
        print(f"ℹ️ [GPIO] Bỏ qua GPIO ({e}) - Giả định máy ảnh đã bật sẵn.")

# ── 2. KIỂM TRA THƯ VIỆN GPHOTO2 ─────────────────────────────────────────────
try:
    import gphoto2 as gp
except ImportError:
    print("❌ Lỗi: Chưa cài đặt thư viện python-gphoto2!")
    print("👉 Hãy chạy: pip3 install gphoto2")
    sys.exit(1)

# Helper tìm widget
def find_widget(config, candidate_names):
    if isinstance(candidate_names, str):
        candidate_names = [candidate_names]
    for name in candidate_names:
        try:
            return config.get_child_by_name(name), name
        except Exception:
            continue
    return None, None

def get_widget_choices(widget):
    wtype = widget.get_type()
    if wtype in (gp.GP_WIDGET_RADIO, gp.GP_WIDGET_MENU):
        return [str(widget.get_choice(i)) for i in range(widget.count_choices())]
    return []

def main():
    print("=" * 70)
    print("📸 BẮT ĐẦU TEST ĐIỀU KHIỂN MÁY ẢNH CANON / NIKON")
    print("=" * 70)

    # Bật nguồn GPIO
    ensure_gpio_power(16)

    # Khởi tạo kết nối máy ảnh
    cam = None
    print("\n🔍 Đang tìm và kết nối máy ảnh qua USB...")
    for attempt in range(1, 6):
        try:
            cam = gp.Camera()
            cam.init()
            summary = cam.get_summary()
            first_line = str(summary.text if hasattr(summary, 'text') else summary).split('\n')[0]
            print(f"✅ [KẾT NỐI THÀNH CÔNG] Lần thử {attempt}: {first_line}")
            break
        except Exception as e:
            print(f"⏳ [Lần {attempt}/5] Chưa thấy máy ảnh ({e}), thử lại sau 2s...")
            time.sleep(2.0)

    if not cam:
        print("\n❌ KHÔNG THỂ KẾT NỐI MÁY ẢNH!")
        print("👉 Kiểm tra:")
        print("   1. Cáp USB đã cắm chắc chưa?")
        print("   2. Máy ảnh đã gạt công tắc ON chưa?")
        print("   3. Đã có pin / nguồn cấp vào máy ảnh chưa?")
        return

    try:
        # Lấy thông tin cơ bản
        config = cam.get_config()
        abilities = cam.get_abilities()
        model_name = getattr(abilities, 'model', 'Unknown Camera')
        print(f"\n🏷️  Model phát hiện: {model_name}")

        # Đọc Lens, Serial, Battery
        lens_w, _ = find_widget(config, ["lensname", "lensid", "eoslensname"])
        lens_name = lens_w.get_value() if lens_w else "Unknown"

        serial_w, _ = find_widget(config, ["serialnumber", "eosserialnumber"])
        serial_no = serial_w.get_value() if serial_w else "Unknown"

        bat_w, bat_name = find_widget(config, ["eosbatterylevel", "batterylevel"])
        bat_val = bat_w.get_value() if bat_w else "Unknown"

        print(f"🔍 Lens:    {lens_name}")
        print(f"🔢 Serial:  {serial_no}")
        print(f"🔋 Battery: {bat_val} (widget: {bat_name})")

        # ── 3. ĐỌC THÔNG SỐ HIỆN TẠI VÀ DANH SÁCH CHOICES ────────────────────
        print("\n" + "=" * 70)
        print("📋 DANH SÁCH THÔNG SỐ HIỆN TẠI & LỰA CHỌN KHẢ DỤNG:")
        print("=" * 70)

        SETTINGS_TO_CHECK = {
            "ISO":           ["iso", "eos-iso"],
            "Shutter Speed": ["shutterspeed", "eos-shutterspeed", "shutterspeed2"],
            "Aperture":      ["aperture", "aperturevalue", "f-number", "fnumber"],
            "White Balance": ["whitebalance", "eos-whitebalance"],
            "Image Format":  ["imageformat", "imagequality", "imageformatsd"],
            "Drive Mode":    ["drivemode"],
            "Auto Power Off":["autopoweroff", "eosautopoweroff"],
            "Capture Target":["capturetarget"],
            "Metering Mode": ["meteringmode", "eos-meteringmode"],
        }

        current_values = {}
        all_choices = {}

        for label, candidate_names in SETTINGS_TO_CHECK.items():
            w, matched_name = find_widget(config, candidate_names)
            if w:
                try:
                    val = str(w.get_value())
                    ro = " [READ-ONLY]" if w.get_readonly() else " [WRITABLE]"
                    choices = get_widget_choices(w)
                    current_values[label] = val
                    all_choices[label] = choices
                    print(f"  • {label:16}: {val:18}{ro} (widget: {matched_name})")
                    if choices:
                        sample_choices = choices[:8]
                        extra = f" ... (+{len(choices)-8} nữa)" if len(choices) > 8 else ""
                        print(f"    ↳ Choices: {sample_choices}{extra}")
                except Exception as ex:
                    print(f"  • {label:16}: Lỗi đọc ({ex})")
            else:
                print(f"  • {label:16}: ⚠️ Không tìm thấy widget phù hợp trong {candidate_names}")

        # ── 4. THỬ CÀI ĐẶT THÔNG SỐ (SET SETTINGS) ───────────────────────────
        print("\n" + "=" * 70)
        print("⚙️  TIẾN HÀNH TEST THAY ĐỔI THÔNG SỐ MÁY ẢNH:")
        print("=" * 70)

        # Lấy lại config mới nhất
        config = cam.get_config()
        changed = []

        # 4a. Tắt Auto Power Off (Canon)
        apo_w, apo_name = find_widget(config, ["autopoweroff", "eosautopoweroff"])
        if apo_w and not apo_w.get_readonly():
            choices = get_widget_choices(apo_w)
            for off_opt in ["0", "Off", "None", "Disable"]:
                if off_opt in choices or not choices:
                    try:
                        apo_w.set_value(off_opt)
                        changed.append(f"Auto Power Off -> {off_opt}")
                        print(f"  ✅ Đã đặt Auto Power Off = '{off_opt}' (Tránh Canon tự ngủ)")
                        break
                    except Exception as e:
                        pass

        # 4b. Đặt Drive Mode = Single
        dm_w, dm_name = find_widget(config, ["drivemode"])
        if dm_w and not dm_w.get_readonly():
            choices = get_widget_choices(dm_w)
            for s_opt in ["Single", "Single shooting", "Single shot"]:
                if s_opt in choices or not choices:
                    try:
                        dm_w.set_value(s_opt)
                        changed.append(f"Drive Mode -> {s_opt}")
                        print(f"  ✅ Đã đặt Drive Mode = '{s_opt}'")
                        break
                    except Exception:
                        pass

        # 4c. Đổi ISO thử nghiệm (chọn giá trị hợp lệ từ choices)
        iso_w, iso_name = find_widget(config, ["iso", "eos-iso"])
        if iso_w and not iso_w.get_readonly():
            iso_choices = get_widget_choices(iso_w)
            target_iso = "400" if "400" in iso_choices else (iso_choices[1] if len(iso_choices) > 1 else "400")
            try:
                iso_w.set_value(target_iso)
                changed.append(f"ISO -> {target_iso}")
                print(f"  ✅ Đã đặt ISO = '{target_iso}'")
            except Exception as e:
                print(f"  ⚠️ Không set được ISO: {e}")

        # 4d. Đổi Shutter Speed thử nghiệm
        shutter_w, shutter_name = find_widget(config, ["shutterspeed", "eos-shutterspeed", "shutterspeed2"])
        if shutter_w and not shutter_w.get_readonly():
            shutter_choices = get_widget_choices(shutter_w)
            target_shutter = "1/125" if "1/125" in shutter_choices else (shutter_choices[len(shutter_choices)//2] if shutter_choices else "1/125")
            try:
                shutter_w.set_value(target_shutter)
                changed.append(f"Shutter Speed -> {target_shutter}")
                print(f"  ✅ Đã đặt Shutter Speed = '{target_shutter}'")
            except Exception as e:
                print(f"  ⚠️ Không set được Shutter Speed: {e}")

        # 4e. Đổi White Balance thử nghiệm
        wb_w, wb_name = find_widget(config, ["whitebalance", "eos-whitebalance"])
        if wb_w and not wb_w.get_readonly():
            wb_choices = get_widget_choices(wb_w)
            target_wb = "Daylight" if "Daylight" in wb_choices else ("Auto" if "Auto" in wb_choices else (wb_choices[0] if wb_choices else "Auto"))
            try:
                wb_w.set_value(target_wb)
                changed.append(f"White Balance -> {target_wb}")
                print(f"  ✅ Đã đặt White Balance = '{target_wb}'")
            except Exception as e:
                print(f"  ⚠️ Không set được White Balance: {e}")

        # Ghi config xuống máy ảnh thật
        if changed:
            print("\n💾 Đang ghi toàn bộ cấu hình mới xuống phần cứng máy ảnh...")
            cam.set_config(config)
            print("🎉 GHI CẤU HÌNH THÀNH CÔNG!")
            time.sleep(1.0)

            # Đọc lại để kiểm chứng (Read-back verification)
            print("\n🔍 ĐỌC LẠI ĐỂ XÁC MINH PHẦN CỨNG ĐÃ NHẬN:")
            verify_cfg = cam.get_config()
            for item in changed:
                name_part = item.split(" -> ")[0]
                target_val = item.split(" -> ")[1]
                w_list = SETTINGS_TO_CHECK.get(name_part, [])
                v_w, _ = find_widget(verify_cfg, w_list)
                actual = v_w.get_value() if v_w else "N/A"
                status = "✅ KHỚP" if str(actual) == str(target_val) else f"⚠️ KHÁC (Hiện tại: {actual})"
                print(f"  • {name_part:16}: Yêu cầu '{target_val}' ➔ Thực tế '{actual}' [{status}]")

        # ── 5. TEST BẤM CHỤP ẢNH THẬT (MÀN TRẬP) ─────────────────────────────
        print("\n" + "=" * 70)
        print("📸 TEST BẤM CHỤP MÀN TRẬP & TẢI ẢNH:")
        print("=" * 70)
        print("👉 Lắng nghe tiếng màn trập cơ học trên máy ảnh!")

        file_path = None
        try:
            file_path = cam.capture(gp.GP_CAPTURE_IMAGE)
            print(f"🎉 [CAPTURE OK] Đã chụp ảnh thành công! File: {file_path.folder}/{file_path.name}")
        except Exception as e_cap:
            print(f"⚠️ Lỗi capture(): {e_cap} -> Thử trigger_capture()...")
            try:
                cam.trigger_capture()
                print("🎉 [TRIGGER OK] Đã phát lệnh trigger_capture thành công!")
            except Exception as e_trig:
                print(f"❌ trigger_capture cũng lỗi: {e_trig}")

        # Chờ file ảnh nạp về
        print("⏳ Đang chờ nạp file qua USB...")
        deadline = time.monotonic() + 10
        saved_files = []
        if file_path:
            saved_files.append(file_path)

        while time.monotonic() < deadline:
            try:
                ev_type, ev_data = cam.wait_for_event(400)
                if ev_type == gp.GP_EVENT_FILE_ADDED:
                    print(f"📥 Phát hiện file mới: {ev_data.folder}/{ev_data.name}")
                    saved_files.append(ev_data)
                    break
                elif ev_type == gp.GP_EVENT_CAPTURE_COMPLETE:
                    if saved_files:
                        break
            except Exception:
                break

        if saved_files:
            target = saved_files[0]
            out_name = f"TEST_{target.name}"
            print(f"💾 Đang tải {target.folder}/{target.name} về file '{out_name}'...")
            cam_file = cam.file_get(target.folder, target.name, gp.GP_FILE_TYPE_NORMAL)
            data = bytes(cam_file.get_data_and_size())
            with open(out_name, "wb") as f:
                f.write(data)
            print(f"🏆 THÀNH CÔNG RỰC RỠ! Đã lưu ảnh '{out_name}' ({len(data):,} bytes / {len(data)/1024/1024:.2f} MB)")
        else:
            print("⚠️ Chưa kéo được file ảnh (có thể ảnh đã lưu trực tiếp vào thẻ nhớ SD).")

    finally:
        try:
            cam.exit()
            print("\n🔌 Đã đóng kết nối máy ảnh gphoto2 an toàn.")
        except Exception:
            pass

    print("=" * 70)
    print("🏁 KẾT THÚC TEST")
    print("=" * 70)

if __name__ == "__main__":
    main()
