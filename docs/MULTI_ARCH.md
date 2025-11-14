# Fawkes Multi-Architecture Support

Comprehensive support for all QEMU architectures - from x86 to exotic embedded processors.

## Supported Architectures

Fawkes supports **28 different architectures** across 9 architecture families, covering everything QEMU emulates:

### x86 Family (2 architectures)
- **i386** - 32-bit x86 architecture
- **x86_64** - 64-bit x86 architecture (AMD64)

### ARM Family (2 architectures)
- **arm** - 32-bit ARM architecture (ARMv7, ARMhf, ARMel)
- **aarch64** - 64-bit ARM architecture (ARMv8, ARM64)

### MIPS Family (4 architectures)
- **mips** - 32-bit MIPS big-endian
- **mipsel** - 32-bit MIPS little-endian
- **mips64** - 64-bit MIPS big-endian
- **mips64el** - 64-bit MIPS little-endian

### PowerPC Family (3 architectures)
- **ppc** - 32-bit PowerPC big-endian
- **ppc64** - 64-bit PowerPC big-endian
- **ppc64le** - 64-bit PowerPC little-endian

### RISC-V Family (2 architectures)
- **riscv32** - 32-bit RISC-V
- **riscv64** - 64-bit RISC-V

### SPARC Family (2 architectures)
- **sparc** - 32-bit SPARC
- **sparc64** - 64-bit SPARC v9

### IBM Mainframe (1 architecture)
- **s390x** - IBM z/Architecture (s390x)

### Embedded/Legacy (7 architectures)
- **alpha** - DEC Alpha 64-bit
- **hppa** - HP PA-RISC
- **m68k** - Motorola 68000 family
- **sh4** / **sh4eb** - SuperH SH-4 (little/big endian)
- **microblaze** / **microblazeel** - Xilinx MicroBlaze (big/little endian)
- **avr** - Atmel AVR 8-bit microcontroller
- **rx** - Renesas RX
- **tricore** - Infineon TriCore

### Exotic (4 architectures)
- **or1k** - OpenRISC 1000
- **xtensa** / **xtensaeb** - Xtensa (little/big endian)
- **loongarch64** - LoongArch 64-bit

---

## Quick Start

### Using Specific Architectures

Simply set the `arch` parameter in your configuration:

```json
{
  "arch": "aarch64",
  "disk_image": "~/vms/ubuntu-arm64.qcow2",
  "snapshot_name": "clean"
}
```

Fawkes automatically:
- Selects the correct QEMU binary (`qemu-system-aarch64`)
- Configures GDB with the right architecture (`aarch64`)
- Uses architecture-specific register sets for crash analysis

### Architecture CLI Tool

```bash
# List all supported architectures
./fawkes-arch list

# Get detailed info about an architecture
./fawkes-arch info riscv64

# Validate architecture support
./fawkes-arch validate ppc64le

# List architecture families
./fawkes-arch families

# Detect architecture from QEMU binary
./fawkes-arch detect qemu-system-m68k
```

---

## Architecture Information

### Viewing Architecture Details

```bash
$ ./fawkes-arch info x86_64
```

```
================================================================================
ARCHITECTURE: x86_64
================================================================================

Description: 64-bit x86 architecture
Word Size: 64-bit
Endianness: little-endian
QEMU Binary: qemu-system-x86_64
GDB Architecture: i386:x86-64
Aliases: amd64, x64

Registers:
  Program Counter: rip
  Stack Pointer: rsp
  Frame Pointer: rbp
  Return Register: rax

General Purpose Registers (16):
  rax        rbx        rcx        rdx        rsi        rdi        r8         r9
  r10        r11        r12        r13        r14        r15

Argument Registers:
  rdi, rsi, rdx, rcx, r8, r9

================================================================================
```

### Listing by Family

```bash
# List all ARM architectures
./fawkes-arch list --family ARM

# List all embedded architectures
./fawkes-arch list --family Embedded
```

---

## Configuration Examples

### ARM64 Android Device

```json
{
  "arch": "aarch64",
  "disk_image": "~/vms/android-arm64.qcow2",
  "snapshot_name": "clean",
  "memory": "2G",
  "vm_params": "-cpu cortex-a57"
}
```

### MIPS Router Firmware

```json
{
  "arch": "mipsel",
  "disk_image": "~/vms/openwrt-mipsel.qcow2",
  "snapshot_name": "boot",
  "memory": "512M",
  "vm_params": "-M malta"
}
```

### PowerPC Big-Endian Linux

```json
{
  "arch": "ppc64",
  "disk_image": "~/vms/debian-ppc64.qcow2",
  "snapshot_name": "ready",
  "memory": "4G",
  "vm_params": "-M pseries"
}
```

### RISC-V System

```json
{
  "arch": "riscv64",
  "disk_image": "~/vms/fedora-riscv64.qcow2",
  "snapshot_name": "clean",
  "memory": "2G",
  "vm_params": "-M virt"
}
```

### Embedded AVR Microcontroller

```json
{
  "arch": "avr",
  "disk_image": "~/vms/arduino-firmware.qcow2",
  "snapshot_name": "init",
  "memory": "32K",
  "vm_params": "-M arduino-mega"
}
```

---

## Register Sets and Calling Conventions

Each architecture has complete register set definitions including:

- **Program Counter**: Where execution is happening (PC/RIP/EIP)
- **Stack Pointer**: Current stack position (SP/RSP/ESP)
- **Frame Pointer**: Stack frame base (FP/RBP/EBP)
- **Return Register**: Function return value (RAX/R0/V0)
- **General Purpose Registers**: All available GPRs
- **Argument Registers**: Function calling convention registers

### Examples:

**x86_64 (System V ABI)**:
- Arguments: `rdi, rsi, rdx, rcx, r8, r9`
- Return: `rax`

**ARM (AAPCS)**:
- Arguments: `r0, r1, r2, r3`
- Return: `r0`

**AArch64 (AAPCS64)**:
- Arguments: `x0, x1, x2, x3, x4, x5, x6, x7`
- Return: `x0`

**MIPS**:
- Arguments: `a0, a1, a2, a3`
- Return: `v0`

**PowerPC**:
- Arguments: `r3, r4, r5, r6, r7, r8, r9, r10`
- Return: `r3`

**RISC-V**:
- Arguments: `a0, a1, a2, a3, a4, a5, a6, a7`
- Return: `a0`

---

## GDB Integration

Each architecture has the correct GDB architecture string pre-configured:

| Fawkes Arch | GDB Architecture String |
|-------------|------------------------|
| i386 | `i386` |
| x86_64 | `i386:x86-64` |
| arm | `arm` |
| aarch64 | `aarch64` |
| mips | `mips` |
| mips64 | `mips:isa64` |
| ppc | `powerpc:common` |
| ppc64 | `powerpc:common64` |
| riscv32 | `riscv:rv32` |
| riscv64 | `riscv:rv64` |
| sparc | `sparc` |
| sparc64 | `sparc:v9` |
| s390x | `s390:64-bit` |
| alpha | `alpha` |
| hppa | `hppa` |
| m68k | `m68k` |
| sh4 | `sh` |
| ... | ... |

GDB automatically uses the correct architecture when connecting to QEMU's debug stub.

---

## Crash Analysis per Architecture

The triage system understands architecture-specific crash patterns:

### x86/x86_64
- EIP/RIP control detection
- Stack smashing (EBP/RBP corruption)
- Return address overwrite
- SEH/VEH corruption (Windows)

### ARM/AArch64
- PC control detection
- Link register (LR) corruption
- Stack pointer corruption
- Exception vector table overwrites

### MIPS
- Program counter control
- Return address ($ra) corruption
- Stack pointer corruption
- Jump register exploitation

### PowerPC
- PC/LR corruption
- TOC (Table of Contents) manipulation
- Function descriptor hijacking

### RISC-V
- PC control detection
- Return address (ra) corruption
- Stack smashing via sp manipulation

---

## Architecture Aliases

Many architectures have common aliases that Fawkes recognizes:

| Canonical Name | Aliases |
|----------------|---------|
| x86_64 | amd64, x64 |
| i386 | x86, ia32 |
| aarch64 | arm64 |
| arm | armv7, armhf, armel |
| ppc | powerpc |
| ppc64 | powerpc64 |
| ppc64le | powerpc64le, ppc64el |
| riscv32 | rv32 |
| riscv64 | rv64 |
| s390x | s390, z/Architecture |
| hppa | parisc |
| or1k | openrisc |
| loongarch64 | loong64 |

You can use any alias in your configuration:

```json
{
  "arch": "amd64"  // Same as x86_64
}
```

---

## Validation

### Check Architecture Support

```bash
# Returns 0 if supported, 1 if not
./fawkes-arch validate arm64
echo $?  # 0

./fawkes-arch validate invalid_arch
echo $?  # 1
```

### Programmatic Validation

```python
from fawkes.arch.architectures import SupportedArchitectures

# Validate architecture
is_valid = SupportedArchitectures.validate_architecture("riscv64")

# Get architecture info
arch_info = SupportedArchitectures.get_architecture("aarch64")
if arch_info:
    print(f"QEMU Binary: {arch_info.qemu_binary}")
    print(f"Word Size: {arch_info.word_size}-bit")
    print(f"Endianness: {arch_info.endianness}")
```

---

## Endianness Support

Fawkes correctly handles both big-endian and little-endian architectures:

**Little-Endian**:
- x86, x86_64
- arm, aarch64
- riscv32, riscv64
- mipsel, mips64el
- ppc64le
- alpha
- sh4, microblazeel, xtensa
- loongarch64, tricore, rx, avr

**Big-Endian**:
- mips, mips64
- ppc, ppc64
- sparc, sparc64
- s390x
- hppa, m68k, sh4eb, microblaze, xtensaeb, or1k

---

## Adding Custom Architectures

If you need to add support for a custom or experimental architecture:

1. Edit `arch/architectures.py`
2. Add entry to `ARCHITECTURES` dict:

```python
"my_arch": ArchitectureInfo(
    name="my_arch",
    qemu_binary="qemu-system-my_arch",
    gdb_arch="my_arch",
    word_size=32,
    endianness="little",
    registers=RegisterSet(
        program_counter="pc",
        stack_pointer="sp",
        frame_pointer="fp",
        return_register="r0",
        general_purpose=["r0", "r1", "r2", ...],
        arguments=["r0", "r1", "r2", "r3"]
    ),
    description="My custom architecture"
)
```

3. Restart Fawkes

---

## Troubleshooting

### Architecture Not Found

```
Error: Unsupported architecture: armv8
Supported architectures: i386, x86_64, aarch64, arm, ...
```

**Solution**: Use the canonical name or a recognized alias:
```bash
# Check valid name
./fawkes-arch list | grep arm
# aarch64
# arm

# Use correct name
"arch": "aarch64"  # Not "armv8"
```

### QEMU Binary Not Found

```
Error: qemu-system-riscv64: command not found
```

**Solution**: Install QEMU package for that architecture:
```bash
# Debian/Ubuntu
sudo apt-get install qemu-system-misc  # For exotic archs
sudo apt-get install qemu-system-arm   # For ARM
sudo apt-get install qemu-system-mips  # For MIPS
# etc.
```

### GDB Architecture Mismatch

```
warning: Selected architecture i386 is not compatible with reported target architecture armv7
```

**Solution**: This is usually harmless. GDB will auto-detect. If issues persist, the architecture mapping may need adjustment.

---

## Performance Considerations

Different architectures have different performance characteristics in QEMU:

**Fast** (near-native speed):
- x86, x86_64 (on x86 hosts with KVM)
- aarch64 (on ARM hosts)

**Medium** (good emulation):
- arm, mips, ppc
- Most modern architectures with TCG

**Slower** (complex emulation):
- Exotic/embedded architectures
- Legacy architectures
- Uncommon endianness on common hosts

For large-scale fuzzing:
- Prefer x86_64 targets when possible
- Use native architecture with KVM when available
- Consider worker distribution across architecture types

---

## See Also

- [Architecture CLI](../fawkes-arch) - Command-line architecture tool
- [Architectures Module](../arch/architectures.py) - Complete architecture definitions
- [QEMU Manager](../qemu.py) - QEMU integration
- [GDB Worker](../gdb.py) - GDB debugging per architecture
