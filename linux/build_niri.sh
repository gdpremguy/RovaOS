#!/bin/bash
# Build a pinned upstream Niri release in our isolated Debian builder, never the host.
set -Eeuo pipefail
source_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
work=${KESTREL_LINUX_WORK_DIR:-/var/cache/kestrel-linux}
builder=$work/builder
revision=8ed0da44d974c32c6877d2f4630c314da0717ecb
[[ $EUID == 0 && -f $work/.kestrel-builder && -d $builder/usr ]] || {
    echo 'Run as root inside the existing Kestrel Linux builder environment.' >&2; exit 1;
}
exec 9>"$work/build.lock"
flock -n 9 || { echo 'Another Kestrel build is running.' >&2; exit 1; }
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
cp /etc/resolv.conf "$builder/etc/resolv.conf"
chroot "$builder" apt-get update
chroot "$builder" env DEBIAN_FRONTEND=noninteractive apt-get install --yes --no-install-recommends \
    git ca-certificates build-essential rustc cargo clang pkg-config dpkg-dev \
    libudev-dev libgbm-dev libxkbcommon-dev libegl1-mesa-dev libwayland-dev \
    libinput-dev libdbus-1-dev libsystemd-dev libseat-dev libpipewire-0.3-dev \
    libpango1.0-dev libdisplay-info-dev
mkdir -p "$builder/opt/kestrel-niri"
if [[ ! -d $builder/opt/kestrel-niri/source/.git ]]; then
    chroot "$builder" git init /opt/kestrel-niri/source
fi
chroot "$builder" git -C /opt/kestrel-niri/source fetch --depth=1 https://github.com/niri-wm/niri.git "$revision"
chroot "$builder" git -C /opt/kestrel-niri/source checkout --detach "$revision"
[[ $(chroot "$builder" git -C /opt/kestrel-niri/source rev-parse HEAD) == "$revision" ]]
chroot "$builder" env -C /opt/kestrel-niri/source CARGO_BUILD_JOBS=2 cargo build --release --locked
stage=$builder/opt/kestrel-niri/package
mkdir -p "$stage/DEBIAN" "$stage/usr/bin" "$stage/usr/share/wayland-sessions" \
    "$stage/usr/share/xdg-desktop-portal" "$stage/usr/lib/systemd/user" \
    "$builder/opt/kestrel-niri/source/debian"
install -m755 "$builder/opt/kestrel-niri/source/target/release/niri" "$stage/usr/bin/niri"
install -m755 "$builder/opt/kestrel-niri/source/resources/niri-session" "$stage/usr/bin/niri-session"
install -m644 "$builder/opt/kestrel-niri/source/resources/niri.desktop" "$stage/usr/share/wayland-sessions/"
install -m644 "$builder/opt/kestrel-niri/source/resources/niri-portals.conf" "$stage/usr/share/xdg-desktop-portal/"
install -m644 "$builder/opt/kestrel-niri/source/resources/niri.service" \
    "$builder/opt/kestrel-niri/source/resources/niri-shutdown.target" "$stage/usr/lib/systemd/user/"
printf 'Source: niri\nSection: x11\nPriority: optional\nMaintainer: KestrelOS local build <build@localhost>\n\nPackage: niri\nArchitecture: amd64\nDescription: Pinned upstream Niri for KestrelOS\n' \
    > "$builder/opt/kestrel-niri/source/debian/control"
depends=$(chroot "$builder" env -C /opt/kestrel-niri/source dpkg-shlibdeps -O -e target/release/niri)
depends=${depends#shlibs:Depends=}
cat > "$stage/DEBIAN/control" <<EOF
Package: niri
Version: 26.04-1kestrel1
Architecture: amd64
Maintainer: KestrelOS local build <build@localhost>
Depends: $depends
Description: Niri scrollable-tiling Wayland compositor for KestrelOS
 Built from upstream commit $revision with Cargo.lock enforced.
EOF
mkdir -p "$source_dir/artifacts"
chroot "$builder" dpkg-deb --root-owner-group --build /opt/kestrel-niri/package /opt/kestrel-niri/niri_26.04-1kestrel1_amd64.deb
cp "$builder/opt/kestrel-niri/niri_26.04-1kestrel1_amd64.deb" "$source_dir/artifacts/"
echo 'Niri package built. The live ISO has NOT been changed by this command.'
