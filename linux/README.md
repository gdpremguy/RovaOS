# Build RovaOS

The current portable desktop uses Debian 13 amd64, Niri, Waybar and Horizon
artwork. Output: **`rovaos.iso`** and `rovaos.iso.sha256`.

Build on Linux or WSL as root inside Linux. The scripts use isolated Debian
builders and write regular image files, never a physical USB or internal disk.
Allow generous free space for dependencies, caches and build output.

## First build from source

The compiled Niri package is deliberately not in the repository. The current
recipes need a bootstrapped builder before compiling it. A supported first-build
route is:

```sh
sudo apt-get install debootstrap debian-archive-keyring

# Bootstrap the default builder and its dependencies through an Xfce build.
# This also creates rovaos-xfce.iso, which is not the primary Niri edition.
sudo env ROVA_DESKTOP=xfce bash linux/build.sh

# Compile the pinned upstream compositor in that builder.
sudo bash linux/build_niri.sh

# Build the primary desktop in its separate cache.
sudo env ROVA_DESKTOP=niri bash linux/build.sh
python3 linux/verify.py rovaos.iso
```

The Xfce configs are retained because this bootstrap/fallback path uses them.
The package generated in `linux/artifacts/` is ignored by Git.

On WSL, set `KESTREL_LINUX_BACKING_DIR` to the Windows backing volume if
necessary, for example `/mnt/e`. Choose your actual drive, not a copied
developer-specific path. The disk guard checks available backing storage.

## Subsequent changes

For desktop-file changes with an already completed Niri builder:

```sh
sudo bash linux/refresh_niri.sh
python3 linux/verify.py rovaos.iso
sha256sum -c rovaos.iso.sha256
```

Package changes need a full rebuild:

```sh
sudo env ROVA_DESKTOP=niri bash linux/build.sh --recover
```

Recovery rebuilds the generated image root while retaining download caches.
Do not remove builders with active mounts.

## Tests

```sh
python3 -B -m unittest discover -s tests
python3 linux/smoke.py --image rovaos.iso --desktop niri --virgl --guest-only \
  --firmware /usr/share/ovmf/OVMF.fd --timeout 900
python3 linux/firstboot_smoke.py --iso rovaos.iso --firmware /usr/share/ovmf/OVMF.fd
```

Smoke tests use QEMU and disposable virtual disks. Guest-only mode does not test
host input, and VM success is not proof of hardware compatibility or USB safety.

## Using the image

Back up the target USB, then flash with Rufus **DD mode** or another raw-image
writer. Flashing erases the selected drive. Boot the USB on a compatible
x86-64 Intel/AMD PC; ARM and Apple Silicon are not supported. Secure Boot,
graphics, Wi-Fi, sleep and other features require testing on the target machine.

The ISO alone is temporary. Open **USB saving setup**, review its confirmation,
restart when prompted, then check for **Persistent USB**. Saving is unencrypted;
temporary-session files are not automatically migrated. Never unplug while
running or suspended. Back up before updating or reflashing.

There is no internal-drive installer. See [USB saving](usb-persistence.md),
[Niri controls](niri/README.md), [customisation](customising-desktop.md) and
[compatibility identifiers](rebranding.md).
