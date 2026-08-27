import gphoto2 as gp
import time

context = gp.Context()
camera = gp.Camera()
camera.init(context)

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

config = camera.get_config(context)
w_rel, n = find_w(config, ["eosremoterelease"])
print(f"Found: {w_rel}, {n}")

print("Setting Press Half MF...")
try:
    w_rel.set_value("Press Half MF")
    print("set_value OK")
    camera.set_config(config, context)
    print("set_config Press Half MF OK!")
    time.sleep(0.3)
except Exception as e:
    print(f"EXCEPTION: {e}")

print("Setting Press Full MF...")
try:
    config = camera.get_config(context)
    w_rel, n = find_w(config, ["eosremoterelease"])
    w_rel.set_value("Press Full MF")
    camera.set_config(config, context)
    print("set_config Press Full MF OK!")
    time.sleep(0.5)
except Exception as e:
    print(f"EXCEPTION: {e}")

print("Setting Release...")
try:
    config = camera.get_config(context)
    w_rel, n = find_w(config, ["eosremoterelease"])
    w_rel.set_value("Release")
    camera.set_config(config, context)
    print("set_config Release OK!")
except Exception as e:
    print(f"EXCEPTION: {e}")

print("Waiting for file event...")
deadline = time.monotonic() + 10.0
while time.monotonic() < deadline:
    ev_type, ev_data = camera.wait_for_event(300, context)
    if ev_type == gp.GP_EVENT_FILE_ADDED:
        print(f"🎉 FILE ADDED: {ev_data.folder}/{ev_data.name}")
        cam_file = camera.file_get(ev_data.folder, ev_data.name, gp.GP_FILE_TYPE_NORMAL)
        data = bytes(cam_file.get_data_and_size())
        print(f"🎉 DOWNLOADED: {len(data):,} bytes ({len(data)/1024/1024:.2f} MB)")
        break

camera.exit(context)
