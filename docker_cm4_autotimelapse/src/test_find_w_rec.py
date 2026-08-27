import time
import gphoto2 as gp

context = gp.Context()
camera = gp.Camera()
camera.init(context)

config = camera.get_config(context)

def find_widget_by_scan(root, target_names):
    if isinstance(target_names, str):
        target_names = [target_names]
    targets = set(target_names)
    
    for i in range(root.count_children()):
        sec = root.get_child(i)
        if sec.get_name() in targets:
            return sec, sec.get_name()
        for j in range(sec.count_children()):
            w = sec.get_child(j)
            if w.get_name() in targets:
                return w, w.get_name()
            for k in range(w.count_children()):
                sub = w.get_child(k)
                if sub.get_name() in targets:
                    return sub, sub.get_name()
    return None, None

w_rel, n_rel = find_widget_by_scan(config, ["eosremoterelease"])
print(f"w_rel is not None: {w_rel is not None}")
print(f"bool(w_rel): {bool(w_rel)} (len={len(w_rel) if hasattr(w_rel, '__len__') else 'no len'})")

if w_rel is not None:
    print("\n📸 FIRING CANON 6D SHUTTER...")
    w_rel.set_value("Press Half MF")
    camera.set_config(config, context)
    time.sleep(0.3)

    config = camera.get_config(context)
    w_rel, _ = find_widget_by_scan(config, ["eosremoterelease"])
    w_rel.set_value("Press Full MF")
    camera.set_config(config, context)
    time.sleep(0.5)

    config = camera.get_config(context)
    w_rel, _ = find_widget_by_scan(config, ["eosremoterelease"])
    w_rel.set_value("Release")
    camera.set_config(config, context)
    print("✅ Shutter release commands sent!")

    print("⏳ Waiting for image file...")
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        ev_type, ev_data = camera.wait_for_event(300, context)
        if ev_type == gp.GP_EVENT_FILE_ADDED:
            print(f"🎉 FILE ADDED: {ev_data.folder}/{ev_data.name}")
            cam_file = camera.file_get(ev_data.folder, ev_data.name, gp.GP_FILE_TYPE_NORMAL)
            data = bytes(cam_file.get_data_and_size())
            print(f"🏆 SUCCESS! Downloaded {len(data):,} bytes ({len(data)/1024/1024:.2f} MB)!")
            break

camera.exit(context)
