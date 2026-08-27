import time
import gphoto2 as gp

print("=== TESTING CANON EOS 6D DIRECT SECTION LOOKUP ===")
context = gp.Context()
camera = gp.Camera()
camera.init(context)

config = camera.get_config(context)
actions = config.get_child_by_name("actions")
settings = config.get_child_by_name("settings")
imgsettings = config.get_child_by_name("imgsettings")
capturesettings = config.get_child_by_name("capturesettings")

# 1. Check widgets
w_ct = settings.get_child_by_name("capturetarget")
print(f"capturetarget: {w_ct.get_value()} (type={w_ct.get_type()})")

w_rel = actions.get_child_by_name("eosremoterelease")
print(f"eosremoterelease: {w_rel.get_value()} (type={w_rel.get_type()})")
choices = [w_rel.get_choice(i) for i in range(w_rel.count_choices())]
print(f"eosremoterelease choices: {choices}")

# 2. Set capturetarget = Internal RAM
w_ct.set_value("Internal RAM")
camera.set_config(config, context)
print("Set capturetarget = Internal RAM OK")
time.sleep(0.3)

# 3. Drain pending events
while True:
    ev_type, _ = camera.wait_for_event(50, context)
    if ev_type == gp.GP_EVENT_TIMEOUT:
        break

# 4. Trigger shutter
print("📸 Triggering Press Half MF -> Press Full MF -> Release...")
config = camera.get_config(context)
actions = config.get_child_by_name("actions")
w_rel = actions.get_child_by_name("eosremoterelease")
w_rel.set_value("Press Half MF")
camera.set_config(config, context)
time.sleep(0.3)

config = camera.get_config(context)
actions = config.get_child_by_name("actions")
w_rel = actions.get_child_by_name("eosremoterelease")
w_rel.set_value("Press Full MF")
camera.set_config(config, context)
time.sleep(0.5)

config = camera.get_config(context)
actions = config.get_child_by_name("actions")
w_rel = actions.get_child_by_name("eosremoterelease")
w_rel.set_value("Release")
camera.set_config(config, context)

# 5. Wait for GP_EVENT_FILE_ADDED
print("⏳ Waiting for file added event...")
deadline = time.monotonic() + 10.0
found = False
while time.monotonic() < deadline:
    ev_type, ev_data = camera.wait_for_event(300, context)
    if ev_type == gp.GP_EVENT_FILE_ADDED:
        print(f"🎉 FILE ADDED: {ev_data.folder}/{ev_data.name}")
        cam_file = camera.file_get(ev_data.folder, ev_data.name, gp.GP_FILE_TYPE_NORMAL)
        data = bytes(cam_file.get_data_and_size())
        print(f"🎉 SUCCESS! Downloaded {len(data):,} bytes ({len(data)/1024/1024:.2f} MB)!")
        found = True
        break

if not found:
    print("❌ No file added event received.")

camera.exit(context)
print("=== FINISHED ===")
