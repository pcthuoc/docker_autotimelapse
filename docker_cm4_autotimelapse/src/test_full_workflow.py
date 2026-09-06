import sys
import time
import gphoto2 as gp

sys.path.insert(0, "/app/src")
from power_manager import CameraPowerManager
from usb_utils import reset_all_camera_usb_devices

print("=" * 60)
print("📸 TEST CHỤP ẢNH CANON EOS 6D TOÀN DIỆN (FULL WORKFLOW)")
print("=" * 60)

# 1. Bật nguồn máy ảnh GPIO 16
pm = CameraPowerManager(pin=16, active_high=True, warmup_delay=4.0)
pm.power_on()

# 2. Reset cổng USB để xóa mọi lock cũ
print("🔄 Đang reset cổng USB máy ảnh...")
try:
    reset_all_camera_usb_devices()
    print("✅ Reset USB thành công!")
except Exception as e:
    print(f"⚠️ Reset USB: {e}")

time.sleep(1.0)

# 3. Kết nối gphoto2
context = gp.Context()
camera = None
for attempt in range(1, 6):
    try:
        camera = gp.Camera()
        camera.init(context)
        print(f"✅ Kết nối máy ảnh thành công (lần {attempt}):", str(camera.get_summary(context).text if hasattr(camera.get_summary(context), 'text') else camera.get_summary(context)).split('\n')[0])
        break
    except Exception as e:
        print(f"⏳ Đang chờ máy ảnh (lần {attempt}/5): {e}")
        time.sleep(1.5)

if not camera:
    print("❌ Không thể kết nối máy ảnh!")
    pm.power_off()
    sys.exit(1)

def find_w(cfg, names):
    if isinstance(names, str):
        names = [names]
    for n in names:
        try:
            return cfg.get_child_by_name(n), n
        except Exception:
            pass
    for i in range(cfg.count_children()):
        try:
            sec = cfg.get_child(i)
            for n in names:
                try:
                    return sec.get_child_by_name(n), n
                except Exception:
                    pass
        except Exception:
            pass
    return None, None

# 4. Kiểm tra và set capturetarget = Internal RAM
config = camera.get_config(context)
w_ct, _ = find_w(config, ["capturetarget"])
if w_ct and str(w_ct.get_value()) != "Internal RAM":
    w_ct.set_value("Internal RAM")
    camera.set_config(config, context)
    print("✅ Đã đặt capturetarget = Internal RAM")

# 5. Bấm chụp màn trập qua eosremoterelease
print("📸 Đang bấm màn trập Canon EOS Remote Release...")
config = camera.get_config(context)
w_rel, _ = find_w(config, ["eosremoterelease"])
if not w_rel:
    print("❌ Không tìm thấy widget eosremoterelease!")
else:
    choices = [str(w_rel.get_choice(i)) for i in range(w_rel.count_choices())] if w_rel.get_type() in (5, 6) else []
    print(f"📷 [CANON REMOTE] eosremoterelease choices: {choices}")
    rel_choice = next((c for c in ["Release Full", "Release 2", "Release 1", "Release", "None"] if c in choices), "None" if "None" in choices else None)

    triggered = False
    if "Immediate" in choices:
        print("📸 Sử dụng lệnh 'Immediate'...")
        w_rel.set_value("Immediate")
        camera.set_config(config, context)
        time.sleep(0.4)
        triggered = True
    else:
        press_full = next((c for c in ["Press Full", "Press 2", "Press 3"] if c in choices), None)
        press_half = next((c for c in ["Press Half", "Press 1"] if c in choices), None)
        if press_full:
            if press_half:
                try:
                    w_rel.set_value(press_half)
                    camera.set_config(config, context)
                    time.sleep(0.2)
                except Exception:
                    pass
            print(f"📸 Sử dụng lệnh '{press_full}'...")
            w_rel.set_value(press_full)
            camera.set_config(config, context)
            time.sleep(0.4)
            triggered = True

    if rel_choice:
        try:
            w_rel.set_value(rel_choice)
            camera.set_config(config, context)
        except Exception:
            pass

    # 5d. Chờ file ảnh
    print("⏳ Đang chờ nhận file ảnh từ máy ảnh...")
    deadline = time.monotonic() + 10.0
    downloaded = False
    while time.monotonic() < deadline:
        ev_type, ev_data = camera.wait_for_event(300, context)
        if ev_type == gp.GP_EVENT_FILE_ADDED:
            print(f"🎉 Phát hiện file ảnh mới: {ev_data.folder}/{ev_data.name}")
            cam_file = camera.file_get(ev_data.folder, ev_data.name, gp.GP_FILE_TYPE_NORMAL)
            data = bytes(cam_file.get_data_and_size())
            print(f"🏆 THÀNH CÔNG RỰC RỠ! Đã tải ảnh thật: {len(data):,} bytes ({len(data)/1024/1024:.2f} MB)")
            downloaded = True
            break

    # Fallback: Thử capture chuẩn nếu chưa nhận file
    if not downloaded:
        print("⚠️ Chưa nhận được event FILE_ADDED qua eosremoterelease. Thử capture(GP_CAPTURE_IMAGE)...")
        try:
            file_path = camera.capture(gp.GP_CAPTURE_IMAGE, context)
            print(f"🎉 Capture thành công: {file_path.folder}/{file_path.name}")
            cam_file = camera.file_get(file_path.folder, file_path.name, gp.GP_FILE_TYPE_NORMAL)
            data = bytes(cam_file.get_data_and_size())
            print(f"🏆 THÀNH CÔNG RỰC RỠ! Đã tải ảnh: {len(data):,} bytes ({len(data)/1024/1024:.2f} MB)")
            downloaded = True
        except Exception as e_cap:
            print(f"⚠️ Lỗi capture fallback: {e_cap}")

# 6. Đóng kết nối và tắt nguồn máy ảnh
camera.exit(context)
print("🔌 Đã đóng kết nối gphoto2.")
pm.power_off()
print("🔌 Đã TẮT NGUỒN máy ảnh qua GPIO 16.")
print("=" * 60)
