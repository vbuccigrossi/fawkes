"""
VM Installation Mode API endpoints.

Handles booting VMs with ISO images for OS installation,
with VNC/noVNC access for interactive installation.
"""

import logging
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional

from fastapi import APIRouter, HTTPException, WebSocket
from pydantic import BaseModel, Field

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from paths import paths

from api.database import db_manager
from api.models.vm_setup import VMInstallationStart, VMInstallationStatus

router = APIRouter()
logger = logging.getLogger("fawkes.web.api.vm_install")

# Track running installation VMs
installation_vms: Dict[int, Dict[str, Any]] = {}
next_install_vm_id = 1


# VM Configuration Presets
VM_PRESETS = {
    "windows11": {
        "name": "Windows 11",
        "description": "Windows 11 with UEFI, TPM 2.0, and modern hardware",
        "config": {
            "arch": "x86_64",
            "memory": "4G",
            "cpu_cores": 4,
            "cpu_model": "host",
            "enable_kvm": True,
            "uefi": True,
            "secure_boot": False,  # Requires special OVMF
            "tpm_enabled": True,
            "tpm_version": "2.0",
            "machine_type": "q35",
            "vga": "qxl",
            "disk_interface": "virtio",
            "disk_cache": "writeback",
            "network_model": "e1000e",
            "usb_enabled": True,
            "usb_tablet": True,
            "audio_enabled": True,
            "audio_device": "intel-hda",
            "boot_order": "dc",
            "rtc_base": "localtime",
        }
    },
    "windows10": {
        "name": "Windows 10",
        "description": "Windows 10 with standard hardware",
        "config": {
            "arch": "x86_64",
            "memory": "4G",
            "cpu_cores": 4,
            "cpu_model": "host",
            "enable_kvm": True,
            "uefi": False,
            "machine_type": "q35",
            "vga": "qxl",
            "disk_interface": "virtio",
            "disk_cache": "writeback",
            "network_model": "e1000e",
            "usb_enabled": True,
            "usb_tablet": True,
            "audio_enabled": True,
            "audio_device": "intel-hda",
            "boot_order": "dc",
            "rtc_base": "localtime",
        }
    },
    "ubuntu_desktop": {
        "name": "Ubuntu Desktop",
        "description": "Ubuntu/Debian desktop with virtio drivers",
        "config": {
            "arch": "x86_64",
            "memory": "4G",
            "cpu_cores": 4,
            "cpu_model": "host",
            "enable_kvm": True,
            "uefi": True,
            "machine_type": "q35",
            "vga": "virtio",
            "disk_interface": "virtio",
            "disk_cache": "writeback",
            "network_model": "virtio-net-pci",
            "usb_enabled": True,
            "usb_tablet": True,
            "audio_enabled": True,
            "audio_device": "intel-hda",
            "boot_order": "dc",
            "rtc_base": "utc",
        }
    },
    "ubuntu_server": {
        "name": "Ubuntu Server",
        "description": "Ubuntu/Debian server (headless)",
        "config": {
            "arch": "x86_64",
            "memory": "2G",
            "cpu_cores": 2,
            "cpu_model": "host",
            "enable_kvm": True,
            "uefi": False,
            "vga": "std",
            "disk_interface": "virtio",
            "disk_cache": "writeback",
            "network_model": "virtio-net-pci",
            "usb_enabled": True,
            "usb_tablet": True,
            "audio_enabled": False,
            "serial_enabled": True,
            "serial_device": "pty",
            "boot_order": "dc",
            "rtc_base": "utc",
        }
    },
    "embedded_arm": {
        "name": "ARM Embedded Device",
        "description": "ARM32 embedded system (Cortex-A)",
        "config": {
            "arch": "arm",
            "memory": "512M",
            "cpu_cores": 1,
            "cpu_model": "cortex-a15",
            "enable_kvm": False,
            "machine_type": "virt",
            "uefi": False,
            "vga": "std",
            "disk_interface": "virtio",
            "network_model": "virtio-net-pci",
            "usb_enabled": False,
            "serial_enabled": True,
            "serial_device": "pty",
            "boot_order": "c",
            "rtc_base": "utc",
        }
    },
    "embedded_arm64": {
        "name": "ARM64 Embedded Device",
        "description": "ARM64 embedded system",
        "config": {
            "arch": "aarch64",
            "memory": "1G",
            "cpu_cores": 2,
            "cpu_model": "cortex-a72",
            "enable_kvm": False,
            "machine_type": "virt",
            "uefi": True,
            "vga": "std",
            "disk_interface": "virtio",
            "network_model": "virtio-net-pci",
            "usb_enabled": False,
            "serial_enabled": True,
            "serial_device": "pty",
            "boot_order": "c",
            "rtc_base": "utc",
        }
    },
    "embedded_mips": {
        "name": "MIPS Embedded Device",
        "description": "MIPS32 embedded system (router/IoT)",
        "config": {
            "arch": "mipsel",
            "memory": "256M",
            "cpu_cores": 1,
            "enable_kvm": False,
            "machine_type": "malta",
            "uefi": False,
            "vga": "std",
            "disk_interface": "ide",
            "network_model": "e1000",
            "usb_enabled": False,
            "serial_enabled": True,
            "serial_device": "pty",
            "boot_order": "c",
            "rtc_base": "utc",
        }
    },
    "freebsd": {
        "name": "FreeBSD",
        "description": "FreeBSD with virtio support",
        "config": {
            "arch": "x86_64",
            "memory": "2G",
            "cpu_cores": 2,
            "cpu_model": "host",
            "enable_kvm": True,
            "uefi": False,
            "vga": "std",
            "disk_interface": "virtio",
            "disk_cache": "writeback",
            "network_model": "virtio-net-pci",
            "usb_enabled": True,
            "usb_tablet": True,
            "serial_enabled": True,
            "serial_device": "pty",
            "boot_order": "dc",
            "rtc_base": "utc",
        }
    },
    "android": {
        "name": "Android x86",
        "description": "Android-x86 system",
        "config": {
            "arch": "x86_64",
            "memory": "4G",
            "cpu_cores": 4,
            "cpu_model": "host",
            "enable_kvm": True,
            "uefi": False,
            "machine_type": "q35",
            "vga": "virtio",
            "disk_interface": "virtio",
            "disk_cache": "writeback",
            "network_model": "e1000",
            "usb_enabled": True,
            "usb_tablet": True,
            "audio_enabled": True,
            "audio_device": "intel-hda",
            "boot_order": "dc",
            "rtc_base": "utc",
        }
    },
    "minimal": {
        "name": "Minimal",
        "description": "Minimal VM for testing",
        "config": {
            "arch": "x86_64",
            "memory": "512M",
            "cpu_cores": 1,
            "enable_kvm": True,
            "uefi": False,
            "vga": "std",
            "disk_interface": "virtio",
            "network_type": "none",
            "usb_enabled": False,
            "audio_enabled": False,
            "boot_order": "c",
            "rtc_base": "utc",
        }
    },
    "custom": {
        "name": "Custom",
        "description": "Start from scratch with manual configuration",
        "config": {
            "arch": "x86_64",
            "memory": "2G",
            "cpu_cores": 2,
            "enable_kvm": True,
            "boot_order": "dc",
        }
    }
}


def find_free_port(start: int = 5900, end: int = 6000) -> int:
    """Find a free port in the given range."""
    for port in range(start, end):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('', port))
                return port
        except OSError:
            continue
    raise RuntimeError(f"No free ports found in range {start}-{end}")


def get_qemu_binary(arch: str) -> str:
    """Get the QEMU binary for an architecture."""
    return f"qemu-system-{arch}"


class InstallVMCreate(BaseModel):
    """Request to create an installation VM with comprehensive configuration."""
    # Basic Configuration
    disk_image: str = Field(..., description="Path to the QCOW2 disk image")
    iso_path: Optional[str] = Field(None, description="Path to the ISO file for installation")
    arch: str = Field(default="x86_64", description="CPU architecture")

    # CPU Configuration
    memory: str = Field(default="2G", description="RAM allocation (e.g., 2G, 4096M)")
    cpu_cores: int = Field(default=2, ge=1, le=128, description="Number of CPU cores")
    cpu_model: Optional[str] = Field(None, description="CPU model (e.g., host, qemu64, Skylake-Client)")
    cpu_features: Optional[str] = Field(None, description="CPU features to enable/disable (e.g., +vmx,-svm)")

    # Acceleration
    enable_kvm: bool = Field(default=True, description="Enable KVM hardware acceleration")
    enable_hax: bool = Field(default=False, description="Enable HAXM acceleration (Windows/macOS)")

    # Boot Configuration
    boot_order: str = Field(default="dc", description="Boot order: d=cdrom, c=disk, n=network (e.g., 'dc', 'cdn')")
    boot_menu: bool = Field(default=False, description="Enable boot menu (F12)")
    uefi: bool = Field(default=False, description="Use UEFI firmware instead of BIOS")
    secure_boot: bool = Field(default=False, description="Enable Secure Boot (requires UEFI)")

    # Display/Graphics
    display: str = Field(default="vnc", description="Display type: vnc, sdl, gtk, spice, none")
    vga: str = Field(default="std", description="VGA type: std, cirrus, vmware, qxl, virtio, none")
    full_screen: bool = Field(default=False, description="Start in full screen mode")

    # Storage Configuration
    disk_interface: str = Field(default="virtio", description="Disk interface: virtio, ide, scsi, nvme, sd")
    disk_cache: str = Field(default="writeback", description="Disk cache mode: none, writeback, writethrough, unsafe")
    disk_aio: str = Field(default="threads", description="Disk AIO mode: threads, native, io_uring")
    cdrom_interface: str = Field(default="ide", description="CD-ROM interface: ide, scsi")

    # Additional Drives
    additional_drives: Optional[List[Dict[str, Any]]] = Field(None, description="Additional disk drives")

    # Network Configuration
    network_type: str = Field(default="user", description="Network type: user, tap, bridge, none")
    network_model: str = Field(default="virtio-net-pci", description="NIC model: virtio-net-pci, e1000, e1000e, rtl8139")
    mac_address: Optional[str] = Field(None, description="MAC address (auto-generated if not specified)")
    host_forward_ports: Optional[List[Dict[str, int]]] = Field(None, description="Host port forwards (user mode): [{host: 2222, guest: 22}]")
    bridge_interface: Optional[str] = Field(None, description="Bridge interface name (bridge mode)")
    tap_interface: Optional[str] = Field(None, description="TAP interface name (tap mode)")

    # USB Configuration
    usb_enabled: bool = Field(default=True, description="Enable USB controller")
    usb_tablet: bool = Field(default=True, description="USB tablet for better mouse handling")
    usb_keyboard: bool = Field(default=False, description="USB keyboard")
    usb_passthrough: Optional[List[Dict[str, str]]] = Field(None, description="USB passthrough: [{vendor: '1234', product: '5678'}]")

    # Audio
    audio_enabled: bool = Field(default=False, description="Enable audio")
    audio_device: str = Field(default="intel-hda", description="Audio device: intel-hda, ac97, es1370")

    # Serial/Parallel Ports
    serial_enabled: bool = Field(default=False, description="Enable serial port")
    serial_device: str = Field(default="pty", description="Serial device type: pty, stdio, file, tcp, unix")
    parallel_enabled: bool = Field(default=False, description="Enable parallel port")

    # TPM (for Windows 11)
    tpm_enabled: bool = Field(default=False, description="Enable TPM 2.0 emulation")
    tpm_version: str = Field(default="2.0", description="TPM version: 1.2, 2.0")

    # SMBIOS/DMI (System Information)
    smbios_manufacturer: Optional[str] = Field(None, description="SMBIOS manufacturer string")
    smbios_product: Optional[str] = Field(None, description="SMBIOS product name")
    smbios_version: Optional[str] = Field(None, description="SMBIOS version string")
    smbios_serial: Optional[str] = Field(None, description="SMBIOS serial number")
    smbios_uuid: Optional[str] = Field(None, description="SMBIOS UUID")

    # Machine Type
    machine_type: Optional[str] = Field(None, description="Machine type (e.g., pc, q35, virt, raspi3)")
    accel: Optional[str] = Field(None, description="Accelerator: kvm, hvf, whpx, tcg")

    # Advanced QEMU Options
    rtc_base: str = Field(default="utc", description="RTC base: utc, localtime")
    no_shutdown: bool = Field(default=False, description="Don't exit QEMU on guest shutdown")
    no_reboot: bool = Field(default=False, description="Exit instead of rebooting")
    snapshot_mode: bool = Field(default=False, description="Run in snapshot mode (no disk writes)")

    # Device Passthrough
    pci_passthrough: Optional[List[str]] = Field(None, description="PCI devices to passthrough (e.g., ['00:1f.3'])")

    # Extra QEMU Arguments
    extra_args: Optional[List[str]] = Field(None, description="Additional QEMU command-line arguments")

    # Shared Folders (9p/virtfs)
    shared_folders: Optional[List[Dict[str, str]]] = Field(None, description="Shared folders: [{host_path: '/path', mount_tag: 'share0'}]")

    # SPICE Options (if display=spice)
    spice_port: Optional[int] = Field(None, description="SPICE port (auto-assigned if not set)")
    spice_password: Optional[str] = Field(None, description="SPICE password")
    spice_tls: bool = Field(default=False, description="Enable SPICE TLS encryption")

    # Config saving options
    save_config: bool = Field(default=True, description="Save this configuration to a JSON file")
    config_name: Optional[str] = Field(None, description="Name for saved config (auto-generated if not set)")
    config_description: Optional[str] = Field(None, description="Description for saved config")
    config_tags: Optional[List[str]] = Field(None, description="Tags for saved config")


class SnapshotCreateRequest(BaseModel):
    """Request to create a snapshot from running VM."""
    name: str = Field(..., description="Snapshot name")


@router.get("/", response_model=Dict[str, Any])
async def list_installation_vms():
    """
    List all running installation VMs.
    """
    try:
        vms = []
        for vm_id, vm_info in installation_vms.items():
            # Check if process is still running
            pid = vm_info.get("pid")
            is_running = False
            if pid:
                try:
                    os.kill(pid, 0)
                    is_running = True
                except OSError:
                    is_running = False

            vms.append({
                "vm_id": vm_id,
                "pid": pid,
                "status": "running" if is_running else "stopped",
                "disk_image": vm_info.get("disk_image"),
                "iso_path": vm_info.get("iso_path"),
                "arch": vm_info.get("arch"),
                "vnc_port": vm_info.get("vnc_port"),
                "vnc_websocket_port": vm_info.get("vnc_ws_port"),
                "monitor_port": vm_info.get("monitor_port"),
                "started_at": vm_info.get("started_at"),
                "uptime_seconds": int(time.time() - vm_info.get("start_time", time.time()))
            })

        return {
            "success": True,
            "count": len(vms),
            "data": vms
        }
    except Exception as e:
        logger.error(f"Error listing installation VMs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/presets/", response_model=Dict[str, Any])
async def list_presets():
    """
    List available VM configuration presets.

    Returns preset configurations for common OS types.
    """
    try:
        presets = []
        for preset_id, preset in VM_PRESETS.items():
            presets.append({
                "id": preset_id,
                "name": preset["name"],
                "description": preset["description"],
                "config": preset["config"]
            })

        return {
            "success": True,
            "count": len(presets),
            "data": presets
        }
    except Exception as e:
        logger.error(f"Error listing presets: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/presets/{preset_id}", response_model=Dict[str, Any])
async def get_preset(preset_id: str):
    """
    Get a specific preset configuration.
    """
    try:
        if preset_id not in VM_PRESETS:
            raise HTTPException(
                status_code=404,
                detail=f"Preset '{preset_id}' not found. Available: {', '.join(VM_PRESETS.keys())}"
            )

        preset = VM_PRESETS[preset_id]
        return {
            "success": True,
            "data": {
                "id": preset_id,
                "name": preset["name"],
                "description": preset["description"],
                "config": preset["config"]
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting preset {preset_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


def build_qemu_command(request: InstallVMCreate, disk_path: Path, iso_path: Optional[Path],
                       vnc_display: int, monitor_port: int, spice_port: Optional[int] = None) -> List[str]:
    """Build the QEMU command line from the request configuration."""
    qemu_binary = get_qemu_binary(request.arch)
    cmd = [qemu_binary]

    # Machine type
    if request.machine_type:
        machine_str = request.machine_type
        if request.accel:
            machine_str += f",accel={request.accel}"
        cmd.extend(['-machine', machine_str])
    elif request.arch in ['x86_64', 'i386']:
        # Default to q35 for modern features (required for Windows 11)
        machine_str = "q35"
        if request.enable_kvm and os.path.exists('/dev/kvm') and os.access('/dev/kvm', os.R_OK | os.W_OK):
            machine_str += ",accel=kvm"
        cmd.extend(['-machine', machine_str])

    # CPU configuration
    cpu_spec = []
    if request.enable_kvm and os.path.exists('/dev/kvm') and os.access('/dev/kvm', os.R_OK | os.W_OK):
        cmd.append('-enable-kvm')
        if request.cpu_model:
            cpu_spec.append(request.cpu_model)
        else:
            cpu_spec.append('host')
    elif request.enable_hax:
        cmd.extend(['-accel', 'hax'])
        cpu_spec.append(request.cpu_model or 'qemu64')
    else:
        # Software emulation
        if request.cpu_model:
            cpu_spec.append(request.cpu_model)
        elif request.arch in ['x86_64', 'i386']:
            cpu_spec.append('qemu64')

    if request.cpu_features:
        cpu_spec.append(request.cpu_features)

    if cpu_spec:
        cmd.extend(['-cpu', ','.join(cpu_spec)])

    # Memory and SMP
    cmd.extend(['-m', request.memory])
    cmd.extend(['-smp', str(request.cpu_cores)])

    # UEFI/BIOS
    if request.uefi:
        # Common OVMF paths
        ovmf_paths = [
            '/usr/share/OVMF/OVMF_CODE.fd',
            '/usr/share/edk2/ovmf/OVMF_CODE.fd',
            '/usr/share/qemu/OVMF_CODE.fd',
            '/usr/share/ovmf/OVMF.fd',
        ]
        ovmf_path = None
        for p in ovmf_paths:
            if os.path.exists(p):
                ovmf_path = p
                break

        if ovmf_path:
            cmd.extend(['-bios', ovmf_path])
            if request.secure_boot:
                # Secure boot requires specific OVMF build
                logger.warning("Secure Boot requested but may require specific OVMF_CODE.secboot.fd")
        else:
            logger.warning("UEFI requested but OVMF not found, falling back to BIOS")

    # Primary disk drive
    drive_opts = [
        f'file={disk_path}',
        'format=qcow2',
        f'if={request.disk_interface}',
        f'cache={request.disk_cache}',
        f'aio={request.disk_aio}',
    ]
    if request.snapshot_mode:
        drive_opts.append('snapshot=on')
    cmd.extend(['-drive', ','.join(drive_opts)])

    # CD-ROM (if ISO provided)
    if iso_path:
        cdrom_opts = f'file={iso_path},media=cdrom'
        if request.cdrom_interface == 'scsi':
            cdrom_opts += ',if=none,id=cdrom0'
            cmd.extend(['-drive', cdrom_opts])
            cmd.extend(['-device', 'scsi-cd,drive=cdrom0'])
        else:
            cmd.extend(['-cdrom', str(iso_path)])

    # Additional drives
    if request.additional_drives:
        for i, drive in enumerate(request.additional_drives):
            d_opts = [f'file={drive.get("path")}']
            d_opts.append(f'format={drive.get("format", "qcow2")}')
            d_opts.append(f'if={drive.get("interface", "virtio")}')
            if drive.get("readonly"):
                d_opts.append('readonly=on')
            cmd.extend(['-drive', ','.join(d_opts)])

    # Boot configuration
    boot_opts = [f'order={request.boot_order}']
    if request.boot_menu:
        boot_opts.append('menu=on')
    cmd.extend(['-boot', ','.join(boot_opts)])

    # VGA/Display
    if request.vga != 'none':
        cmd.extend(['-vga', request.vga])

    # Display output
    if request.display == 'vnc':
        cmd.extend(['-vnc', f':{vnc_display}'])
    elif request.display == 'spice' and spice_port:
        spice_opts = f'port={spice_port},disable-ticketing=on'
        if request.spice_password:
            spice_opts = f'port={spice_port},password={request.spice_password}'
        if request.spice_tls:
            spice_opts += ',tls-port=' + str(spice_port + 1)
        cmd.extend(['-spice', spice_opts])
        # Also enable VNC as fallback
        cmd.extend(['-vnc', f':{vnc_display}'])
    elif request.display == 'none':
        cmd.extend(['-display', 'none'])
    else:
        cmd.extend(['-vnc', f':{vnc_display}'])

    # Monitor
    cmd.extend(['-monitor', f'tcp:127.0.0.1:{monitor_port},server,nowait'])

    # Network configuration
    if request.network_type == 'none':
        cmd.extend(['-nic', 'none'])
    elif request.network_type == 'user':
        nic_opts = [f'user', f'model={request.network_model}']
        if request.mac_address:
            nic_opts.append(f'mac={request.mac_address}')
        if request.host_forward_ports:
            for fwd in request.host_forward_ports:
                proto = fwd.get('proto', 'tcp')
                nic_opts.append(f'hostfwd={proto}::{fwd["host"]}-:{fwd["guest"]}')
        cmd.extend(['-nic', ','.join(nic_opts)])
    elif request.network_type == 'tap':
        tap_opts = [f'tap']
        if request.tap_interface:
            tap_opts.append(f'ifname={request.tap_interface}')
        tap_opts.append(f'model={request.network_model}')
        if request.mac_address:
            tap_opts.append(f'mac={request.mac_address}')
        cmd.extend(['-nic', ','.join(tap_opts)])
    elif request.network_type == 'bridge':
        bridge_opts = [f'bridge']
        if request.bridge_interface:
            bridge_opts.append(f'br={request.bridge_interface}')
        bridge_opts.append(f'model={request.network_model}')
        if request.mac_address:
            bridge_opts.append(f'mac={request.mac_address}')
        cmd.extend(['-nic', ','.join(bridge_opts)])

    # USB
    if request.usb_enabled:
        cmd.extend(['-usb'])
        if request.usb_tablet:
            cmd.extend(['-device', 'usb-tablet'])
        if request.usb_keyboard:
            cmd.extend(['-device', 'usb-kbd'])
        if request.usb_passthrough:
            for usb in request.usb_passthrough:
                cmd.extend(['-device', f'usb-host,vendorid=0x{usb["vendor"]},productid=0x{usb["product"]}'])

    # Audio
    if request.audio_enabled:
        if request.audio_device == 'intel-hda':
            cmd.extend(['-device', 'intel-hda', '-device', 'hda-duplex'])
        elif request.audio_device == 'ac97':
            cmd.extend(['-device', 'AC97'])
        elif request.audio_device == 'es1370':
            cmd.extend(['-device', 'ES1370'])

    # Serial port
    if request.serial_enabled:
        cmd.extend(['-serial', request.serial_device])

    # Parallel port
    if request.parallel_enabled:
        cmd.extend(['-parallel', 'pty'])

    # TPM (for Windows 11)
    if request.tpm_enabled:
        # Use swtpm (software TPM) - must be running separately or use emulator
        tpm_dir = tempfile.mkdtemp(prefix='tpm_')
        cmd.extend(['-chardev', f'socket,id=chrtpm,path={tpm_dir}/swtpm-sock'])
        cmd.extend(['-tpmdev', f'emulator,id=tpm0,chardev=chrtpm'])
        if request.tpm_version == '2.0':
            cmd.extend(['-device', 'tpm-tis,tpmdev=tpm0'])
        else:
            cmd.extend(['-device', 'tpm-tis,tpmdev=tpm0'])

    # SMBIOS
    smbios_opts = []
    if request.smbios_manufacturer:
        smbios_opts.append(f'manufacturer={request.smbios_manufacturer}')
    if request.smbios_product:
        smbios_opts.append(f'product={request.smbios_product}')
    if request.smbios_version:
        smbios_opts.append(f'version={request.smbios_version}')
    if request.smbios_serial:
        smbios_opts.append(f'serial={request.smbios_serial}')
    if request.smbios_uuid:
        smbios_opts.append(f'uuid={request.smbios_uuid}')
    if smbios_opts:
        cmd.extend(['-smbios', 'type=1,' + ','.join(smbios_opts)])

    # RTC
    cmd.extend(['-rtc', f'base={request.rtc_base}'])

    # Shutdown/reboot behavior
    if request.no_shutdown:
        cmd.append('-no-shutdown')
    if request.no_reboot:
        cmd.append('-no-reboot')

    # PCI passthrough
    if request.pci_passthrough:
        for pci in request.pci_passthrough:
            cmd.extend(['-device', f'vfio-pci,host={pci}'])

    # Shared folders (9p virtfs)
    if request.shared_folders:
        for i, share in enumerate(request.shared_folders):
            fsdev_id = f'fsdev{i}'
            cmd.extend(['-fsdev', f'local,security_model=passthrough,id={fsdev_id},path={share["host_path"]}'])
            cmd.extend(['-device', f'virtio-9p-pci,fsdev={fsdev_id},mount_tag={share["mount_tag"]}'])

    # Extra arguments
    if request.extra_args:
        cmd.extend(request.extra_args)

    return cmd


@router.post("/start", response_model=Dict[str, Any])
async def start_installation_vm(request: InstallVMCreate):
    """
    Start a VM in installation mode with an ISO attached.

    The VM will be accessible via VNC for interactive OS installation.
    A websockify proxy is started for noVNC browser access.
    """
    global next_install_vm_id

    try:
        # Validate paths
        disk_path = Path(os.path.expanduser(request.disk_image))

        if not disk_path.exists():
            raise HTTPException(status_code=404, detail=f"Disk image not found: {request.disk_image}")

        iso_path = None
        if request.iso_path:
            iso_path = Path(os.path.expanduser(request.iso_path))
            if not iso_path.exists():
                raise HTTPException(status_code=404, detail=f"ISO not found: {request.iso_path}")

        # Find free ports
        vnc_port = find_free_port(5900, 5999)
        vnc_display = vnc_port - 5900
        monitor_port = find_free_port(4444, 4500)
        vnc_ws_port = find_free_port(6080, 6100)
        spice_port = None
        if request.display == 'spice':
            spice_port = find_free_port(5930, 5999)

        # Build QEMU command
        cmd = build_qemu_command(request, disk_path, iso_path, vnc_display, monitor_port, spice_port)

        # Start QEMU process
        logger.info(f"Starting installation VM: {' '.join(cmd)}")

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True
        )

        # Wait a moment for QEMU to start
        time.sleep(1)

        # Check if process started successfully
        if process.poll() is not None:
            stderr = process.stderr.read().decode() if process.stderr else ""
            raise HTTPException(
                status_code=500,
                detail=f"Failed to start QEMU: {stderr}"
            )

        # Start websockify for noVNC access
        websockify_process = None
        try:
            websockify_cmd = [
                'websockify',
                '--web', '/usr/share/novnc',  # Path to noVNC files
                str(vnc_ws_port),
                f'127.0.0.1:{vnc_port}'
            ]

            # Try to start websockify
            websockify_process = subprocess.Popen(
                websockify_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True
            )
            time.sleep(0.5)

            if websockify_process.poll() is not None:
                logger.warning("websockify not available, noVNC will not work")
                websockify_process = None
        except Exception as e:
            logger.warning(f"Could not start websockify: {e}")
            websockify_process = None

        # Register the VM
        vm_id = next_install_vm_id
        next_install_vm_id += 1

        installation_vms[vm_id] = {
            "pid": process.pid,
            "process": process,
            "websockify_pid": websockify_process.pid if websockify_process else None,
            "websockify_process": websockify_process,
            "disk_image": str(disk_path),
            "iso_path": str(iso_path) if iso_path else None,
            "arch": request.arch,
            "memory": request.memory,
            "cpu_cores": request.cpu_cores,
            "vnc_port": vnc_port,
            "vnc_display": vnc_display,
            "vnc_ws_port": vnc_ws_port if websockify_process else None,
            "spice_port": spice_port,
            "monitor_port": monitor_port,
            "started_at": datetime.now().isoformat(),
            "start_time": time.time(),
            "boot_order": request.boot_order,
            "uefi": request.uefi,
            "enable_kvm": request.enable_kvm,
            "config": request.model_dump()  # Store full config
        }

        logger.info(f"Installation VM {vm_id} started (PID: {process.pid})")

        # Save configuration to JSON file if requested
        saved_config_id = None
        saved_config_path = None
        if request.save_config:
            try:
                import json
                import re
                from uuid import uuid4

                # Generate config ID
                config_id = str(uuid4())[:8]
                now = datetime.now().isoformat()

                # Generate config name if not provided
                if request.config_name:
                    config_name = request.config_name
                else:
                    # Auto-generate name from disk image
                    disk_name = disk_path.stem
                    config_name = f"{disk_name} ({request.arch})"

                # Build config to save
                config_data = request.model_dump()
                # Remove config-saving fields from the saved config
                config_data.pop("save_config", None)
                config_data.pop("config_name", None)
                config_data.pop("config_description", None)
                config_data.pop("config_tags", None)

                vm_config = {
                    "id": config_id,
                    "version": "1.0",
                    "name": config_name,
                    "description": request.config_description or f"VM configuration for {disk_path.name}",
                    "created_at": now,
                    "updated_at": now,
                    "tags": request.config_tags or [],
                    **config_data
                }

                # Save to vm_configs directory
                safe_name = re.sub(r'[^\w\-.]', '_', config_name)[:64].strip('_') or "unnamed"
                filename = f"{safe_name}_{config_id}.json"
                config_path = paths.vm_configs_dir / filename

                with open(config_path, 'w') as f:
                    json.dump(vm_config, f, indent=2, default=str)

                saved_config_id = config_id
                saved_config_path = str(config_path)
                logger.info(f"VM configuration saved: {filename}")

            except Exception as e:
                logger.warning(f"Failed to save VM configuration: {e}")

        return {
            "success": True,
            "message": "Installation VM started successfully",
            "data": {
                "vm_id": vm_id,
                "pid": process.pid,
                "vnc_port": vnc_port,
                "vnc_display": vnc_display,
                "vnc_websocket_port": vnc_ws_port if websockify_process else None,
                "vnc_url": f"vnc://127.0.0.1:{vnc_port}",
                "novnc_url": f"http://127.0.0.1:{vnc_ws_port}/vnc.html?host=127.0.0.1&port={vnc_ws_port}" if websockify_process else None,
                "monitor_port": monitor_port,
                "disk_image": str(disk_path),
                "iso_path": str(iso_path),
                "config_id": saved_config_id,
                "config_path": saved_config_path
            },
            "instructions": [
                f"Connect via VNC client to 127.0.0.1:{vnc_port}",
                f"Or use noVNC at http://<server-ip>:{vnc_ws_port}/vnc.html" if websockify_process else "Install websockify for browser VNC access",
                "Install your operating system from the ISO",
                "When installation is complete, use the 'Create Snapshot' button",
                "The snapshot will be usable for fuzzing"
            ]
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting installation VM: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{vm_id}", response_model=Dict[str, Any])
async def get_installation_vm(vm_id: int):
    """
    Get status of an installation VM.
    """
    try:
        if vm_id not in installation_vms:
            raise HTTPException(status_code=404, detail=f"Installation VM {vm_id} not found")

        vm_info = installation_vms[vm_id]
        pid = vm_info.get("pid")

        # Check if process is still running
        is_running = False
        if pid:
            try:
                os.kill(pid, 0)
                is_running = True
            except OSError:
                is_running = False

        return {
            "success": True,
            "data": {
                "vm_id": vm_id,
                "pid": pid,
                "status": "running" if is_running else "stopped",
                "disk_image": vm_info.get("disk_image"),
                "iso_path": vm_info.get("iso_path"),
                "arch": vm_info.get("arch"),
                "memory": vm_info.get("memory"),
                "vnc_port": vm_info.get("vnc_port"),
                "vnc_display": vm_info.get("vnc_display"),
                "vnc_websocket_port": vm_info.get("vnc_ws_port"),
                "monitor_port": vm_info.get("monitor_port"),
                "started_at": vm_info.get("started_at"),
                "uptime_seconds": int(time.time() - vm_info.get("start_time", time.time())),
                "can_create_snapshot": is_running
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting installation VM {vm_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{vm_id}/snapshot", response_model=Dict[str, Any])
async def create_vm_snapshot(vm_id: int, request: SnapshotCreateRequest):
    """
    Create a snapshot of the running installation VM.

    This creates a snapshot with VM state, which is required for fuzzing.
    The VM will briefly pause during snapshot creation.
    """
    try:
        if vm_id not in installation_vms:
            raise HTTPException(status_code=404, detail=f"Installation VM {vm_id} not found")

        vm_info = installation_vms[vm_id]
        monitor_port = vm_info.get("monitor_port")
        pid = vm_info.get("pid")

        # Check if VM is running
        try:
            os.kill(pid, 0)
        except OSError:
            raise HTTPException(status_code=400, detail="VM is not running")

        # Connect to QEMU monitor and create snapshot
        logger.info(f"Creating snapshot '{request.name}' for VM {vm_id}")

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(30)
                s.connect(('127.0.0.1', monitor_port))

                # Read initial prompt
                s.recv(4096)

                # Send savevm command
                cmd = f"savevm {request.name}\n"
                s.send(cmd.encode())

                # Wait for completion
                time.sleep(2)
                response = s.recv(4096).decode()

                if 'error' in response.lower():
                    raise HTTPException(
                        status_code=500,
                        detail=f"Failed to create snapshot: {response}"
                    )

        except socket.error as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to connect to QEMU monitor: {e}"
            )

        logger.info(f"Snapshot '{request.name}' created for VM {vm_id}")

        return {
            "success": True,
            "message": f"Snapshot '{request.name}' created successfully",
            "data": {
                "vm_id": vm_id,
                "snapshot_name": request.name,
                "disk_image": vm_info.get("disk_image"),
                "has_vm_state": True
            },
            "next_steps": [
                "The snapshot includes VM memory state and is ready for fuzzing",
                "You can now stop the VM and use this disk image for fuzzing jobs",
                f"When creating a job, use snapshot name: {request.name}"
            ]
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating snapshot for VM {vm_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{vm_id}/stop", response_model=Dict[str, Any])
async def stop_installation_vm(vm_id: int):
    """
    Stop an installation VM.

    Sends ACPI shutdown first, then forces termination if needed.
    """
    try:
        if vm_id not in installation_vms:
            raise HTTPException(status_code=404, detail=f"Installation VM {vm_id} not found")

        vm_info = installation_vms[vm_id]
        pid = vm_info.get("pid")
        monitor_port = vm_info.get("monitor_port")

        # Try graceful shutdown via monitor
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(5)
                s.connect(('127.0.0.1', monitor_port))
                s.recv(4096)  # Read prompt
                s.send(b"quit\n")
                time.sleep(1)
        except:
            pass

        # Check if still running
        try:
            os.kill(pid, 0)
            # Still running, force kill
            os.kill(pid, signal.SIGTERM)
            time.sleep(1)
            try:
                os.kill(pid, 0)
                # Still running, SIGKILL
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
        except OSError:
            pass

        # Stop websockify if running
        websockify_pid = vm_info.get("websockify_pid")
        if websockify_pid:
            try:
                os.kill(websockify_pid, signal.SIGTERM)
            except OSError:
                pass

        # Remove from tracking
        del installation_vms[vm_id]

        logger.info(f"Installation VM {vm_id} stopped")

        return {
            "success": True,
            "message": f"Installation VM {vm_id} stopped",
            "data": {
                "vm_id": vm_id,
                "disk_image": vm_info.get("disk_image")
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error stopping installation VM {vm_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{vm_id}/eject-iso", response_model=Dict[str, Any])
async def eject_iso(vm_id: int):
    """
    Eject the ISO from the running VM.

    Use this after OS installation is complete to boot from hard disk.
    """
    try:
        if vm_id not in installation_vms:
            raise HTTPException(status_code=404, detail=f"Installation VM {vm_id} not found")

        vm_info = installation_vms[vm_id]
        monitor_port = vm_info.get("monitor_port")

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(10)
                s.connect(('127.0.0.1', monitor_port))
                s.recv(4096)  # Read prompt
                s.send(b"eject -f ide1-cd0\n")
                time.sleep(0.5)
                response = s.recv(4096).decode()

        except socket.error as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to connect to QEMU monitor: {e}"
            )

        logger.info(f"ISO ejected from VM {vm_id}")

        return {
            "success": True,
            "message": "ISO ejected successfully",
            "data": {"vm_id": vm_id}
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error ejecting ISO from VM {vm_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{vm_id}/reset", response_model=Dict[str, Any])
async def reset_vm(vm_id: int):
    """
    Reset/reboot the VM.
    """
    try:
        if vm_id not in installation_vms:
            raise HTTPException(status_code=404, detail=f"Installation VM {vm_id} not found")

        vm_info = installation_vms[vm_id]
        monitor_port = vm_info.get("monitor_port")

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(10)
                s.connect(('127.0.0.1', monitor_port))
                s.recv(4096)  # Read prompt
                s.send(b"system_reset\n")
                time.sleep(0.5)

        except socket.error as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to connect to QEMU monitor: {e}"
            )

        logger.info(f"VM {vm_id} reset")

        return {
            "success": True,
            "message": "VM reset successfully",
            "data": {"vm_id": vm_id}
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resetting VM {vm_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{vm_id}/sendkey", response_model=Dict[str, Any])
async def send_key(vm_id: int, keys: str):
    """
    Send key combination to the VM.

    Args:
        keys: Key combination (e.g., "ctrl-alt-delete", "ret" for Enter)
    """
    try:
        if vm_id not in installation_vms:
            raise HTTPException(status_code=404, detail=f"Installation VM {vm_id} not found")

        vm_info = installation_vms[vm_id]
        monitor_port = vm_info.get("monitor_port")

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(10)
                s.connect(('127.0.0.1', monitor_port))
                s.recv(4096)  # Read prompt
                s.send(f"sendkey {keys}\n".encode())
                time.sleep(0.2)

        except socket.error as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to connect to QEMU monitor: {e}"
            )

        return {
            "success": True,
            "message": f"Keys '{keys}' sent to VM",
            "data": {"vm_id": vm_id}
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending keys to VM {vm_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
