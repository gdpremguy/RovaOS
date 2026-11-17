"""Inspect the built Linux live filesystem without booting or mounting it."""
import argparse
import hashlib
import json
import pathlib
import subprocess
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]


def verify(image):
    image = image.resolve()
    cache = pathlib.Path.home() / '.cache' / 'kestrel-linux'
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='verify-', dir=cache) as work:
        squash = pathlib.Path(work) / 'filesystem.squashfs'
        subprocess.run(['xorriso', '-osirrox', 'on', '-indev', str(image),
                        '-extract', '/live/filesystem.squashfs', str(squash)], check=True)

        def cat(path):
            return subprocess.check_output(['unsquashfs', '-cat', str(squash), path], text=True)

        status = cat('var/lib/dpkg/status')
        packages = {}
        for stanza in status.split('\n\n'):
            fields = dict(line.split(': ', 1) for line in stanza.splitlines()
                          if ': ' in line and not line.startswith(' '))
            if fields.get('Status') == 'install ok installed':
                packages[fields['Package']] = fields['Version']
        required = ['linux-image-amd64', 'firmware-iwlwifi', 'network-manager',
                    'wpasupplicant', 'firefox-esr', 'ca-certificates', 'xfce4',
                    'lightdm', 'systemd-timesyncd', 'xserver-xorg-input-libinput',
                    'arc-theme', 'papirus-icon-theme', 'librsvg2-common', 'rofi', 'python3-gi',
                    'xfce4-power-manager-plugins']
        niri = 'niri' in packages
        if niri:
            required = [p for p in required if p not in ('xfce4', 'lightdm', 'xserver-xorg-input-libinput', 'xfce4-power-manager-plugins', 'rofi')]
            required += ['niri', 'greetd', 'waybar', 'foot', 'fuzzel', 'mako-notifier', 'power-profiles-daemon']
        missing = [package for package in required if package not in packages]
        if missing:
            raise RuntimeError(f'Live image is missing packages: {missing}')
        listing = subprocess.check_output(['unsquashfs', '-ls', str(squash)], text=True)
        permissions = subprocess.check_output(['unsquashfs', '-ll', str(squash)], text=True)
        for line in permissions.splitlines():
            fields = line.split()
            if len(fields) >= 6 and (fields[5] == 'squashfs-root/usr/local' or fields[5].startswith('squashfs-root/usr/local/')):
                if fields[0].startswith('l'):
                    continue
                if fields[1] != 'root/root' or fields[0][5] == 'w' or fields[0][8] == 'w':
                    raise RuntimeError(f'User-writable or non-root desktop helper: {line}')
        if 'iwlwifi.ko' not in listing or 'iwlwifi-so-a0-gf-a0-' not in listing:
            raise RuntimeError('AX211-family driver/firmware absent from live filesystem')
        if not niri and '/plugins/power-manager-plugin.desktop' not in listing:
            raise RuntimeError('Configured battery panel plugin is missing')
        for relative in ['etc/systemd/system/kestrel-smoke-report.service',
                         'etc/systemd/timesyncd.conf.d/50-kestrel.conf',
                         'usr/local/libexec/kestrel-display-default',
                         'etc/xdg/autostart/kestrel-display.desktop',
                         'usr/local/bin/kestrel-clock-report',
                         'etc/xdg/xfce4/xfconf/xfce-perchannel-xml/xfwm4.xml',
                         'etc/xdg/xfce4/xfconf/xfce-perchannel-xml/xfce4-panel.xml',
                         'etc/xdg/xfce4/xfconf/xfce-perchannel-xml/xsettings.xml',
                         'etc/xdg/rofi/kestrel.rasi',
                         'usr/share/themes/Rova-Summit/gtk-3.0/gtk.css',
                         'usr/local/libexec/kestrel-smoke-enabled',
                         'usr/local/libexec/kestrel-smoke-report',
                         'usr/local/libexec/kestrel-desktop-init',
                          'usr/local/lib/kestrel/session.py',
                          'usr/local/lib/kestrel/experience.py',
                          'usr/share/rova/branding.json',
                          'usr/share/rova/control-center.json',
                          'usr/share/rova/shortcuts.json',
                          'usr/share/rova/welcome-profiles.json',
                          'usr/share/rova/welcome.template.html',
                          'usr/share/rova/welcome.css',
                         'usr/local/bin/kestrel-control-center',
                         'usr/local/bin/kestrel-firstboot',
                         'etc/systemd/system/kestrel-firstboot-smoke.service',
                         'usr/local/libexec/kestrel-firstboot-smoke-enabled',
                         'usr/local/libexec/kestrel-firstboot-smoke',
                         'usr/local/libexec/kestrel-persistence-smoke',
                         'etc/os-release',
                         'usr/lib/firefox-esr/distribution/policies.json']:
            if cat(relative) != (ROOT / 'linux/includes.chroot' / relative).read_text():
                raise RuntimeError(f'Built configuration differs from source: {relative}')
        from render_welcome import render
        if cat('usr/share/rova/welcome.html') != render('niri' if niri else 'xfce'):
            raise RuntimeError('Welcome page differs from current content or desktop profile')
        for helper in ('firstboot_persistence.py', 'setup_usb_persistence.py', 'make_persistent.py'):
            if cat('usr/local/lib/kestrel/'+helper) != (ROOT/'linux'/helper).read_text():
                raise RuntimeError(f'Built first-boot backend differs from source: {helper}')
        if cat('etc/timezone').strip() != 'Australia/Adelaide':
            raise RuntimeError('Unexpected timezone')
        session_config = 'etc/greetd/config.toml' if niri else 'etc/lightdm/lightdm.conf.d/50-kestrel.conf'
        if 'kestrel' not in cat(session_config):
            raise RuntimeError('Live desktop user is not configured')
        if niri and cat('etc/skel/.config/niri/config.kdl') != (ROOT/'linux/niri/config.kdl').read_text():
            raise RuntimeError('Niri configuration differs from source')
        if niri:
            for relative in ('usr/local/lib/kestrel/desktop.py', 'usr/local/bin/kestrel-tools',
                             'usr/local/bin/kestrel-desktop-status', 'usr/local/bin/kestrel-display-settings',
                             'usr/local/libexec/kestrel-niri-session', 'usr/local/libexec/kestrel-autotile',
                             'usr/local/libexec/kestrel-wallpaper', 'usr/local/libexec/kestrel-space-watch',
                             'usr/local/libexec/kestrel-desktop-smoke'):
                if cat(relative) != (ROOT/'linux/includes.chroot'/relative).read_text():
                    raise RuntimeError(f'Desktop helper differs from source: {relative}')
            for source, target in [('config.kdl', 'niri/config.kdl'), ('waybar.json', 'waybar/config'),
                                   ('waybar.css', 'waybar/style.css')]:
                if cat('etc/skel/.config/'+target) != (ROOT/'linux/niri'/source).read_text():
                    raise RuntimeError(f'Desktop default differs from source: {source}')
            if cat('usr/share/rova/defaults/niri/config.kdl') != (ROOT/'linux/niri/config.kdl').read_text():
                raise RuntimeError('Recovery defaults differ from source')
        for asset in ('rova-horizon.png', 'rova-horizon.svg', 'HORIZON-NOTICE.txt'):
            embedded = subprocess.check_output([
                'unsquashfs', '-cat', str(squash), 'usr/share/backgrounds/rova/'+asset])
            if embedded != (ROOT/'assets/wallpapers'/asset).read_bytes():
                raise RuntimeError(f'Default wallpaper differs from source: {asset}')
        with image.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        result = {'iso_sha256': digest, 'desktop_profile': 'niri' if niri else 'xfce', 'packages': {name: packages[name] for name in required},
                  'iwlwifi_driver': True, 'ax211_family_firmware': True,
                  'configuration_matches_source': True, 'physical_wifi_tested': False}
        output = ROOT / 'build'
        output.mkdir(exist_ok=True)
        (output / 'linux-image-verification.json').write_text(json.dumps(result, indent=2) + '\n')
        print('Linux ISO package/configuration/Intel firmware verification: PASS')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', nargs='?', type=pathlib.Path, default=ROOT / 'rovaos.iso')
    verify(parser.parse_args().image)
