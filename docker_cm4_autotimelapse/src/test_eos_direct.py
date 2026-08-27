import time
import gphoto2 as gp

print("=== TESTING CANON EOS 6D DIRECT SHUTTER RELEASE ===")
context = gp.Context()
camera = gp.Camera()
camera.init(context)
print("Camera connected:", str(camera.get_summary(context).text if hasattr(camera.get_summary(context), 'text') else camera.get_summary(context)).split("\n")[0])

def find_widget(w, names):
    if isinstance(names, str):
        names = [names]
    target_set = set(names)
    def _rec(node):
        try:
            if node.get_name() in target_set:
                return node
        except Exception:
            pass
        try:
            for i in range(node.count_children()):
                res = _rec(node.get_child(i))
                if res:
                    return res
        except Exception:
            pass
        return None
    return _rec(w)

# 1. Set capturetarget = Internal RAM
config = camera.get_config(context)
w_ct = find_widget(config, ["capturetarget"])
if w_ct:
    print(f"Found capturetarget: current value = {w_ct.get_value()}")
    w_ct.set_value("Internal RAM")
    camera.set_config(config, context)
    print("Set capturetarget = Internal RAM OK")
    time.sleep(0.3)

# 2. Drain all pending events
while True:
    ev_type, _ = camera.wait_for_event(50, context)
    if ev_type == gp.GP_EVENT_TIMEOUT:
        break

# 3. Trigger Press Half MF -> Press Full MF -> Release
print("📸 Firing shutter with Press Full MF...")
config = camera.get_config(context)
w_rel = find_widget(config, ["eosremoterelease"])
if not w_rel:
    print("❌ eosremoterelease widget not found!")
else:
    print(f"Found eosremoterelease: {w_rel.get_value()}")
    w_rel.set_value("Press Half MF")
    camera.set_config(config, context)
    time.sleep(0.3)

    config = camera.get_config(context)
    w_rel = find_widget(config, ["eosremoterelease"])
    w_rel.set_value("Press Full MF")
    camera.set_config(config, context)
    time.sleep(0.5)

    config = camera.get_config(context)
    w_rel = find_widget(config, ["eosremoterelease"])
    w_rel.set_value("Release")
    camera.set_config(config, context)

# 4. Wait for GP_EVENT_FILE_ADDED
print("⏳ Waiting for file added event...")
deadline = time.monotonic() + 10.0
found = False
while time.monotonic() < deadline:
    ev_type, ev_data = camera.wait_for_event(300, context)
    if ev_type == gp.GP_EVENT_FILE_ADDED:
        print(f"🎉 FILE ADDED: folder='{ev_data.folder}', name='{ev_data.name}'")
        cam_file = camera.file_get(ev_data.folder, ev_data.name, gp.GP_FILE_TYPE_NORMAL)
        data = bytes(cam_file.get_data_and_size())
        print(f"🎉 SUCCESS! Downloaded {len(data):,} bytes ({len(data)/1024/1024:.2f} MB)!")
        found = True
        break

if not found:
    print("❌ No file added event received.")

camera.exit(context)
print("=== FINISHED ===")
