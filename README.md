makeing a disk image:

# Revert your disk to snapshot "clean"
qemu-img snapshot -a clean windows98.qcow2

# Then just run QEMU in the normal way
qemu-system-i386 -drive file=windows98.qcow2,format=qcow2 -monitor stdio

(set up the image as you need)

(qemu) savevm clean

(qemu) quit


for the tui you need pynput and rich installed


process of setiing up a fuzz job:

## Setting up a windows fuzz job

Step 1: Start your vm image attaching your shared directory you will be using for the fuzz job.

qemu-system-x86_64 -drive file=Windows10.qcow2,format=qcow2 -net nic -net user,smb=/home/user/fawkes_shared -monitor stdio

Step 2: Mount the shared drive to the Z:\

net use Z: \\10.0.2.4\qemu

Step 3: Install the user space monitoring agent

You can just move the WindowsAgent.exe into the share to access it and then copy it to the desktop or where ever you would like and run it from the terminal.

step 4: Setup any automation scripts or things you need take your snap shot and then you are good to run the fawks system for your test.



