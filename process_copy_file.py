import subprocess
import time

#HOST_FILE_PATH = "/root/open5gswork/open5gs/install/var/log/open5gs/amf.txt"
#HOST_FILE_PATH= "/root/open5gswork/open5gs/NEF/amf_logs.txt"
HOST_FILE_PATH = "/root/open5gswork/open5gs/install/var/log/open5gs/amf.txt"
CONTAINER_NAME = "core_crowler"
CONTAINER_DEST_PATH = "/home/user/app/resources/amf.txt"
INTERVAL_SECONDS = 3

def copy_file():
    try:
        subprocess.run(
            ["docker", "cp", HOST_FILE_PATH, f"{CONTAINER_NAME}:{CONTAINER_DEST_PATH}"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        print(f"[✓] File copied to {CONTAINER_NAME}:{CONTAINER_DEST_PATH}")
    except subprocess.CalledProcessError as e:
        print(f"[✗] Copy error: {e.stderr.decode().strip()}")

print(f"Running... copying every {INTERVAL_SECONDS} seconds. Press Ctrl+C to stop.")
while True:
    copy_file()
    time.sleep(INTERVAL_SECONDS)
