#!/usr/bin/python3
"""Brand generated BIOS/UEFI menus without changing their boot payloads."""
import pathlib
import re
import struct
import zlib


def splash(width=640, height=480):
    def chunk(kind, data):
        return struct.pack('>I', len(data))+kind+data+struct.pack('>I', zlib.crc32(kind+data))
    pixels = bytearray()
    for y in range(height):
        pixels.append(0)
        for x in range(width):
            colour = (13+int(9*y/height), 27+int(14*y/height), 37+int(15*y/height))
            # A restrained glacier-coloured R, above the boot menu.
            u, v = x-width//2, y-height//4
            if ((-38 <= u <= -26 and -42 <= v <= 42)
                    or (-26 <= u <= 20 and (-42 <= v <= -30 or -6 <= v <= 6))
                    or (14 <= u <= 28 and -30 <= v <= -6)
                    or (6 <= v <= 42 and abs(u-((v-6)*1.2-20)) <= 6)):
                colour = (100, 198, 193)
            pixels.extend(colour)
    return (b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
            +chunk(b'IDAT', zlib.compress(pixels))+chunk(b'IEND', b''))


def brand(binary):
    binary = pathlib.Path(binary).resolve()
    for relative in ('boot/grub/grub.cfg', 'isolinux/live.cfg'):
        path = binary/relative
        if path.exists():
            text = path.read_text()
            text = text.replace('Live system (amd64 fail-safe mode)', 'RovaOS — troubleshooting')
            text = text.replace('Live system (amd64)', 'RovaOS — start desktop')
            text = text.replace('KestrelOS', 'RovaOS')
            profile = binary.parent/'config/includes.chroot/etc/kestrel/desktop'
            if profile.exists() and profile.read_text().strip() == 'niri':
                text = recovery_entries(text, relative.endswith('grub.cfg'))
            path.write_text(text)
    # Use ASCII for the legacy VGA menu font.
    bios = binary/'isolinux/live.cfg'
    if bios.exists():
        bios.write_text(bios.read_text().replace('—', '-'))
    menu = binary/'isolinux/menu.cfg'
    if menu.exists():
        lines = menu.read_text().splitlines()
        menu.write_text('\n'.join('menu title RovaOS / Summit' if line.startswith('menu title ') else line for line in lines)+'\n')
    legacy = binary/'isolinux/isolinux.cfg'
    if legacy.exists():
        lines = legacy.read_text().splitlines()
        legacy.write_text('\n'.join('timeout 50' if line.startswith('timeout ') else line for line in lines)+'\n')
    config = binary/'boot/grub/config.cfg'
    if config.exists():
        lines = config.read_text().splitlines()
        config.write_text('set timeout=5\n'+'\n'.join(line for line in lines if not line.startswith(('play ', 'insmod play', 'set timeout=')))+'\n')
    for relative in ('boot/grub/splash.png', 'isolinux/splash.png'):
        path = binary/relative
        if path.parent.is_dir():
            path.write_bytes(splash())
    theme = binary/'boot/grub/live-theme/theme.txt'
    if theme.exists():
        text = theme.read_text().replace('title-text: ""', 'title-text: "RovaOS / Summit"').replace('KestrelOS', 'RovaOS')
        text = text.replace('#a8a8a8', '#a4bdc6')
        theme.write_text(text)


def recovery_entries(text, grub):
    """Clone the real kernel/initrd arguments, not a guessed kernel filename."""
    if 'kestrel.recovery' in text:
        return text
    if grub:
        match = re.search(r'^menuentry[^\n]+\{\n.*?^}', text, re.M | re.S)
        if not match:
            raise ValueError('Cannot locate the normal GRUB live entry')
        normal = match.group()
        def entry(title, extra, temporary=False):
            value = re.sub(r'^menuentry[^\n]+', f'menuentry "{title}" {{', normal, count=1)
            if temporary:
                value = re.sub(r'(?<!\S)persistence(?:-[\w-]+=[^\s]+)?(?=\s|$)', '', value)
            return re.sub(r'^(\s*linux[^\n]+)', lambda m: m[1]+' '+extra, value, count=1, flags=re.M)
        return text + '\n' + entry('RovaOS - desktop recovery (clean settings)', 'kestrel.recovery') + '\n' + entry(
            'RovaOS - safe graphics console (temporary)', 'nomodeset systemd.unit=multi-user.target', True) + '\n'
    match = re.search(r'^label [^\n]+\n.*?(?=^label |\Z)', text, re.M | re.S)
    if not match:
        raise ValueError('Cannot locate the normal BIOS live entry')
    normal = match.group()
    def entry(name, title, extra, temporary=False):
        value = re.sub(r'^label [^\n]+', 'label '+name, normal, count=1)
        value = re.sub(r'^\s*menu default\s*$', '', value, flags=re.M)
        value = re.sub(r'^(\s*menu label)[^\n]+', lambda m: m[1]+' '+title, value, count=1, flags=re.M)
        if temporary:
            value = re.sub(r'(?<!\S)persistence(?:-[\w-]+=[^\s]+)?(?=\s|$)', '', value)
        return re.sub(r'^(\s*append[^\n]+)', lambda m: m[1]+' '+extra, value, count=1, flags=re.M)
    return text + '\n' + entry('kestrel-recovery', 'RovaOS - desktop recovery (clean settings)', 'kestrel.recovery') + '\n' + entry(
        'kestrel-console', 'RovaOS - safe graphics console (temporary)', 'nomodeset systemd.unit=multi-user.target', True) + '\n'


if __name__ == '__main__':
    # live-build runs binary hooks with the binary tree as the working directory.
    brand('.')
