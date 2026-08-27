import sys
import logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')

sys.path.insert(0, "/app/src")
import gphoto2 as gp

context = gp.Context()
camera = gp.Camera()
camera.init(context)

config = camera.get_config(context)

print(f"Config root name: {config.get_name()}, children count: {config.count_children()}")
for i in range(config.count_children()):
    child = config.get_child(i)
    print(f"  Child {i}: name='{child.get_name()}', label='{child.get_label()}', subchildren={child.count_children()}")
    try:
        w_rel = child.get_child_by_name("eosremoterelease")
        print(f"    -> FOUND eosremoterelease in child '{child.get_name()}'! Value={w_rel.get_value()}")
    except Exception as e:
        pass
    try:
        w_ct = child.get_child_by_name("capturetarget")
        print(f"    -> FOUND capturetarget in child '{child.get_name()}'! Value={w_ct.get_value()}")
    except Exception as e:
        pass

# Test direct find_widget logic
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

w1, n1 = find_w(config, ["eosremoterelease"])
print(f"find_w('eosremoterelease') -> {w1}, {n1}")
w2, n2 = find_w(config, ["capturetarget"])
print(f"find_w('capturetarget') -> {w2}, {n2}")
w3, n3 = find_w(config, ["iso"])
print(f"find_w('iso') -> {w3}, {n3}")
w4, n4 = find_w(config, ["shutterspeed"])
print(f"find_w('shutterspeed') -> {w4}, {n4}")

camera.exit(context)
