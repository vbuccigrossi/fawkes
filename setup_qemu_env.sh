#!/usr/bin/env bash
#
# Automates QEMU/KVM/GDB setup on a Debian/Ubuntu-based system.
# Installs required packages, creates a directory for your VM,
# and demonstrates how to create a QCOW2 disk image. 
# Also optionally installs Samba for a shared folder with Windows.

# --- ANSI Color Codes ---
GREEN="\e[32m"
RED="\e[31m"
YELLOW="\e[33m"
BLUE="\e[34m"
BOLD="\e[1m"
RESET="\e[0m"

function echo_info()    { echo -e "${BLUE}[INFO]${RESET} $1"; }
function echo_success() { echo -e "${GREEN}[SUCCESS]${RESET} $1"; }
function echo_warn()    { echo -e "${YELLOW}[WARNING]${RESET} $1"; }
function echo_error()   { echo -e "${RED}[ERROR]${RESET} $1"; }

# --- Check for root privileges ---
if [[ $EUID -ne 0 ]]; then
  echo_error "This script must be run as root (sudo). Exiting."
  exit 1
fi

echo_info "Updating package lists..."
apt-get update -y

# --- Install QEMU / KVM / GDB ---
PACKAGES=(
  qemu-kvm
  libvirt-daemon-system
  libvirt-clients
  bridge-utils
  virt-manager
  gdb
  python3  # Let's have Python3 if we plan to do some harnessing in Python
)

echo_info "Installing QEMU/KVM and related packages: ${PACKAGES[*]}"
apt-get install -y "${PACKAGES[@]}"
if [[ $? -ne 0 ]]; then
  echo_error "Failed to install all packages. Please check your apt sources or network."
  exit 1
fi

echo_success "QEMU/KVM and GDB successfully installed."

# --- Optional: Offer to install Samba for shared folders with Windows ---
echo_info "Would you like to install Samba for an easy shared folder with Windows? [y/N]"
read -r INSTALL_SAMBA
if [[ "$INSTALL_SAMBA" =~ ^[Yy]$ ]]; then
  apt-get install -y samba
  if [[ $? -ne 0 ]]; then
    echo_warn "Failed to install Samba. You can install it manually later if needed."
  else
    echo_success "Samba installed. You can configure /etc/samba/smb.conf for sharing."
    echo_info "Example share config:
    
    [shared]
    path = /path/to/host/shared_dir
    read only = no
    guest ok = yes
    force user = $(logname)

    Then run 'systemctl restart smbd' and connect from Windows using \\\\HOST_IP\\shared
    "
  fi
fi

# --- Create a directory for QEMU VM images (if not exists) ---
DEFAULT_VM_DIR="/var/lib/qemu_vms"
mkdir -p "$DEFAULT_VM_DIR"
chown "$(logname):$(logname)" "$DEFAULT_VM_DIR"

echo_info "We'll store VM disk images in: $DEFAULT_VM_DIR"
echo_info "Would you like to create a Windows QCOW2 disk now? [y/N]"
read -r CREATE_DISK
if [[ "$CREATE_DISK" =~ ^[Yy]$ ]]; then
  echo_info "Enter name for your Windows QCOW2 (e.g. windows.qcow2):"
  read -r DISK_NAME
  if [[ -z "$DISK_NAME" ]]; then
    DISK_NAME="windows.qcow2"
  fi
  echo_info "Enter size for disk in GB (e.g. 60):"
  read -r DISK_SIZE
  if [[ -z "$DISK_SIZE" ]]; then
    DISK_SIZE="60"
  fi

  FULL_PATH="$DEFAULT_VM_DIR/$DISK_NAME"
  echo_info "Creating $FULL_PATH with size ${DISK_SIZE}G..."
  sudo -u "$(logname)" qemu-img create -f qcow2 "$FULL_PATH" "${DISK_SIZE}G"
  if [[ $? -ne 0 ]]; then
    echo_error "Failed to create disk image."
    exit 1
  fi
  echo_success "Disk image created at $FULL_PATH"
  echo_info "You can install Windows by running a command like:

  qemu-system-x86_64 \\
      -enable-kvm \\
      -m 4G \\
      -cpu host \\
      -drive file=$FULL_PATH,format=qcow2 \\
      -cdrom /path/to/Windows.ISO \\
      -boot d

  (Adjust memory, CPU, and other settings as needed.)
  "
fi

# --- Show example debug-run command ---
echo_info "For debugging with GDB, you might run something like:

  qemu-system-x86_64 \\
      -enable-kvm \\
      -m 4G \\
      -cpu host \\
      -drive file=/var/lib/qemu_vms/windows.qcow2,format=qcow2 \\
      -s -S

Then from another terminal:
  gdb
  (gdb) target remote :1234
  (gdb) continue

And you'll have full system debugging.
"

# --- Finishing up ---
echo_success "QEMU/KVM environment setup is complete!"
echo_info    "Next steps:
1) Place your Windows ISO somewhere.
2) Use 'qemu-system-x86_64' (or 'virt-manager') to install Windows onto the QCOW2 disk.
3) If needed, configure Samba for file sharing or set up your own share method.
4) For advanced fuzzing, you can snapshot your VM and attach GDB for crash detection.

Happy hacking!
"

exit 0

