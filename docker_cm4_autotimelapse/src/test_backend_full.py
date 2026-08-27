import sys
import logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')

sys.path.insert(0, "/app/src")
from power_manager import CameraPowerManager
from camera_backend import HybridCameraBackend

print("=== STARTING DIRECT BACKEND CAPTURE TEST ===")
pm = CameraPowerManager(pin=16, active_high=True, warmup_delay=5.0)
pm.power_on()

backend = HybridCameraBackend(pm)

print("--- Calling backend.capture() ---")
try:
    files = backend.capture(camera_code="CAM-KCSHPT")
    print(f"Result: {len(files)} files captured.")
    for name, data, thumb in files:
        print(f"  File: '{name}', data size: {len(data):,} bytes ({len(data)/1024/1024:.2f} MB), thumb: {len(thumb) if thumb else 0} bytes")
except Exception as e:
    print(f"EXCEPTION: {e}")
    import traceback
    traceback.print_exc()

print("--- Calling pm.power_off() ---")
backend.disconnect_real_camera()
pm.power_off()
print("=== FINISHED ===")
