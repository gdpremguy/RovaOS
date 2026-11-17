#!/bin/bash
# Refresh desktop files in our completed, generated Niri build only.
# Package changes require build.sh --recover instead. Never opens a disk device.
set -Eeuo pipefail
source_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo_dir=$(dirname -- "$source_dir")
work=/var/cache/kestrel-linux-niri
builder=$work/builder
root=$builder/work/chroot
[[ $EUID == 0 && -f $work/.kestrel-builder && -f $builder/work/.build/chroot_hooks &&
   $(cat "$root/etc/kestrel/desktop") == niri ]] || {
    echo 'Requires the completed isolated Niri builder. Use build.sh --recover.' >&2; exit 1;
}
exec 9>"$work/build.lock"
flock -n 9 || { echo 'Another build is running.' >&2; exit 1; }
python3 "$source_dir/disk_guard.py" --filesystem "${KESTREL_LINUX_BACKING_DIR:-/mnt/e}" --check-only
previous=$(sha256sum "$builder/work/config/package-lists/kestrel.list.chroot" | cut -d' ' -f1)
cp -a "$source_dir/includes.chroot/." "$builder/work/config/includes.chroot/"
for helper in firstboot_persistence.py setup_usb_persistence.py make_persistent.py; do
    cp "$source_dir/$helper" "$builder/work/config/includes.chroot/usr/local/lib/kestrel/$helper"
done
python3 "$source_dir/prepare_niri.py" "$builder/work/config"
python3 "$source_dir/render_welcome.py" --profile niri \
    --output "$builder/work/config/includes.chroot/usr/share/rova/welcome.html"
current=$(sha256sum "$builder/work/config/package-lists/kestrel.list.chroot" | cut -d' ' -f1)
[[ $previous == "$current" ]] || { echo 'Package list changed; use build.sh --recover.' >&2; exit 1; }
mkdir -p "$builder/work/config/includes.chroot/usr/share/backgrounds/rova"
for asset in rova-horizon.png rova-horizon.svg HORIZON-NOTICE.txt; do
    cp "$repo_dir/assets/wallpapers/$asset" "$builder/work/config/includes.chroot/usr/share/backgrounds/rova/$asset"
done
# Do not leave the superseded default bundled in a refreshed image.
rm -f "$builder/work/config/includes.chroot/usr/share/backgrounds/kestrel/summit.bmp" \
      "$root/usr/share/backgrounds/kestrel/summit.bmp"
for relative in etc/kestrel etc/greetd etc/skel/.config etc/xdg etc/systemd/user etc/systemd/system \
                etc/systemd/logind.conf.d usr/share/rova usr/share/backgrounds/rova usr/share/applications usr/share/themes/Rova-Summit usr/share/icons/hicolor/scalable/apps usr/local; do
    mkdir -p "$root/$relative"
    cp -a "$builder/work/config/includes.chroot/$relative/." "$root/$relative/"
done
install -m644 "$builder/work/config/includes.chroot/etc/os-release" "$root/etc/os-release"
# Firefox's distribution directory may be an absolute symlink. Resolve it inside
# the chroot rather than replacing it or following it into the build host.
cp "$builder/work/config/includes.chroot/usr/lib/firefox-esr/distribution/policies.json" "$root/tmp/rova-firefox-policies.json"
chroot "$root" /bin/sh -c 'mkdir -p /usr/lib/firefox-esr/distribution && install -m644 /tmp/rova-firefox-policies.json /usr/lib/firefox-esr/distribution/policies.json'
rm -- "$root/tmp/rova-firefox-policies.json"
# Keep generated runtime data out of the live image; only refresh our known files.
cp "$source_dir/customize.hook.chroot" "$root/tmp/kestrel-refresh-hook"
chroot "$root" /bin/sh /tmp/kestrel-refresh-hook
rm -- "$root/tmp/kestrel-refresh-hook"
cp "$source_dir/brand_boot.py" "$builder/work/config/hooks/live/0900-kestrel.hook.binary"
chmod 755 "$builder/work/config/hooks/live/0900-kestrel.hook.binary"
# Reconfigure ISO identity/hostname as well as refreshing its files.
cp "$source_dir/configure.sh" "$builder/work/configure.sh"
chroot "$builder" /bin/sh -c 'cd /work && sh configure.sh'
mounted=()
cleanup() {
    local i
    for ((i=${#mounted[@]}-1;i>=0;i--)); do umount "${mounted[i]}"; done
}
trap cleanup EXIT
for directory in dev proc sys; do
    if ! mountpoint -q "$builder/$directory"; then
        mount --bind "/$directory" "$builder/$directory"
        mounted+=("$builder/$directory")
    fi
done
chroot "$builder" /bin/sh -c 'cd /work && lb clean --binary'
python3 "$source_dir/disk_guard.py" --filesystem "${KESTREL_LINUX_BACKING_DIR:-/mnt/e}" -- \
    chroot "$builder" /bin/sh -c 'cd /work && lb build' 2>&1 | tee "$work/refresh.log"
cp "$builder/work/live-image-amd64.hybrid.iso" "$repo_dir/rovaos.iso.partial"
mv "$repo_dir/rovaos.iso.partial" "$repo_dir/rovaos.iso"
(cd "$repo_dir" && sha256sum rovaos.iso > rovaos.iso.sha256)
echo 'Built rovaos.iso. Run verification before flashing. No physical drive was written.'
