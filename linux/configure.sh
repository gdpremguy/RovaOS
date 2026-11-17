#!/bin/sh
# Run inside a clean Debian live-build work directory, not in the source tree.
set -eu
lb config \
    --mode debian \
    --distribution trixie \
    --architectures amd64 \
    --binary-images iso-hybrid \
    --bootloaders "syslinux,grub-efi" \
    --archive-areas "main contrib non-free non-free-firmware" \
    --firmware-chroot false \
    --firmware-binary false \
    --debian-installer false \
    --uefi-secure-boot auto \
    --apt-recommends false \
    --apt-indices false \
    --apt-source-archives false \
    --security true \
    --updates true \
    --mirror-bootstrap https://deb.debian.org/debian/ \
    --mirror-chroot https://deb.debian.org/debian/ \
    --mirror-binary https://deb.debian.org/debian/ \
    --mirror-chroot-security https://security.debian.org/debian-security/ \
    --mirror-binary-security https://security.debian.org/debian-security/ \
    --iso-volume ROVA_LINUX \
    --iso-application "RovaOS Live" \
    --bootappend-live "boot=live components username=kestrel hostname=rovaos locales=en_AU.UTF-8 keyboard-layouts=us timezone=Australia/Adelaide persistence persistence-label=kestrel-rw persistence-storage=filesystem persistence-media=removable-usb noeject"
