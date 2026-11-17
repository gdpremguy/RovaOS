"""Prepare a separate Niri live-build profile; keep the verified Xfce ISO intact."""
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parent


def prepare(config):
    package = ROOT/'artifacts/niri_26.04-1kestrel1_amd64.deb'
    if not package.is_file():
        raise RuntimeError('Run linux/build_niri.sh first; no unverified external packages are downloaded')
    includes = config/'includes.chroot'
    packages = (ROOT/'packages.list.chroot').read_text().splitlines()
    excluded = {'lightdm', 'lightdm-gtk-greeter', 'rofi', 'xserver-xorg',
                'xserver-xorg-input-libinput', 'xserver-xorg-video-all'}
    packages = [p for p in packages if p not in excluded and not p.startswith('xfce4')]
    packages += ['niri', 'greetd', 'waybar', 'fuzzel', 'foot', 'mako-notifier', 'swaybg',
                 'swaylock', 'swayidle', 'brightnessctl', 'xdg-desktop-portal',
                 'xdg-desktop-portal-gtk', 'xdg-desktop-portal-gnome', 'libpam-systemd',
                 'libegl1', 'libgl1-mesa-dri', 'e2fsprogs', 'util-linux', 'udev',
                 'power-profiles-daemon']
    (config/'package-lists/kestrel.list.chroot').write_text('\n'.join(packages)+'\n')
    (config/'packages.chroot').mkdir(exist_ok=True)
    shutil.copyfile(package, config/'packages.chroot'/package.name)
    files = {
        'etc/kestrel/desktop': 'niri\n',
        'etc/greetd/config.toml': '[terminal]\nvt = 7\n[default_session]\ncommand = "agreety --cmd /usr/local/libexec/kestrel-niri-session"\nuser = "_greetd"\n[initial_session]\ncommand = "/usr/local/libexec/kestrel-niri-session"\nuser = "kestrel"\n',
        'etc/skel/.config/gtk-3.0/settings.ini': '[Settings]\ngtk-theme-name=Rova-Summit\ngtk-icon-theme-name=Papirus-Dark\ngtk-font-name=DejaVu Sans 11\n',
        'etc/skel/.config/mako/config': 'font=DejaVu Sans 11\nbackground-color=#0d1b25\ntext-color=#e8f3f5\nborder-color=#64c6c1\nborder-radius=8\ndefault-timeout=7000\n',
        'etc/systemd/logind.conf.d/60-kestrel-laptop.conf': '[Login]\nHandleLidSwitch=suspend\nHandleLidSwitchExternalPower=suspend\nHandleLidSwitchDocked=ignore\n',
    }
    for relative, content in files.items():
        path = includes/relative;path.parent.mkdir(parents=True, exist_ok=True);path.write_text(content)
    for original, relative in [('config.kdl', 'niri/config.kdl'), ('waybar.json', 'waybar/config'),
                               ('waybar.css', 'waybar/style.css'), ('fuzzel.ini', 'fuzzel/fuzzel.ini')]:
        path = includes/'etc/skel/.config'/relative
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/'niri'/original, path)
    defaults = includes/'usr/share/rova/defaults/niri'
    defaults.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT/'niri/config.kdl', defaults/'config.kdl')
    # Explicit single startup owner; no competing spawn-at-startup entries.
    for name, command in {
        'kestrel-wallpaper': '/usr/local/libexec/kestrel-wallpaper',
        'kestrel-space-watch': '/usr/local/libexec/kestrel-space-watch',
        'kestrel-idle': '/usr/bin/swayidle -w timeout 600 "swaylock -f -c 0d1b25" before-sleep "swaylock -f -c 0d1b25"',
    }.items():
        path = includes/f'etc/systemd/user/{name}.service'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('[Unit]\nDescription=Rova desktop component\nPartOf=graphical-session.target\n'
                        'After=graphical-session.target\n[Service]\nExecStart='+command+
                        '\nRestart=on-failure\nRestartSec=3\n[Install]\nWantedBy=graphical-session.target\n')


if __name__ == '__main__':
    prepare(pathlib.Path(sys.argv[1]))
