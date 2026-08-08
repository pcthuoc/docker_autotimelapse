#!/usr/bin/env python3
"""
Orchestrator Main Entrypoint for CM4 / Camera Agent.
Triggers camera_wifi_agent.py execution.
"""
import os
import sys

def main():
    dir_path = os.path.dirname(os.path.abspath(__file__))
    target_script = os.path.join(dir_path, "camera_wifi_agent.py")
    if not os.path.exists(target_script):
        target_script = os.path.join(dir_path, "repo", "camera_wifi_agent.py")
        
    if os.path.exists(target_script):
        os.execv(sys.executable, [sys.executable, "-u", target_script] + sys.argv[1:])
    else:
        print(f"❌ Error: {target_script} not found!")
        sys.exit(1)

if __name__ == "__main__":
    main()
