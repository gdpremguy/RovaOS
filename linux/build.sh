#!/bin/bash
# Root is required only inside the Linux builder. Never opens a physical disk.
set -Eeuo pipefail
source_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo_dir=$(dirname -- "$source_dir")
desktop=${ROVA_DESKTOP:-${KESTREL_DESKTOP:-xfce}}
case "$desktop" in xfce|niri) ;; *) echo 'Unknown desktop profile' >&2; exit 1;; esac
default_work=/var/cache/kestrel-linux
if [[ $desktop == niri ]]; then default_work=/var/cache/kestrel-linux-niri;fi
work=${KESTREL_LINUX_WORK_DIR:-$default_work}
recover=false
if [[ ${1:-} == --recover ]]; then recover=true;shift;fi
if [[ $# != 0 ]]; then echo 'Usage: build.sh [--recover]' >&2;exit 1;fi
if [[ $EUID != 0 ]]; then
    echo 'Run with sudo on Linux, or: wsl --user root --exec bash linux/build.sh' >&2
    exit 1
fi
for tool in debootstrap chroot mount mountpoint flock findmnt python3; do
    command -v "$tool" >/dev/null || { echo "Missing build dependency: $tool" >&2; exit 1; }
done
work=$(realpath -m -- "$work")
case "$work" in /|/mnt/*|"$repo_dir"|"$repo_dir"/*)
    echo 'Use a dedicated Linux ext4 build cache, not the project or a Windows mount.' >&2; exit 1;;
esac
mkdir -p -- "$work"
if [[ ! -f "$work/.kestrel-builder" && -n $(find "$work" -mindepth 1 -maxdepth 1 -print -quit) ]]; then
    echo "Refusing to use a nonempty unrelated directory: $work" >&2; exit 1
fi
touch "$work/.kestrel-builder"
exec 9>"$work/build.lock"
flock -n 9 || { echo 'Another RovaOS build is running.' >&2; exit 1; }
builder=$work/builder
backing=${KESTREL_LINUX_BACKING_DIR:-$work}
if [[ -z ${KESTREL_LINUX_BACKING_DIR:-} && -d /mnt/c && $(uname -r) == *microsoft* ]]; then backing=/mnt/c;fi
python3 "$source_dir/disk_guard.py" --filesystem "$backing" --check-only
if [[ ! -f "$work/bootstrap-complete" ]]; then
    debootstrap --arch=amd64 --variant=minbase --include=ca-certificates \
        trixie "$builder" https://deb.debian.org/debian/
    touch "$work/bootstrap-complete"
fi
mounted=()
cleanup() {
    local i
    for ((i=${#mounted[@]}-1;i>=0;i--)); do
        umount "${mounted[i]}" || echo "Build mount still busy: ${mounted[i]}" >&2
    done
}
trap cleanup EXIT
for directory in dev proc sys; do
    mkdir -p "$builder/$directory"
    if ! mountpoint -q "$builder/$directory"; then
        mount --bind "/$directory" "$builder/$directory"
        mounted+=("$builder/$directory")
    fi
done
# Block package maintainer scripts from starting services on the build host.
printf '#!/bin/sh\nexit 101\n' > "$builder/usr/sbin/policy-rc.d"
chmod 755 "$builder/usr/sbin/policy-rc.d"
cp /etc/resolv.conf "$builder/etc/resolv.conf"
chroot "$builder" apt-get update
chroot "$builder" env DEBIAN_FRONTEND=noninteractive apt-get install --yes --no-install-recommends \
    live-build squashfs-tools xorriso grub-pc-bin grub-efi-amd64-bin \
    isolinux syslinux-common mtools dosfstools cpio zstd python3 binutils file
mkdir -p "$builder/work"
if "$recover" && [[ -d "$builder/work/.build" ]]; then
    # Only the generated image root is reset, never the project or boot USB.
    # Retain downloaded .debs in live-build's package cache before cleaning.
    mkdir -p "$builder/work/cache/packages.chroot"
    if [[ -d "$builder/work/chroot/var/cache/apt/archives" ]]; then
        find "$builder/work/chroot/var/cache/apt/archives" -maxdepth 1 -name '*.deb' \
            -exec cp -n -- '{}' "$builder/work/cache/packages.chroot/" \;
    fi
    # Reset bootstrap stage markers too: --chroot alone leaves a completed
    # bootstrap marker pointing at the now-removed generated root.
    # --all preserves cache/; --purge would discard the downloads.
    chroot "$builder" /bin/sh -c 'cd /work && lb clean --all'
fi
cp "$source_dir/configure.sh" "$builder/work/configure.sh"
(cd "$builder/work" && chroot "$builder" /bin/sh -c 'cd /work && sh configure.sh')
mkdir -p "$builder/work/config/package-lists" "$builder/work/config/hooks/live"
cp "$source_dir/packages.list.chroot" "$builder/work/config/package-lists/kestrel.list.chroot"
cp -a "$source_dir/includes.chroot/." "$builder/work/config/includes.chroot/"
mkdir -p "$builder/work/config/includes.chroot/usr/local/lib/kestrel"
for helper in firstboot_persistence.py setup_usb_persistence.py make_persistent.py; do
    cp "$source_dir/$helper" "$builder/work/config/includes.chroot/usr/local/lib/kestrel/$helper"
done
if [[ $desktop == niri ]]; then
    python3 "$source_dir/prepare_niri.py" "$builder/work/config"
fi
python3 "$source_dir/render_welcome.py" --profile "$desktop" \
    --output "$builder/work/config/includes.chroot/usr/share/rova/welcome.html"
cp "$source_dir/customize.hook.chroot" "$builder/work/config/hooks/live/0500-kestrel.hook.chroot"
cp "$source_dir/brand_boot.py" "$builder/work/config/hooks/live/0900-kestrel.hook.binary"
chmod 755 "$builder/work/config/hooks/live/0900-kestrel.hook.binary"
chmod 755 "$builder/work/config/hooks/live/0500-kestrel.hook.chroot"
mkdir -p "$builder/work/config/includes.chroot/usr/share/backgrounds/rova"
cp "$repo_dir/assets/wallpapers/rova-horizon.png" "$builder/work/config/includes.chroot/usr/share/backgrounds/rova/rova-horizon.png"
cp "$repo_dir/assets/wallpapers/rova-horizon.svg" "$builder/work/config/includes.chroot/usr/share/backgrounds/rova/rova-horizon.svg"
cp "$repo_dir/assets/wallpapers/HORIZON-NOTICE.txt" "$builder/work/config/includes.chroot/usr/share/backgrounds/rova/HORIZON-NOTICE.txt"
# Retire only the previous generated Linux default, not user wallpapers.
rm -f "$builder/work/config/includes.chroot/usr/share/backgrounds/kestrel/summit.bmp"
python3 "$source_dir/disk_guard.py" --filesystem "$backing" -- \
    chroot "$builder" /bin/sh -c 'cd /work && lb build' 2>&1 | tee "$work/build.log"
mapfile -t images < <(find "$builder/work" -maxdepth 1 -type f -name '*.hybrid.iso')
if [[ ${#images[@]} != 1 ]]; then
    echo 'Expected exactly one completed hybrid ISO. Nothing published.' >&2; exit 1
fi
output=rovaos-xfce.iso
if [[ $desktop == niri ]]; then output=rovaos.iso;fi
cp "${images[0]}" "$repo_dir/$output.partial"
mv "$repo_dir/$output.partial" "$repo_dir/$output"
(cd "$repo_dir" && sha256sum "$output" > "$output.sha256")
echo "Built $repo_dir/$output"
echo 'Use the RovaOS ISO. No physical drive was written.'
