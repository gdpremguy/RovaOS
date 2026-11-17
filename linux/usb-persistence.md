# Small ISO + a save partition on the USB

You do **not** need to download or manage a multi-GB persistent `.img`.
The existing `kestrelos-linux.iso` already supports this method. No ISO rebuild
is needed. The save space exists on the USB only, not on the computer's disk.

## Requirements and safety

- Back up everything on the USB first. **Flashing the ISO erases that USB.**
- Flash `kestrelos-linux.iso` with Rufus **DD mode**, not ISO extraction mode.
- Run setup on **native Linux from another drive/session**, with this USB
  plugged in but all its partitions unmounted. It cannot modify the USB you
  are currently booted from. WSL/Windows are explicitly rejected.
- Have the exact ISO used for flashing, Python 3, `e2fsprogs`, `util-linux`,
  and `udev`. On Debian/Ubuntu the last three supply `mke2fs`, `blockdev`,
  and `udevadm`. Run setup from a folder on the other Linux drive.
- Put `setup_usb_persistence.py` and `make_persistent.py` in the same folder.
  Importing the latter does not create a disk image.
- Only removable whole USB disks under `/dev/disk/by-id/usb-*` are accepted.
  USB SSDs marked non-removable, internal disks, mounted partitions, swap,
  device-mapper users and disks with existing save partitions are refused.

## 1. Identify the correct USB (read-only)

```sh
lsblk -o NAME,SIZE,MODEL,TRAN,RM,MOUNTPOINTS
ls -l /dev/disk/by-id/usb-*
```

Match its model, capacity and serial to the USB you intend to change. Select
the whole-disk link **without** `-part1`/`-part2`. Unmount only that USB's
mounted partitions using your file manager; do not choose Eject yet.

## 2. Preview the plan (no writes)

Replace the sample ISO path and `usb-YOUR_STICK_SERIAL` with your actual paths:

```sh
sudo python3 setup_usb_persistence.py \
  --iso /path/to/kestrelos-linux.iso \
  --device /dev/disk/by-id/usb-YOUR_STICK_SERIAL
```

The tool compares the flashed USB bytes with the supplied ISO and validates
the partition metadata before showing the plan. By default it uses remaining
whole MiB for saving. Add e.g. `--save-mib 512` for a smaller save partition.
The minimum is 64 MiB; leave more room for Firefox and downloaded files.

## 3. Create the save partition (writes to that USB)

Run the same command with `--apply`:

```sh
sudo python3 setup_usb_persistence.py \
  --iso /path/to/kestrelos-linux.iso \
  --device /dev/disk/by-id/usb-YOUR_STICK_SERIAL \
  --apply
```

You must type `CREATE SAVE ON usb-YOUR_STICK_SERIAL` exactly. There is no
unattended `--yes` option. A small JSON backup of changed partition-table
metadata is saved in your current folder before writing. This is not a backup
of USB files and cannot undo formatting. No full-size image file is created.

The tool retains the ISO/EFI payload, adds GPT/MBR partition 3, formats **only
that new partition** as ext4 labelled `kestrel-rw`, and seeds
`persistence.conf` with `/ union`. Existing persistence is never resized or
reformatted by this tool. If any step fails after metadata writing, stop and
keep the printed backup; do not retry blindly or manually format another disk.

## 4. Boot and confirm

Safely eject, then boot the Kestrel USB. In Control Center check for
**Persistent USB**, or run `kestrel-session-status`. Create a small file,
shut down normally, boot again, and check it survived. If status says temporary,
do not rely on saves. The status detection works with ISO+save partitions even
if an older welcome page only mentions the prebuilt `.img` option.

**Saves are unencrypted**, including Wi-Fi credentials. Reflashing the ISO
can erase them, so back up before updates. A separate save partition reduces
download/image-file size; it does not make slow USB random writes faster.

## Validation limits

The partition planner and refusal paths are tested against synthetic files.
QEMU tests can verify the resulting USB layout and cold-boot persistence.
Physical-drive writing requires a sacrificial USB test before broad release;
no physical USB is modified by the automated tests.
