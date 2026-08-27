import gphoto2 as gp

context = gp.Context()
camera = gp.Camera()
camera.init(context)

cfg_without = camera.get_config()
print(f"cfg_without count_children: {cfg_without.count_children()}")
for i in range(cfg_without.count_children()):
    print(f"  without child {i}: {cfg_without.get_child(i).get_name()}")

cfg_with = camera.get_config(context)
print(f"cfg_with count_children: {cfg_with.count_children()}")
for i in range(cfg_with.count_children()):
    print(f"  with child {i}: {cfg_with.get_child(i).get_name()}")

camera.exit(context)
