import logging
import os
import subprocess
import time
from pathlib import Path
import shutil


class NbdManager:
    def __init__(self, disk_image: str):
        self.disk_image = Path(disk_image).expanduser().resolve()
        self.logger = logging.getLogger("fawkes.NbdManager")
        self.nbd_dev = None
        if not shutil.which("qemu-nbd"):
            raise RuntimeError("qemu-nbd not found. Install with 'sudo apt install qemu-utils'.")
        # Clean up stale NBD devices
        for i in range(16):
            dev = f"/dev/nbd{i}"
            subprocess.run(["sudo", "qemu-nbd", "-d", dev], check=False)
        time.sleep(1)  # Let them die...


    def _find_free_nbd(self):
        for i in range(16):
            dev = f"/dev/nbd{i}"
            if not os.path.exists(dev):
                self.logger.debug(f"NBD device {dev} does not exist, skipping")
                continue
            try:
                subprocess.run(["sudo", "qemu-nbd", "-c", dev, str(self.disk_image)],
                              check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
                subprocess.run(["sudo", "qemu-nbd", "-d", dev], check=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                self.logger.debug(f"Found free NBD device: {dev}")
                return dev
            except subprocess.CalledProcessError as e:
                self.logger.debug(f"NBD device {dev} in use or failed: {e.stderr.decode()}")
                continue
        raise RuntimeError("No available NBD devices found. Free up /dev/nbd* or increase kernel NBD max devices.")

    def mount(self, mount_point: str):
        mount_point = Path(mount_point).expanduser().resolve()
        mount_point.mkdir(parents=True, exist_ok=True)
        os.chmod(mount_point, 0o777)  # Ensure writable
        if not self.nbd_dev:
            self.nbd_dev = self._find_free_nbd()
        self.logger.debug(f"Mounting {self.disk_image} to {mount_point} via {self.nbd_dev}")

        subprocess.run(["sudo", "modprobe", "nbd"], check=True)
        subprocess.run(["sudo", "qemu-nbd", "-d", self.nbd_dev], check=False)
        time.sleep(1)

        try:
            result = subprocess.run(["sudo", "qemu-nbd", "-c", self.nbd_dev, str(self.disk_image)],
                                   check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
            self.logger.debug(f"qemu-nbd connected: {result.stdout.decode()}")
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to connect NBD: {e.stderr.decode()}")
            raise

        time.sleep(1)
        partition = f"{self.nbd_dev}p1"
        if not os.path.exists(partition):
            self.logger.error(f"Partition {partition} not found")
            subprocess.run(["sudo", "qemu-nbd", "-d", self.nbd_dev], check=False)
            raise FileNotFoundError(f"Expected partition {partition} not available")

        try:
            subprocess.run(["sudo", "mount", "-o", "uid=1000,gid=1000", partition, str(mount_point)],
                          check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Mount failed: {e.stderr.decode()}")
            subprocess.run(["sudo", "qemu-nbd", "-d", self.nbd_dev], check=False)
            raise
        return mount_point

    def unmount(self, mount_point: str):
        mount_point = Path(mount_point).expanduser().resolve()
        self.logger.debug(f"Unmounting {mount_point}")
        try:
            subprocess.run(["sudo", "umount", str(mount_point)], check=True)
            subprocess.run(["sudo", "qemu-nbd", "-d", self.nbd_dev], check=True)
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Unmount failed: {e.stderr.decode()}")
            raise
        finally:
            time.sleep(1)
            if mount_point.exists():
                shutil.rmtree(mount_point, ignore_errors=True)

    def inject_script(self, script_content: str, dest_path: str, mount_point: str):
        mount_point = self.mount(mount_point)
        script_path = mount_point / dest_path.lstrip("/")
        script_path.parent.mkdir(parents=True, exist_ok=True)
        with script_path.open("w") as f:
            f.write(script_content)
        self.logger.info(f"Injected script to {script_path}")
