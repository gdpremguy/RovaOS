"""Boot the actual Linux ISO, then test guest networking, HTTPS and Firefox.

No physical disks are attached; QEMU supplies a disposable NAT Ethernet link.
This tests the Linux software stack, NOT the ThinkPad's physical AX211 radio.
"""
import argparse
import base64
import hashlib
import json
import pathlib
import selectors
import shutil
import socket
import subprocess
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]


def smoke(image, firmware=None, timeout=600, showcase=False, desktop='xfce', virgl=False, guest_only=False):
    image = image.resolve()
    if not image.is_file():
        raise SystemExit(f'Build the Linux image first: {image}')
    output = ROOT / 'build'
    output.mkdir(exist_ok=True)
    mode = 'uefi' if firmware else 'bios'
    log = bytearray()
    with tempfile.TemporaryDirectory(prefix='kestrel-linux-smoke-') as work:
        qmp_path = pathlib.Path(work) / 'qmp.sock'
        command = [
            'qemu-system-x86_64', '-m', '3072', '-smp', '2', '-cpu', 'max',
            '-accel', 'tcg,thread=multi', '-machine', 'q35', '-display', 'gtk,gl=on' if virgl else 'none',
            '-vga', 'virtio' if desktop == 'niri' else 'std', '-serial', 'stdio', '-monitor', 'none',
            '-device', 'qemu-xhci,id=pointer-usb', '-device', 'usb-tablet,bus=pointer-usb.0',
            '-qmp', f'unix:{qmp_path},server=on,wait=off',
            '-nic', 'user,model=virtio-net-pci', '-cdrom', str(image),
            '-boot', 'order=d', '-no-reboot',
            '-smbios', 'type=1,manufacturer=KestrelOS-Test,product=KestrelOS-Network-Smoke',
        ]
        if virgl:
            command[command.index('-vga')+1] = 'none'
            command += ['-device', 'virtio-vga-gl,xres=1280,yres=800']
        if firmware:
            command += ['-bios', str(firmware.resolve())]
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)
        started = time.monotonic()
        qmp = None
        stream = None
        passed = False

        def monitor(command):
            stream.write(json.dumps(command).encode() + b'\n')
            stream.flush()
            while True:
                response = json.loads(stream.readline())
                if 'error' in response:
                    raise RuntimeError(response['error'])
                if 'return' in response:
                    return response['return']

        try:
            enter_sent = False
            while time.monotonic() - started < timeout:
                for key, _ in selector.select(1):
                    chunk = key.fileobj.read1(65536)
                    if chunk:
                        log.extend(chunk)
                    elif process.poll() is not None:
                        raise RuntimeError(f'QEMU exited with {process.returncode}')
                if qmp is None and qmp_path.exists():
                    qmp = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    qmp.settimeout(60)
                    qmp.connect(str(qmp_path))
                    stream = qmp.makefile('rwb')
                    json.loads(stream.readline())
                    monitor({'execute': 'qmp_capabilities'})
                if stream and not enter_sent and time.monotonic() - started > 15:
                    monitor({'execute': 'human-monitor-command', 'arguments': {'command-line': 'sendkey ret'}})
                    enter_sent = True
                if b'KESTREL_SMOKE_FAIL' in log:
                    raise RuntimeError('Guest reported a failed network/browser check')
                if b'KESTREL_SMOKE_PASS' in log:
                    break
            else:
                raise TimeoutError('Linux boot/network/browser smoke test timed out')
            marker = b'KESTREL_BROWSER_PNG_BASE64='
            encoded = bytes(log).split(marker, 1)[1].splitlines()[0].strip()
            png = base64.b64decode(encoded, validate=True)
            if not png.startswith(b'\x89PNG\r\n\x1a\n'):
                raise RuntimeError('Firefox did not generate a PNG')
            (output / f'linux-{mode}-firefox.png').write_bytes(png)
            if guest_only:
                for name in ('tiling', 'quick', 'welcome'):
                    marker = ('KESTREL_'+name.upper()+'_PNG_BASE64=').encode()
                    if marker in log:
                        png = base64.b64decode(bytes(log).split(marker, 1)[1].splitlines()[0].strip(), validate=True)
                        if not png.startswith(b'\x89PNG\r\n\x1a\n'):
                            raise RuntimeError('Invalid guest desktop screenshot')
                        (output/f'linux-{mode}-{name}.png').write_bytes(png)
                if desktop == 'niri' and b'KESTREL_DESKTOP_FEATURES_PASS' not in log:
                    raise RuntimeError('Niri desktop feature checks did not pass')
                with image.open('rb') as image_stream:
                    digest = hashlib.file_digest(image_stream, 'sha256').hexdigest()
                result = {'mode': mode, 'iso_sha256': digest, 'desktop_profile': desktop,
                          'desktop': True, 'guest_dns_tcp_https': True, 'firefox_rendered': True,
                          'desktop_features': desktop == 'niri', 'host_input_tested': False,
                          'physical_ax211_tested': False}
                (output/f'linux-{mode}-smoke.json').write_text(json.dumps(result, indent=2)+'\n')
                passed = True
                print(f'{mode.upper()}: guest desktop/features, HTTPS and Firefox: PASS (host input not tested)')
                return
            # Exercise the normal desktop launcher too, rather than claiming a
            # headless render proves that the graphical browser is usable.
            def key(name):
                monitor({'execute': 'human-monitor-command',
                         'arguments': {'command-line': 'sendkey ' + name}})
            import sys
            sys.path.insert(0, str(ROOT / 'tools'))
            from preview_desktop import convert

            def capture(name):
                ppm = pathlib.Path(work) / 'desktop.ppm'
                monitor({'execute': 'screendump', 'arguments': {'filename': str(ppm)}})
                convert(ppm)
                shutil.copyfile(ppm.with_suffix('.png'), output / name)

            capture(f'linux-{mode}-before-input.png')

            def type_text(value):
                keys = {' ': 'spc', '-': 'minus', ':': 'shift-semicolon', '/': 'slash', '.': 'dot'}
                for char in value:
                    key(keys.get(char, char));time.sleep(.15)

            if showcase:
                capture('linux-custom-desktop.png')
                key('meta_l-spc');time.sleep(5)
                capture('linux-custom-apps.png')
                key('esc');time.sleep(.5)
                # Open the real Control Center dock launcher. This also tests
                # the shipped dock entry rather than relying on shortcut focus.
                import struct
                width, height = struct.unpack('>II', (output/'linux-custom-desktop.png').read_bytes()[16:24])
                if desktop == 'niri':
                    key('meta_l-comma')
                else:
                    monitor({'execute': 'input-send-event', 'arguments': {'events': [
                    {'type': 'abs', 'data': {'axis': 'x', 'value': int((width/2+96)/width*32767)}},
                    {'type': 'abs', 'data': {'axis': 'y', 'value': int((height-23)/height*32767)}},
                    ]}})
                    time.sleep(1)
                    for down in (True, False):
                        monitor({'execute': 'input-send-event', 'arguments': {'events': [
                            {'type': 'btn', 'data': {'button': 'left', 'down': down}}]}})
                        time.sleep(.2)
                time.sleep(15)
                capture('linux-custom-settings.png')
                key('alt-f4');time.sleep(1)
            key('meta_l-b' if desktop == 'niri' else 'alt-f2')
            # A software-emulated first launch can take several seconds. Wait
            # for focus before typing so the executable name isn't lost.
            time.sleep(5)
            if desktop != 'niri':
                key('ctrl-a')
                time.sleep(.3)
                type_text('firefox-esr https://example.com/')
                key('ret')
            time.sleep(60)
            capture(f'linux-{mode}-desktop.png')
            if desktop == 'niri' and (output/f'linux-{mode}-before-input.png').read_bytes() == (output/f'linux-{mode}-desktop.png').read_bytes():
                raise RuntimeError('Display did not change after graphical launcher/browser input; inspect screenshots')
            with image.open('rb') as image_stream:
                digest = hashlib.file_digest(image_stream, 'sha256').hexdigest()
            result = {
                'mode': mode, 'iso_sha256': digest, 'desktop_profile': desktop,
                'desktop': True, 'guest_dns_tcp_https': True, 'firefox_rendered': True,
                'physical_ax211_tested': False,
            }
            (output / f'linux-{mode}-smoke.json').write_text(json.dumps(result, indent=2) + '\n')
            passed = True
            print(f'{mode.upper()}: Linux desktop, NAT networking, verified HTTPS and Firefox render: PASS')
        finally:
            (output / f'linux-{mode}-serial.log').write_bytes(log)
            if stream and not passed:
                try:
                    ppm = output / f'linux-{mode}-last.ppm'
                    monitor({'execute': 'screendump', 'arguments': {'filename': str(ppm)}})
                except (OSError, ValueError, RuntimeError):
                    pass
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            selector.close()
            if stream:
                try:
                    stream.close()
                except OSError:
                    pass
            if qmp:
                qmp.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', type=pathlib.Path, default=ROOT / 'rovaos-xfce.iso')
    parser.add_argument('--firmware', type=pathlib.Path)
    parser.add_argument('--timeout', type=int, default=600)
    parser.add_argument('--showcase', action='store_true')
    parser.add_argument('--desktop', choices=('xfce', 'niri'), default='xfce')
    parser.add_argument('--virgl', action='store_true', help='Use a 3D virtual GPU and host GTK/OpenGL display (requires a graphical host)')
    parser.add_argument('--guest-only', action='store_true', help='Use guest feature checks/screenshots; skip host QMP screenshots and input tests')
    args = parser.parse_args()
    smoke(args.image, args.firmware, args.timeout, args.showcase, args.desktop, args.virgl, args.guest_only)
