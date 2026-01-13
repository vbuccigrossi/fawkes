"""
VM Runner API Routes.

Provides endpoints for running VMs in preparation mode (for agent installation and snapshot creation).
Handles file uploads to shared folder and crash agent deployment.
"""

import os
import json
import shutil
import subprocess
import socket
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel, Field

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from paths import paths

router = APIRouter()

# Track running preparation VMs
running_prep_vms: Dict[str, Dict[str, Any]] = {}


def get_agents_dir() -> Path:
    """Get the agents directory."""
    return Path(__file__).parent.parent.parent.parent / "agents"


def get_free_port() -> int:
    """Get a free port for VNC."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]


def is_kvm_available() -> bool:
    """Check if KVM is available and accessible."""
    kvm_path = Path("/dev/kvm")
    if not kvm_path.exists():
        return False
    # Check if we have read/write access
    return os.access(kvm_path, os.R_OK | os.W_OK)


def get_shared_folder_for_config(config_id: str) -> Path:
    """Get or create the shared folder for a VM config."""
    shared_base = paths.shared_dir / config_id
    shared_base.mkdir(parents=True, exist_ok=True)

    # Create subdirectories
    (shared_base / "agents").mkdir(exist_ok=True)
    (shared_base / "uploads").mkdir(exist_ok=True)
    (shared_base / "crashes").mkdir(exist_ok=True)

    return shared_base


def copy_agents_to_shared(shared_folder: Path, target_os: str = "both") -> Dict[str, Any]:
    """Copy crash agents to the shared folder."""
    agents_dir = get_agents_dir()
    agents_dest = shared_folder / "agents"
    agents_dest.mkdir(parents=True, exist_ok=True)

    copied = []
    errors = []

    # Files to copy based on target OS
    agent_files = {
        "windows": [
            ("FawkesCrashAgentWindows.exe", "FawkesCrashAgent.exe"),
            ("FawkesCrashAgent-Windows.cpp", "FawkesCrashAgent-Windows.cpp"),
        ],
        "linux": [
            ("LinuxCrashAgent.cpp", "LinuxCrashAgent.cpp"),
            ("fawkes-agent.service", "fawkes-agent.service"),
        ],
    }

    # Also copy a README for the user
    readme_content = """# Fawkes Crash Agent Installation

## Windows Installation

1. Copy `FawkesCrashAgent.exe` to a location on the Windows VM (e.g., C:\\Fawkes\\)
2. Run the agent as Administrator
3. The agent will:
   - Mount the shared folder as Z: drive
   - Configure Windows Error Reporting to capture crashes
   - Start listening on port 9999 for crash queries

To run at startup, add to Task Scheduler or create a service.

## Linux Installation

1. Compile the agent:
   ```bash
   g++ -o fawkes-agent LinuxCrashAgent.cpp -lpthread
   ```

2. Install the agent:
   ```bash
   sudo cp fawkes-agent /usr/local/bin/
   sudo cp fawkes-agent.service /etc/systemd/system/
   sudo systemctl enable fawkes-agent
   sudo systemctl start fawkes-agent
   ```

3. Mount the shared folder:
   ```bash
   sudo mkdir -p /mnt/virtfs
   sudo mount -t 9p -o trans=virtio hostshare /mnt/virtfs
   ```

   Add to /etc/fstab for permanent mount:
   ```
   hostshare /mnt/virtfs 9p trans=virtio,version=9p2000.L 0 0
   ```

## Verification

After installation, the agent listens on port 9999. You can test:
```
nc localhost 9999
```

It should return JSON with crash status.

## Creating a Fuzzing-Ready Snapshot

1. Install the crash agent
2. Install any target software you want to fuzz
3. Configure the system (disable updates, screensaver, etc.)
4. Return to the VM Runner page and click "Create Snapshot"
"""

    # Write README
    readme_path = agents_dest / "README.md"
    readme_path.write_text(readme_content)
    copied.append("README.md")

    # Copy agent files
    os_list = ["windows", "linux"] if target_os == "both" else [target_os]

    for os_name in os_list:
        for src_name, dest_name in agent_files.get(os_name, []):
            src_path = agents_dir / src_name
            dest_path = agents_dest / dest_name

            if src_path.exists():
                try:
                    shutil.copy2(src_path, dest_path)
                    copied.append(dest_name)
                except Exception as e:
                    errors.append(f"{src_name}: {str(e)}")
            else:
                errors.append(f"{src_name}: File not found")

    return {
        "copied": copied,
        "errors": errors,
        "agents_path": str(agents_dest),
    }


class PrepVMStart(BaseModel):
    """Request to start a preparation VM."""
    config_id: str = Field(..., description="VM config ID to use")
    memory: Optional[str] = Field(None, description="Override memory (e.g., '4G')")
    cpu_cores: Optional[int] = Field(None, description="Override CPU cores")
    enable_kvm: bool = Field(default=True, description="Enable KVM acceleration")
    copy_agents: bool = Field(default=True, description="Copy crash agents to shared folder")
    target_os: str = Field(default="both", description="Target OS for agents: 'windows', 'linux', or 'both'")


class SnapshotCreate(BaseModel):
    """Request to create a snapshot."""
    vm_id: str = Field(..., description="Running VM ID")
    snapshot_name: str = Field(..., description="Name for the snapshot")
    update_config: bool = Field(default=True, description="Update the VM config with snapshot name")


@router.get("/")
async def list_running_prep_vms():
    """List all running preparation VMs."""
    # Clean up any dead VMs
    dead_vms = []
    for vm_id, vm_info in running_prep_vms.items():
        pid = vm_info.get("pid")
        if pid:
            try:
                os.kill(pid, 0)  # Check if process exists
            except OSError:
                dead_vms.append(vm_id)

    for vm_id in dead_vms:
        running_prep_vms[vm_id]["status"] = "stopped"

    # Return VMs without the process object (not JSON serializable)
    vms_data = []
    for vm_info in running_prep_vms.values():
        vm_copy = {k: v for k, v in vm_info.items() if k != "process"}
        vms_data.append(vm_copy)

    return {
        "success": True,
        "count": len(running_prep_vms),
        "data": vms_data,
    }


@router.post("/start")
async def start_prep_vm(request: PrepVMStart):
    """Start a VM for preparation (agent installation, snapshot creation)."""
    # Load the VM config
    config_path = None
    config_data = None

    for f in paths.vm_configs_dir.iterdir():
        if f.suffix == ".json" and request.config_id in f.name:
            config_path = f
            break

    if not config_path or not config_path.exists():
        raise HTTPException(status_code=404, detail=f"VM config '{request.config_id}' not found")

    with open(config_path) as f:
        config_data = json.load(f)

    # Check disk image exists
    disk_image = config_data.get("disk_image")
    if not disk_image or not Path(disk_image).exists():
        raise HTTPException(status_code=400, detail=f"Disk image not found: {disk_image}")

    # Set up shared folder
    shared_folder = get_shared_folder_for_config(request.config_id)

    # Copy agents if requested
    agents_result = None
    if request.copy_agents:
        agents_result = copy_agents_to_shared(shared_folder, request.target_os)

    # Get free ports
    vnc_port = get_free_port()
    agent_port = get_free_port()

    # Build QEMU command
    memory = request.memory or config_data.get("memory", "4G")
    cpu_cores = request.cpu_cores or config_data.get("cpu_cores", 2)
    arch = config_data.get("arch", "x86_64")

    qemu_binary = f"qemu-system-{arch}"

    cmd = [
        qemu_binary,
        "-m", memory,
        "-smp", str(cpu_cores),
        "-hda", disk_image,
        "-vnc", f":{vnc_port - 5900}",
        "-monitor", "stdio",
    ]

    # KVM acceleration - only enable if available and requested
    kvm_enabled = False
    if request.enable_kvm and config_data.get("enable_kvm", True):
        if is_kvm_available():
            cmd.extend(["-enable-kvm", "-cpu", "host"])
            kvm_enabled = True
        else:
            # Log warning but continue without KVM
            import logging
            logging.getLogger("fawkes.web").warning(
                "KVM requested but not available (permission denied or /dev/kvm missing). "
                "Running without KVM acceleration. Add user to 'kvm' group for better performance."
            )

    # Display settings
    vga = config_data.get("vga", "std")
    cmd.extend(["-vga", vga])

    # USB tablet for better mouse
    if config_data.get("usb_tablet", True):
        cmd.extend(["-usb", "-device", "usb-tablet"])

    # Network with SMB share and port forwarding
    cmd.extend([
        "-net", "nic,model=virtio",
        "-net", f"user,smb={shared_folder},hostfwd=tcp::{agent_port}-:9999",
    ])

    # VirtFS for Linux guests
    cmd.extend([
        "-virtfs", f"local,path={shared_folder},mount_tag=hostshare,security_model=none",
    ])

    # Machine type
    machine_type = config_data.get("machine_type", "")
    if machine_type:
        cmd.extend(["-machine", machine_type])
    elif arch == "x86_64":
        cmd.extend(["-machine", "q35"])

    # UEFI if specified
    if config_data.get("uefi"):
        ovmf_paths = [
            "/usr/share/OVMF/OVMF_CODE.fd",
            "/usr/share/edk2/ovmf/OVMF_CODE.fd",
            "/usr/share/qemu/OVMF_CODE.fd",
        ]
        for ovmf in ovmf_paths:
            if Path(ovmf).exists():
                cmd.extend(["-bios", ovmf])
                break

    # Start the VM
    vm_id = f"prep_{request.config_id}_{datetime.now().strftime('%H%M%S')}"

    try:
        # Start QEMU process
        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )

        # Store VM info
        running_prep_vms[vm_id] = {
            "vm_id": vm_id,
            "config_id": request.config_id,
            "config_name": config_data.get("name", "Unknown"),
            "pid": process.pid,
            "vnc_port": vnc_port,
            "agent_port": agent_port,
            "shared_folder": str(shared_folder),
            "disk_image": disk_image,
            "status": "running",
            "started_at": datetime.now().isoformat(),
            "memory": memory,
            "cpu_cores": cpu_cores,
            "process": process,  # Keep reference
        }

        return {
            "success": True,
            "message": "Preparation VM started" + (" (without KVM - may be slow)" if not kvm_enabled else ""),
            "data": {
                "vm_id": vm_id,
                "vnc_port": vnc_port,
                "vnc_display": vnc_port - 5900,
                "agent_port": agent_port,
                "shared_folder": str(shared_folder),
                "agents_copied": agents_result,
                "pid": process.pid,
                "kvm_enabled": kvm_enabled,
            },
            "instructions": {
                "vnc": f"Connect via VNC to localhost:{vnc_port}",
                "shared_folder_windows": "Access shared folder via \\\\10.0.2.4\\qemu or Z: drive (after agent runs)",
                "shared_folder_linux": "Mount with: sudo mount -t 9p -o trans=virtio hostshare /mnt/virtfs",
                "agents": f"Crash agents are in the 'agents' subfolder of the shared folder",
            },
        }

    except FileNotFoundError:
        raise HTTPException(status_code=500, detail=f"QEMU binary '{qemu_binary}' not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start VM: {str(e)}")


@router.get("/{vm_id}")
async def get_prep_vm(vm_id: str):
    """Get status of a preparation VM."""
    if vm_id not in running_prep_vms:
        raise HTTPException(status_code=404, detail="VM not found")

    vm_info = running_prep_vms[vm_id].copy()
    vm_info.pop("process", None)  # Don't serialize process object

    # Check if still running
    pid = vm_info.get("pid")
    if pid:
        try:
            os.kill(pid, 0)
            vm_info["status"] = "running"
        except OSError:
            vm_info["status"] = "stopped"

    return {"success": True, "data": vm_info}


@router.post("/{vm_id}/stop")
async def stop_prep_vm(vm_id: str):
    """Stop a preparation VM."""
    if vm_id not in running_prep_vms:
        raise HTTPException(status_code=404, detail="VM not found")

    vm_info = running_prep_vms[vm_id]
    process = vm_info.get("process")
    pid = vm_info.get("pid")

    try:
        if process:
            # Try graceful shutdown first via QEMU monitor
            try:
                process.stdin.write(b"system_powerdown\n")
                process.stdin.flush()
                process.wait(timeout=10)
            except:
                process.terminate()
                process.wait(timeout=5)
        elif pid:
            os.kill(pid, 15)  # SIGTERM
    except Exception as e:
        # Force kill
        try:
            if pid:
                os.kill(pid, 9)  # SIGKILL
        except:
            pass

    vm_info["status"] = "stopped"

    return {"success": True, "message": "VM stopped"}


@router.post("/{vm_id}/snapshot")
async def create_snapshot(vm_id: str, request: SnapshotCreate):
    """Create a snapshot of the running VM."""
    if vm_id not in running_prep_vms:
        raise HTTPException(status_code=404, detail="VM not found")

    vm_info = running_prep_vms[vm_id]
    process = vm_info.get("process")
    disk_image = vm_info.get("disk_image")

    if not process:
        raise HTTPException(status_code=400, detail="VM process not available")

    # Check VM is running
    try:
        os.kill(vm_info.get("pid"), 0)
    except OSError:
        raise HTTPException(status_code=400, detail="VM is not running")

    try:
        # Send savevm command to QEMU monitor
        snapshot_cmd = f"savevm {request.snapshot_name}\n"
        process.stdin.write(snapshot_cmd.encode())
        process.stdin.flush()

        # Wait a moment for snapshot to complete
        import time
        time.sleep(2)

        # Verify snapshot was created using qemu-img
        result = subprocess.run(
            ["qemu-img", "snapshot", "-l", disk_image],
            capture_output=True,
            text=True,
        )

        snapshot_created = request.snapshot_name in result.stdout

        # Update config if requested
        if request.update_config and snapshot_created:
            config_id = vm_info.get("config_id")
            for f in paths.vm_configs_dir.iterdir():
                if f.suffix == ".json" and config_id in f.name:
                    with open(f) as cf:
                        config = json.load(cf)
                    config["snapshot_name"] = request.snapshot_name
                    config["updated_at"] = datetime.now().isoformat()
                    with open(f, "w") as cf:
                        json.dump(config, cf, indent=2)
                    break

        return {
            "success": snapshot_created,
            "message": f"Snapshot '{request.snapshot_name}' created" if snapshot_created else "Snapshot creation may have failed",
            "data": {
                "snapshot_name": request.snapshot_name,
                "disk_image": disk_image,
                "config_updated": request.update_config and snapshot_created,
            },
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create snapshot: {str(e)}")


@router.get("/{vm_id}/shared")
async def list_shared_folder(vm_id: str, subpath: str = ""):
    """List contents of the shared folder."""
    if vm_id not in running_prep_vms:
        raise HTTPException(status_code=404, detail="VM not found")

    shared_folder = Path(running_prep_vms[vm_id]["shared_folder"])
    target_path = shared_folder / subpath

    if not target_path.exists():
        raise HTTPException(status_code=404, detail="Path not found")

    if not target_path.is_dir():
        raise HTTPException(status_code=400, detail="Path is not a directory")

    # Ensure we're still within shared folder
    try:
        target_path.resolve().relative_to(shared_folder.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")

    items = []
    for item in sorted(target_path.iterdir()):
        stat = item.stat()
        items.append({
            "name": item.name,
            "path": str(item.relative_to(shared_folder)),
            "is_dir": item.is_dir(),
            "size": stat.st_size if item.is_file() else None,
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        })

    return {
        "success": True,
        "path": subpath or "/",
        "data": items,
    }


@router.post("/{vm_id}/upload")
async def upload_to_shared(
    vm_id: str,
    file: UploadFile = File(...),
    subpath: str = Form(default="uploads"),
):
    """Upload a file to the shared folder."""
    if vm_id not in running_prep_vms:
        raise HTTPException(status_code=404, detail="VM not found")

    shared_folder = Path(running_prep_vms[vm_id]["shared_folder"])
    target_dir = shared_folder / subpath
    target_dir.mkdir(parents=True, exist_ok=True)

    # Ensure we're still within shared folder
    try:
        target_dir.resolve().relative_to(shared_folder.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")

    target_path = target_dir / file.filename

    try:
        with open(target_path, "wb") as f:
            content = await file.read()
            f.write(content)

        return {
            "success": True,
            "message": f"File uploaded: {file.filename}",
            "data": {
                "filename": file.filename,
                "path": str(target_path.relative_to(shared_folder)),
                "size": len(content),
                "full_path": str(target_path),
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.delete("/{vm_id}/shared/{filepath:path}")
async def delete_from_shared(vm_id: str, filepath: str):
    """Delete a file from the shared folder."""
    if vm_id not in running_prep_vms:
        raise HTTPException(status_code=404, detail="VM not found")

    shared_folder = Path(running_prep_vms[vm_id]["shared_folder"])
    target_path = shared_folder / filepath

    # Ensure we're still within shared folder
    try:
        target_path.resolve().relative_to(shared_folder.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")

    if not target_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    # Don't allow deleting the agents folder
    if "agents" in target_path.parts and target_path.parent.name == "agents":
        pass  # Allow deleting files in agents folder
    elif target_path.name == "agents":
        raise HTTPException(status_code=403, detail="Cannot delete agents folder")

    try:
        if target_path.is_dir():
            shutil.rmtree(target_path)
        else:
            target_path.unlink()

        return {"success": True, "message": f"Deleted: {filepath}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Delete failed: {str(e)}")


@router.get("/agents/list")
async def list_available_agents():
    """List available crash agents."""
    agents_dir = get_agents_dir()

    agents = []

    # Check for Windows agent
    win_agent = agents_dir / "FawkesCrashAgentWindows.exe"
    if win_agent.exists():
        agents.append({
            "name": "Windows Crash Agent",
            "filename": "FawkesCrashAgentWindows.exe",
            "platform": "windows",
            "size": win_agent.stat().st_size,
            "exists": True,
        })
    else:
        agents.append({
            "name": "Windows Crash Agent",
            "filename": "FawkesCrashAgentWindows.exe",
            "platform": "windows",
            "exists": False,
            "note": "Compile FawkesCrashAgent-Windows.cpp on Windows",
        })

    # Check for Linux agent source
    linux_src = agents_dir / "LinuxCrashAgent.cpp"
    linux_service = agents_dir / "fawkes-agent.service"
    agents.append({
        "name": "Linux Crash Agent",
        "filename": "LinuxCrashAgent.cpp",
        "platform": "linux",
        "exists": linux_src.exists(),
        "service_exists": linux_service.exists(),
        "note": "Compile inside Linux VM with: g++ -o fawkes-agent LinuxCrashAgent.cpp -lpthread",
    })

    return {
        "success": True,
        "agents_directory": str(agents_dir),
        "data": agents,
    }


@router.post("/agents/copy/{config_id}")
async def copy_agents_to_config(config_id: str, target_os: str = "both"):
    """Copy crash agents to a config's shared folder."""
    shared_folder = get_shared_folder_for_config(config_id)
    result = copy_agents_to_shared(shared_folder, target_os)

    return {
        "success": len(result["errors"]) == 0,
        "message": f"Copied {len(result['copied'])} agent files",
        "data": result,
    }


@router.post("/stop-all")
async def stop_all_prep_vms():
    """Stop all running preparation VMs."""
    stopped = []
    failed = []

    for vm_id, vm_info in list(running_prep_vms.items()):
        if vm_info.get("status") == "stopped":
            continue

        process = vm_info.get("process")
        pid = vm_info.get("pid")

        try:
            if process:
                # Try graceful shutdown first via QEMU monitor
                try:
                    process.stdin.write(b"system_powerdown\n")
                    process.stdin.flush()
                    process.wait(timeout=5)
                except:
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except:
                        process.kill()
            elif pid:
                os.kill(pid, 15)  # SIGTERM

            vm_info["status"] = "stopped"
            stopped.append(vm_id)
        except Exception as e:
            # Force kill
            try:
                if pid:
                    os.kill(pid, 9)  # SIGKILL
                vm_info["status"] = "stopped"
                stopped.append(vm_id)
            except:
                failed.append({"vm_id": vm_id, "error": str(e)})

    return {
        "success": len(failed) == 0,
        "message": f"Stopped {len(stopped)} VM(s)",
        "data": {
            "stopped": stopped,
            "failed": failed,
        },
    }


@router.post("/clear-stopped")
async def clear_stopped_prep_vms():
    """Remove stopped VMs from the list."""
    # First, update statuses for any VMs with dead processes
    for vm_id, vm_info in list(running_prep_vms.items()):
        pid = vm_info.get("pid")
        if pid:
            try:
                os.kill(pid, 0)  # Check if process exists
            except OSError:
                vm_info["status"] = "stopped"

    # Find and remove stopped VMs
    removed = []
    for vm_id in list(running_prep_vms.keys()):
        if running_prep_vms[vm_id].get("status") == "stopped":
            removed.append(vm_id)
            del running_prep_vms[vm_id]

    return {
        "success": True,
        "message": f"Cleared {len(removed)} stopped VM(s)",
        "data": {
            "removed": removed,
            "remaining": len(running_prep_vms),
        },
    }
