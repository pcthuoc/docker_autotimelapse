import gphoto2 as gp

context = gp.Context()
camera = gp.Camera()
camera.init(context)

config = camera.get_config(context)

def print_tree(node, level=0):
    indent = "  " * level
    name = node.get_name()
    label = node.get_label()
    wtype = node.get_type()
    count = node.count_children()
    print(f"{indent}- Name: '{name}' | Label: '{label}' | Type: {wtype} | Children: {count}")
    for i in range(count):
        print_tree(node.get_child(i), level + 1)

print("=== GPHOTO2 CONFIG TREE ===")
print_tree(config)
camera.exit(context)
