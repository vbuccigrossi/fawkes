"""
Architecture Detection API endpoints.

Lists supported CPU architectures and checks QEMU availability.
"""

import logging
import shutil
import subprocess
from typing import Dict, Any, List

from fastapi import APIRouter, HTTPException

from api.models.vm_setup import ArchitectureInfo, ArchitectureCheck

router = APIRouter()
logger = logging.getLogger("fawkes.web.api.architectures")


# Define all supported architectures
ARCHITECTURES = {
    # x86 Family
    "i386": {
        "display_name": "x86 32-bit (i386)",
        "qemu_binary": "qemu-system-i386",
        "gdb_arch": "i386",
        "word_size": 32,
        "endianness": "little",
        "family": "x86"
    },
    "x86_64": {
        "display_name": "x86 64-bit (AMD64)",
        "qemu_binary": "qemu-system-x86_64",
        "gdb_arch": "i386:x86-64",
        "word_size": 64,
        "endianness": "little",
        "family": "x86"
    },
    # ARM Family
    "arm": {
        "display_name": "ARM 32-bit",
        "qemu_binary": "qemu-system-arm",
        "gdb_arch": "arm",
        "word_size": 32,
        "endianness": "little",
        "family": "arm"
    },
    "aarch64": {
        "display_name": "ARM 64-bit (AArch64)",
        "qemu_binary": "qemu-system-aarch64",
        "gdb_arch": "aarch64",
        "word_size": 64,
        "endianness": "little",
        "family": "arm"
    },
    # MIPS Family
    "mips": {
        "display_name": "MIPS 32-bit (Big Endian)",
        "qemu_binary": "qemu-system-mips",
        "gdb_arch": "mips",
        "word_size": 32,
        "endianness": "big",
        "family": "mips"
    },
    "mipsel": {
        "display_name": "MIPS 32-bit (Little Endian)",
        "qemu_binary": "qemu-system-mipsel",
        "gdb_arch": "mips",
        "word_size": 32,
        "endianness": "little",
        "family": "mips"
    },
    "mips64": {
        "display_name": "MIPS 64-bit (Big Endian)",
        "qemu_binary": "qemu-system-mips64",
        "gdb_arch": "mips64",
        "word_size": 64,
        "endianness": "big",
        "family": "mips"
    },
    "mips64el": {
        "display_name": "MIPS 64-bit (Little Endian)",
        "qemu_binary": "qemu-system-mips64el",
        "gdb_arch": "mips64",
        "word_size": 64,
        "endianness": "little",
        "family": "mips"
    },
    # PowerPC Family
    "ppc": {
        "display_name": "PowerPC 32-bit",
        "qemu_binary": "qemu-system-ppc",
        "gdb_arch": "powerpc:common",
        "word_size": 32,
        "endianness": "big",
        "family": "ppc"
    },
    "ppc64": {
        "display_name": "PowerPC 64-bit",
        "qemu_binary": "qemu-system-ppc64",
        "gdb_arch": "powerpc:common64",
        "word_size": 64,
        "endianness": "big",
        "family": "ppc"
    },
    # RISC-V Family
    "riscv32": {
        "display_name": "RISC-V 32-bit",
        "qemu_binary": "qemu-system-riscv32",
        "gdb_arch": "riscv:rv32",
        "word_size": 32,
        "endianness": "little",
        "family": "riscv"
    },
    "riscv64": {
        "display_name": "RISC-V 64-bit",
        "qemu_binary": "qemu-system-riscv64",
        "gdb_arch": "riscv:rv64",
        "word_size": 64,
        "endianness": "little",
        "family": "riscv"
    },
    # SPARC Family
    "sparc": {
        "display_name": "SPARC 32-bit",
        "qemu_binary": "qemu-system-sparc",
        "gdb_arch": "sparc",
        "word_size": 32,
        "endianness": "big",
        "family": "sparc"
    },
    "sparc64": {
        "display_name": "SPARC 64-bit",
        "qemu_binary": "qemu-system-sparc64",
        "gdb_arch": "sparc:v9",
        "word_size": 64,
        "endianness": "big",
        "family": "sparc"
    },
    # S390 (IBM Z)
    "s390x": {
        "display_name": "IBM Z (s390x)",
        "qemu_binary": "qemu-system-s390x",
        "gdb_arch": "s390:64-bit",
        "word_size": 64,
        "endianness": "big",
        "family": "s390"
    },
}


def check_qemu_binary(binary: str) -> tuple[bool, str]:
    """Check if a QEMU binary exists and get its version."""
    path = shutil.which(binary)
    if not path:
        return False, None

    try:
        result = subprocess.run(
            [path, '--version'],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            # Parse version from first line
            first_line = result.stdout.split('\n')[0]
            # Typical output: "QEMU emulator version 8.0.0"
            if 'version' in first_line.lower():
                parts = first_line.split('version')
                if len(parts) > 1:
                    return True, parts[1].strip().split()[0]
            return True, "unknown"
    except Exception:
        pass

    return True, None


@router.get("/", response_model=Dict[str, Any])
async def list_architectures():
    """
    List all supported CPU architectures.

    Returns architecture info including QEMU binary availability.
    """
    try:
        architectures: List[ArchitectureInfo] = []

        for name, info in ARCHITECTURES.items():
            available, version = check_qemu_binary(info["qemu_binary"])
            architectures.append(ArchitectureInfo(
                name=name,
                display_name=info["display_name"],
                qemu_binary=info["qemu_binary"],
                gdb_arch=info["gdb_arch"],
                word_size=info["word_size"],
                endianness=info["endianness"],
                available=available,
                family=info["family"]
            ))

        # Sort by family, then by word size (64-bit first)
        architectures.sort(key=lambda x: (x.family, -x.word_size))

        # Count available
        available_count = sum(1 for a in architectures if a.available)

        return {
            "success": True,
            "total": len(architectures),
            "available": available_count,
            "data": [arch.model_dump() for arch in architectures]
        }
    except Exception as e:
        logger.error(f"Error listing architectures: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/families", response_model=Dict[str, Any])
async def list_architecture_families():
    """
    List architecture families grouped together.

    Returns architectures grouped by family (x86, arm, mips, etc.)
    """
    try:
        families: Dict[str, List[ArchitectureInfo]] = {}

        for name, info in ARCHITECTURES.items():
            available, version = check_qemu_binary(info["qemu_binary"])
            arch = ArchitectureInfo(
                name=name,
                display_name=info["display_name"],
                qemu_binary=info["qemu_binary"],
                gdb_arch=info["gdb_arch"],
                word_size=info["word_size"],
                endianness=info["endianness"],
                available=available,
                family=info["family"]
            )

            family = info["family"]
            if family not in families:
                families[family] = []
            families[family].append(arch)

        # Sort each family by word size (64-bit first)
        for family in families:
            families[family].sort(key=lambda x: -x.word_size)

        return {
            "success": True,
            "families": list(families.keys()),
            "data": {
                family: [arch.model_dump() for arch in archs]
                for family, archs in families.items()
            }
        }
    except Exception as e:
        logger.error(f"Error listing architecture families: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/kvm/check", response_model=Dict[str, Any])
async def check_kvm_support():
    """
    Check if KVM hardware virtualization is available.

    KVM provides significant performance improvements for x86 VMs.
    """
    try:
        kvm_available = False
        kvm_usable = False
        error_message = None

        # Check if /dev/kvm exists
        import os
        if os.path.exists('/dev/kvm'):
            kvm_available = True

            # Check if we can access it
            if os.access('/dev/kvm', os.R_OK | os.W_OK):
                kvm_usable = True
            else:
                error_message = "KVM device exists but not accessible. Add user to 'kvm' group."
        else:
            error_message = "KVM not available. Enable VT-x/AMD-V in BIOS or run in a supported environment."

        return {
            "success": True,
            "data": {
                "kvm_available": kvm_available,
                "kvm_usable": kvm_usable,
                "error_message": error_message,
                "recommendation": "KVM provides 10-100x performance improvement for x86/x86_64 VMs"
                                if not kvm_usable else "KVM is available and will be used automatically"
            }
        }
    except Exception as e:
        logger.error(f"Error checking KVM support: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{arch}", response_model=Dict[str, Any])
async def get_architecture(arch: str):
    """
    Get details for a specific architecture.

    Args:
        arch: Architecture name (e.g., x86_64, aarch64)
    """
    try:
        if arch not in ARCHITECTURES:
            raise HTTPException(
                status_code=404,
                detail=f"Unknown architecture: {arch}. "
                       f"Supported: {', '.join(ARCHITECTURES.keys())}"
            )

        info = ARCHITECTURES[arch]
        available, version = check_qemu_binary(info["qemu_binary"])

        architecture = ArchitectureInfo(
            name=arch,
            display_name=info["display_name"],
            qemu_binary=info["qemu_binary"],
            gdb_arch=info["gdb_arch"],
            word_size=info["word_size"],
            endianness=info["endianness"],
            available=available,
            family=info["family"]
        )

        return {
            "success": True,
            "data": architecture.model_dump(),
            "qemu_version": version
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting architecture {arch}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{arch}/check", response_model=Dict[str, Any])
async def check_architecture(arch: str):
    """
    Check if an architecture's QEMU binary is available.

    Args:
        arch: Architecture name
    """
    try:
        if arch not in ARCHITECTURES:
            raise HTTPException(
                status_code=404,
                detail=f"Unknown architecture: {arch}"
            )

        info = ARCHITECTURES[arch]
        binary = info["qemu_binary"]
        available, version = check_qemu_binary(binary)

        check = ArchitectureCheck(
            arch=arch,
            available=available,
            qemu_binary=binary,
            qemu_version=version,
            error_message=None if available else f"QEMU binary '{binary}' not found in PATH"
        )

        return {
            "success": True,
            "data": check.model_dump()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking architecture {arch}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
