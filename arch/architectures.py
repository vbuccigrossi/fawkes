"""
Multi-Architecture Support for Fawkes

Comprehensive support for all QEMU architectures with register definitions,
GDB architectures, and architecture-specific configurations.
"""

from enum import Enum
from typing import Dict, List, Optional, Any
from dataclasses import dataclass


@dataclass
class RegisterSet:
    """Architecture-specific register definitions"""
    program_counter: str  # PC/RIP/EIP
    stack_pointer: str    # SP/RSP/ESP
    frame_pointer: str    # FP/RBP/EBP
    return_register: str  # Return value register
    general_purpose: List[str]  # List of general purpose registers
    arguments: List[str]  # Argument passing registers (for calling conventions)


@dataclass
class ArchitectureInfo:
    """Complete architecture information"""
    name: str
    qemu_binary: str
    gdb_arch: str
    word_size: int  # in bits (32, 64, etc.)
    endianness: str  # "little" or "big"
    registers: RegisterSet
    aliases: List[str] = None  # Alternative names
    description: str = ""


class SupportedArchitectures:
    """
    Comprehensive QEMU architecture support

    Supports all 38+ architectures available in QEMU 10.0.0
    """

    ARCHITECTURES: Dict[str, ArchitectureInfo] = {
        # x86 Family
        "i386": ArchitectureInfo(
            name="i386",
            qemu_binary="qemu-system-i386",
            gdb_arch="i386",
            word_size=32,
            endianness="little",
            registers=RegisterSet(
                program_counter="eip",
                stack_pointer="esp",
                frame_pointer="ebp",
                return_register="eax",
                general_purpose=["eax", "ebx", "ecx", "edx", "esi", "edi"],
                arguments=["eax", "edx", "ecx"]  # cdecl / fastcall varies
            ),
            aliases=["x86", "ia32"],
            description="32-bit x86 architecture"
        ),

        "x86_64": ArchitectureInfo(
            name="x86_64",
            qemu_binary="qemu-system-x86_64",
            gdb_arch="i386:x86-64",
            word_size=64,
            endianness="little",
            registers=RegisterSet(
                program_counter="rip",
                stack_pointer="rsp",
                frame_pointer="rbp",
                return_register="rax",
                general_purpose=["rax", "rbx", "rcx", "rdx", "rsi", "rdi", "r8", "r9", "r10", "r11", "r12", "r13", "r14", "r15"],
                arguments=["rdi", "rsi", "rdx", "rcx", "r8", "r9"]  # System V ABI
            ),
            aliases=["amd64", "x64"],
            description="64-bit x86 architecture"
        ),

        # ARM Family
        "arm": ArchitectureInfo(
            name="arm",
            qemu_binary="qemu-system-arm",
            gdb_arch="arm",
            word_size=32,
            endianness="little",
            registers=RegisterSet(
                program_counter="pc",
                stack_pointer="sp",
                frame_pointer="r11",
                return_register="r0",
                general_purpose=["r0", "r1", "r2", "r3", "r4", "r5", "r6", "r7", "r8", "r9", "r10", "r11", "r12"],
                arguments=["r0", "r1", "r2", "r3"]  # AAPCS
            ),
            aliases=["armv7", "armhf", "armel"],
            description="32-bit ARM architecture"
        ),

        "aarch64": ArchitectureInfo(
            name="aarch64",
            qemu_binary="qemu-system-aarch64",
            gdb_arch="aarch64",
            word_size=64,
            endianness="little",
            registers=RegisterSet(
                program_counter="pc",
                stack_pointer="sp",
                frame_pointer="x29",
                return_register="x0",
                general_purpose=[f"x{i}" for i in range(31)],
                arguments=["x0", "x1", "x2", "x3", "x4", "x5", "x6", "x7"]
            ),
            aliases=["arm64"],
            description="64-bit ARM architecture (ARMv8)"
        ),

        # MIPS Family
        "mips": ArchitectureInfo(
            name="mips",
            qemu_binary="qemu-system-mips",
            gdb_arch="mips",
            word_size=32,
            endianness="big",
            registers=RegisterSet(
                program_counter="pc",
                stack_pointer="sp",
                frame_pointer="fp",
                return_register="v0",
                general_purpose=["zero", "at", "v0", "v1", "a0", "a1", "a2", "a3",
                               "t0", "t1", "t2", "t3", "t4", "t5", "t6", "t7",
                               "s0", "s1", "s2", "s3", "s4", "s5", "s6", "s7",
                               "t8", "t9", "k0", "k1", "gp", "sp", "fp", "ra"],
                arguments=["a0", "a1", "a2", "a3"]
            ),
            description="32-bit MIPS big-endian"
        ),

        "mipsel": ArchitectureInfo(
            name="mipsel",
            qemu_binary="qemu-system-mipsel",
            gdb_arch="mips",
            word_size=32,
            endianness="little",
            registers=RegisterSet(
                program_counter="pc",
                stack_pointer="sp",
                frame_pointer="fp",
                return_register="v0",
                general_purpose=["zero", "at", "v0", "v1", "a0", "a1", "a2", "a3",
                               "t0", "t1", "t2", "t3", "t4", "t5", "t6", "t7",
                               "s0", "s1", "s2", "s3", "s4", "s5", "s6", "s7",
                               "t8", "t9", "k0", "k1", "gp", "sp", "fp", "ra"],
                arguments=["a0", "a1", "a2", "a3"]
            ),
            description="32-bit MIPS little-endian"
        ),

        "mips64": ArchitectureInfo(
            name="mips64",
            qemu_binary="qemu-system-mips64",
            gdb_arch="mips:isa64",
            word_size=64,
            endianness="big",
            registers=RegisterSet(
                program_counter="pc",
                stack_pointer="sp",
                frame_pointer="fp",
                return_register="v0",
                general_purpose=["zero", "at", "v0", "v1", "a0", "a1", "a2", "a3",
                               "a4", "a5", "a6", "a7", "t0", "t1", "t2", "t3",
                               "s0", "s1", "s2", "s3", "s4", "s5", "s6", "s7",
                               "t8", "t9", "k0", "k1", "gp", "sp", "fp", "ra"],
                arguments=["a0", "a1", "a2", "a3", "a4", "a5", "a6", "a7"]
            ),
            description="64-bit MIPS big-endian"
        ),

        "mips64el": ArchitectureInfo(
            name="mips64el",
            qemu_binary="qemu-system-mips64el",
            gdb_arch="mips:isa64",
            word_size=64,
            endianness="little",
            registers=RegisterSet(
                program_counter="pc",
                stack_pointer="sp",
                frame_pointer="fp",
                return_register="v0",
                general_purpose=["zero", "at", "v0", "v1", "a0", "a1", "a2", "a3",
                               "a4", "a5", "a6", "a7", "t0", "t1", "t2", "t3",
                               "s0", "s1", "s2", "s3", "s4", "s5", "s6", "s7",
                               "t8", "t9", "k0", "k1", "gp", "sp", "fp", "ra"],
                arguments=["a0", "a1", "a2", "a3", "a4", "a5", "a6", "a7"]
            ),
            description="64-bit MIPS little-endian"
        ),

        # PowerPC Family
        "ppc": ArchitectureInfo(
            name="ppc",
            qemu_binary="qemu-system-ppc",
            gdb_arch="powerpc:common",
            word_size=32,
            endianness="big",
            registers=RegisterSet(
                program_counter="pc",
                stack_pointer="r1",
                frame_pointer="r31",
                return_register="r3",
                general_purpose=[f"r{i}" for i in range(32)],
                arguments=["r3", "r4", "r5", "r6", "r7", "r8", "r9", "r10"]
            ),
            aliases=["powerpc"],
            description="32-bit PowerPC"
        ),

        "ppc64": ArchitectureInfo(
            name="ppc64",
            qemu_binary="qemu-system-ppc64",
            gdb_arch="powerpc:common64",
            word_size=64,
            endianness="big",
            registers=RegisterSet(
                program_counter="pc",
                stack_pointer="r1",
                frame_pointer="r31",
                return_register="r3",
                general_purpose=[f"r{i}" for i in range(32)],
                arguments=["r3", "r4", "r5", "r6", "r7", "r8", "r9", "r10"]
            ),
            aliases=["powerpc64"],
            description="64-bit PowerPC big-endian"
        ),

        "ppc64le": ArchitectureInfo(
            name="ppc64le",
            qemu_binary="qemu-system-ppc64",
            gdb_arch="powerpc:common64",
            word_size=64,
            endianness="little",
            registers=RegisterSet(
                program_counter="pc",
                stack_pointer="r1",
                frame_pointer="r31",
                return_register="r3",
                general_purpose=[f"r{i}" for i in range(32)],
                arguments=["r3", "r4", "r5", "r6", "r7", "r8", "r9", "r10"]
            ),
            aliases=["powerpc64le", "ppc64el"],
            description="64-bit PowerPC little-endian"
        ),

        # RISC-V Family
        "riscv32": ArchitectureInfo(
            name="riscv32",
            qemu_binary="qemu-system-riscv32",
            gdb_arch="riscv:rv32",
            word_size=32,
            endianness="little",
            registers=RegisterSet(
                program_counter="pc",
                stack_pointer="sp",
                frame_pointer="fp",
                return_register="a0",
                general_purpose=["zero", "ra", "sp", "gp", "tp", "t0", "t1", "t2",
                               "fp", "s1", "a0", "a1", "a2", "a3", "a4", "a5",
                               "a6", "a7", "s2", "s3", "s4", "s5", "s6", "s7",
                               "s8", "s9", "s10", "s11", "t3", "t4", "t5", "t6"],
                arguments=["a0", "a1", "a2", "a3", "a4", "a5", "a6", "a7"]
            ),
            aliases=["rv32"],
            description="32-bit RISC-V"
        ),

        "riscv64": ArchitectureInfo(
            name="riscv64",
            qemu_binary="qemu-system-riscv64",
            gdb_arch="riscv:rv64",
            word_size=64,
            endianness="little",
            registers=RegisterSet(
                program_counter="pc",
                stack_pointer="sp",
                frame_pointer="fp",
                return_register="a0",
                general_purpose=["zero", "ra", "sp", "gp", "tp", "t0", "t1", "t2",
                               "fp", "s1", "a0", "a1", "a2", "a3", "a4", "a5",
                               "a6", "a7", "s2", "s3", "s4", "s5", "s6", "s7",
                               "s8", "s9", "s10", "s11", "t3", "t4", "t5", "t6"],
                arguments=["a0", "a1", "a2", "a3", "a4", "a5", "a6", "a7"]
            ),
            aliases=["rv64"],
            description="64-bit RISC-V"
        ),

        # SPARC Family
        "sparc": ArchitectureInfo(
            name="sparc",
            qemu_binary="qemu-system-sparc",
            gdb_arch="sparc",
            word_size=32,
            endianness="big",
            registers=RegisterSet(
                program_counter="pc",
                stack_pointer="sp",
                frame_pointer="fp",
                return_register="o0",
                general_purpose=[f"g{i}" for i in range(8)] + [f"o{i}" for i in range(8)] +
                               [f"l{i}" for i in range(8)] + [f"i{i}" for i in range(8)],
                arguments=["o0", "o1", "o2", "o3", "o4", "o5"]
            ),
            description="32-bit SPARC"
        ),

        "sparc64": ArchitectureInfo(
            name="sparc64",
            qemu_binary="qemu-system-sparc64",
            gdb_arch="sparc:v9",
            word_size=64,
            endianness="big",
            registers=RegisterSet(
                program_counter="pc",
                stack_pointer="sp",
                frame_pointer="fp",
                return_register="o0",
                general_purpose=[f"g{i}" for i in range(8)] + [f"o{i}" for i in range(8)] +
                               [f"l{i}" for i in range(8)] + [f"i{i}" for i in range(8)],
                arguments=["o0", "o1", "o2", "o3", "o4", "o5"]
            ),
            description="64-bit SPARC v9"
        ),

        # S390X (IBM z/Architecture)
        "s390x": ArchitectureInfo(
            name="s390x",
            qemu_binary="qemu-system-s390x",
            gdb_arch="s390:64-bit",
            word_size=64,
            endianness="big",
            registers=RegisterSet(
                program_counter="psw_addr",
                stack_pointer="r15",
                frame_pointer="r11",
                return_register="r2",
                general_purpose=[f"r{i}" for i in range(16)],
                arguments=["r2", "r3", "r4", "r5", "r6"]
            ),
            aliases=["s390", "z/Architecture"],
            description="IBM z/Architecture (s390x)"
        ),

        # Alpha
        "alpha": ArchitectureInfo(
            name="alpha",
            qemu_binary="qemu-system-alpha",
            gdb_arch="alpha",
            word_size=64,
            endianness="little",
            registers=RegisterSet(
                program_counter="pc",
                stack_pointer="sp",
                frame_pointer="fp",
                return_register="v0",
                general_purpose=[f"${i}" for i in range(32)],
                arguments=["$16", "$17", "$18", "$19", "$20", "$21"]
            ),
            description="DEC Alpha 64-bit"
        ),

        # HPPA (PA-RISC)
        "hppa": ArchitectureInfo(
            name="hppa",
            qemu_binary="qemu-system-hppa",
            gdb_arch="hppa",
            word_size=32,
            endianness="big",
            registers=RegisterSet(
                program_counter="pc",
                stack_pointer="r30",
                frame_pointer="r3",
                return_register="r28",
                general_purpose=[f"r{i}" for i in range(32)],
                arguments=["r26", "r25", "r24", "r23"]
            ),
            aliases=["parisc"],
            description="HP PA-RISC"
        ),

        # M68K (Motorola 68000)
        "m68k": ArchitectureInfo(
            name="m68k",
            qemu_binary="qemu-system-m68k",
            gdb_arch="m68k",
            word_size=32,
            endianness="big",
            registers=RegisterSet(
                program_counter="pc",
                stack_pointer="a7",
                frame_pointer="a6",
                return_register="d0",
                general_purpose=[f"d{i}" for i in range(8)] + [f"a{i}" for i in range(7)],
                arguments=["d0", "d1", "a0", "a1"]
            ),
            description="Motorola 68000 family"
        ),

        # SH4 (SuperH)
        "sh4": ArchitectureInfo(
            name="sh4",
            qemu_binary="qemu-system-sh4",
            gdb_arch="sh",
            word_size=32,
            endianness="little",
            registers=RegisterSet(
                program_counter="pc",
                stack_pointer="r15",
                frame_pointer="r14",
                return_register="r0",
                general_purpose=[f"r{i}" for i in range(16)],
                arguments=["r4", "r5", "r6", "r7"]
            ),
            description="SuperH SH-4 little-endian"
        ),

        "sh4eb": ArchitectureInfo(
            name="sh4eb",
            qemu_binary="qemu-system-sh4eb",
            gdb_arch="sh",
            word_size=32,
            endianness="big",
            registers=RegisterSet(
                program_counter="pc",
                stack_pointer="r15",
                frame_pointer="r14",
                return_register="r0",
                general_purpose=[f"r{i}" for i in range(16)],
                arguments=["r4", "r5", "r6", "r7"]
            ),
            description="SuperH SH-4 big-endian"
        ),

        # MicroBlaze
        "microblaze": ArchitectureInfo(
            name="microblaze",
            qemu_binary="qemu-system-microblaze",
            gdb_arch="microblaze",
            word_size=32,
            endianness="big",
            registers=RegisterSet(
                program_counter="pc",
                stack_pointer="r1",
                frame_pointer="r19",
                return_register="r3",
                general_purpose=[f"r{i}" for i in range(32)],
                arguments=["r5", "r6", "r7", "r8", "r9", "r10"]
            ),
            description="Xilinx MicroBlaze big-endian"
        ),

        "microblazeel": ArchitectureInfo(
            name="microblazeel",
            qemu_binary="qemu-system-microblazeel",
            gdb_arch="microblaze",
            word_size=32,
            endianness="little",
            registers=RegisterSet(
                program_counter="pc",
                stack_pointer="r1",
                frame_pointer="r19",
                return_register="r3",
                general_purpose=[f"r{i}" for i in range(32)],
                arguments=["r5", "r6", "r7", "r8", "r9", "r10"]
            ),
            description="Xilinx MicroBlaze little-endian"
        ),

        # LoongArch
        "loongarch64": ArchitectureInfo(
            name="loongarch64",
            qemu_binary="qemu-system-loongarch64",
            gdb_arch="loongarch64",
            word_size=64,
            endianness="little",
            registers=RegisterSet(
                program_counter="pc",
                stack_pointer="r3",
                frame_pointer="r22",
                return_register="r4",
                general_purpose=[f"r{i}" for i in range(32)],
                arguments=["r4", "r5", "r6", "r7", "r8", "r9", "r10", "r11"]
            ),
            aliases=["loong64"],
            description="LoongArch 64-bit"
        ),

        # OpenRISC
        "or1k": ArchitectureInfo(
            name="or1k",
            qemu_binary="qemu-system-or1k",
            gdb_arch="or1k",
            word_size=32,
            endianness="big",
            registers=RegisterSet(
                program_counter="pc",
                stack_pointer="r1",
                frame_pointer="r2",
                return_register="r11",
                general_purpose=[f"r{i}" for i in range(32)],
                arguments=["r3", "r4", "r5", "r6", "r7", "r8"]
            ),
            aliases=["openrisc"],
            description="OpenRISC 1000"
        ),

        # Xtensa
        "xtensa": ArchitectureInfo(
            name="xtensa",
            qemu_binary="qemu-system-xtensa",
            gdb_arch="xtensa",
            word_size=32,
            endianness="little",
            registers=RegisterSet(
                program_counter="pc",
                stack_pointer="a1",
                frame_pointer="a15",
                return_register="a2",
                general_purpose=[f"a{i}" for i in range(16)],
                arguments=["a2", "a3", "a4", "a5", "a6", "a7"]
            ),
            description="Xtensa little-endian"
        ),

        "xtensaeb": ArchitectureInfo(
            name="xtensaeb",
            qemu_binary="qemu-system-xtensaeb",
            gdb_arch="xtensa",
            word_size=32,
            endianness="big",
            registers=RegisterSet(
                program_counter="pc",
                stack_pointer="a1",
                frame_pointer="a15",
                return_register="a2",
                general_purpose=[f"a{i}" for i in range(16)],
                arguments=["a2", "a3", "a4", "a5", "a6", "a7"]
            ),
            description="Xtensa big-endian"
        ),

        # TriCore
        "tricore": ArchitectureInfo(
            name="tricore",
            qemu_binary="qemu-system-tricore",
            gdb_arch="tricore",
            word_size=32,
            endianness="little",
            registers=RegisterSet(
                program_counter="pc",
                stack_pointer="a10",
                frame_pointer="a11",
                return_register="d2",
                general_purpose=[f"d{i}" for i in range(16)] + [f"a{i}" for i in range(16)],
                arguments=["d4", "d5", "d6", "d7"]
            ),
            description="Infineon TriCore"
        ),

        # AVR
        "avr": ArchitectureInfo(
            name="avr",
            qemu_binary="qemu-system-avr",
            gdb_arch="avr",
            word_size=8,
            endianness="little",
            registers=RegisterSet(
                program_counter="pc",
                stack_pointer="sp",
                frame_pointer="y",
                return_register="r24",
                general_purpose=[f"r{i}" for i in range(32)],
                arguments=["r24", "r22", "r20", "r18", "r16", "r14"]
            ),
            description="Atmel AVR 8-bit microcontroller"
        ),

        # RX (Renesas)
        "rx": ArchitectureInfo(
            name="rx",
            qemu_binary="qemu-system-rx",
            gdb_arch="rx",
            word_size=32,
            endianness="little",
            registers=RegisterSet(
                program_counter="pc",
                stack_pointer="r0",
                frame_pointer="r13",
                return_register="r1",
                general_purpose=[f"r{i}" for i in range(16)],
                arguments=["r1", "r2", "r3", "r4"]
            ),
            description="Renesas RX"
        ),
    }

    @classmethod
    def get_architecture(cls, name: str) -> Optional[ArchitectureInfo]:
        """Get architecture by name or alias"""
        # Direct lookup
        if name in cls.ARCHITECTURES:
            return cls.ARCHITECTURES[name]

        # Check aliases
        for arch_name, arch_info in cls.ARCHITECTURES.items():
            if arch_info.aliases and name in arch_info.aliases:
                return arch_info

        return None

    @classmethod
    def list_architectures(cls) -> List[str]:
        """List all supported architecture names"""
        return sorted(cls.ARCHITECTURES.keys())

    @classmethod
    def get_qemu_binary(cls, arch: str) -> Optional[str]:
        """Get QEMU binary name for architecture"""
        arch_info = cls.get_architecture(arch)
        return arch_info.qemu_binary if arch_info else None

    @classmethod
    def get_gdb_arch(cls, arch: str) -> Optional[str]:
        """Get GDB architecture string for architecture"""
        arch_info = cls.get_architecture(arch)
        return arch_info.gdb_arch if arch_info else None

    @classmethod
    def get_register_set(cls, arch: str) -> Optional[RegisterSet]:
        """Get register set for architecture"""
        arch_info = cls.get_architecture(arch)
        return arch_info.registers if arch_info else None

    @classmethod
    def validate_architecture(cls, arch: str) -> bool:
        """Validate if architecture is supported"""
        return cls.get_architecture(arch) is not None

    @classmethod
    def get_architecture_families(cls) -> Dict[str, List[str]]:
        """Group architectures by family"""
        families = {
            "x86": ["i386", "x86_64"],
            "ARM": ["arm", "aarch64"],
            "MIPS": ["mips", "mipsel", "mips64", "mips64el"],
            "PowerPC": ["ppc", "ppc64", "ppc64le"],
            "RISC-V": ["riscv32", "riscv64"],
            "SPARC": ["sparc", "sparc64"],
            "IBM": ["s390x"],
            "Embedded": ["avr", "rx", "tricore", "microblaze", "microblazeel"],
            "Legacy": ["alpha", "hppa", "m68k", "sh4", "sh4eb"],
            "Exotic": ["or1k", "xtensa", "xtensaeb", "loongarch64"]
        }
        return families
