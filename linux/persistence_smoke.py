"""Cold-boot a disposable QCOW2 overlay of the USB image; no physical disks."""
import argparse
import hashlib
import json
import pathlib
import selectors
import socket
import subprocess
import tempfile
import time
import uuid

ROOT = pathlib.Path(__file__).resolve().parents[1]


def boot_phase(disk, phase, token, output, firmware=None, timeout=420, desktop='xfce'):
    mode='uefi' if firmware else 'bios'
    expected=f'KESTREL_PERSIST_{phase.upper()}_PASS'.encode()
    serial=bytearray();passed=False
    with tempfile.TemporaryDirectory(prefix='kestrel-persist-qmp-') as work:
        qmp_path=pathlib.Path(work)/'qmp.sock'
        command=['qemu-system-x86_64','-m','3072','-smp','2','-cpu','max',
                 '-accel','tcg,thread=multi','-machine','q35','-display','none','-vga','virtio' if desktop=='niri' else 'std',
                 '-serial','stdio','-monitor','none','-qmp',f'unix:{qmp_path},server=on,wait=off',
                 '-nic','user,model=virtio-net-pci','-device','qemu-xhci,id=usbhost',
                 '-drive',f'file={disk},format=qcow2,if=none,id=kestrelboot',
                 '-device','usb-storage,drive=kestrelboot,bus=usbhost.0,removable=on,bootindex=1',
                 '-no-reboot','-smbios',
                 f'type=1,manufacturer=KestrelOS-Test,product=KestrelOS-Persist-{phase.title()},serial={token}']
        if firmware:command+=['-bios',str(firmware.resolve())]
        process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        selector=selectors.DefaultSelector();selector.register(process.stdout,selectors.EVENT_READ)
        connection=None;stream=None;started=time.monotonic();enter_sent=False

        def request(command):
            stream.write(json.dumps(command).encode()+b'\n');stream.flush()
            while True:
                response=json.loads(stream.readline())
                if 'error' in response:raise RuntimeError(response['error'])
                if 'return' in response:return response['return']

        try:
            while time.monotonic()-started<timeout:
                for key,_ in selector.select(1):
                    chunk=key.fileobj.read1(65536)
                    if chunk:serial.extend(chunk)
                    elif process.poll() is not None:break
                if connection is None and qmp_path.exists():
                    connection=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);connection.settimeout(10)
                    connection.connect(str(qmp_path));stream=connection.makefile('rwb')
                    json.loads(stream.readline());request({'execute':'qmp_capabilities'})
                if stream and not enter_sent and time.monotonic()-started>15:
                    request({'execute':'human-monitor-command','arguments':{'command-line':'sendkey ret'}})
                    enter_sent=True
                failure=serial.find(b'KESTREL_PERSIST_FAIL')
                if failure>=0 and b'\n' in serial[failure:]:
                    raise RuntimeError(serial[failure:].split(b'\n',1)[0].decode(errors='replace'))
                if expected in serial and not passed:
                    passed=True
                    ppm=output/f'linux-persistence-{mode}-{phase}.ppm'
                    request({'execute':'screendump','arguments':{'filename':str(ppm)}})
                    import sys
                    sys.path.insert(0,str(ROOT/'tools'))
                    from preview_desktop import convert
                    convert(ppm);ppm.unlink()
                if process.poll() is not None:
                    if not passed or process.returncode!=0:raise RuntimeError('Guest exited without a successful clean persistence test')
                    print(f'{mode.upper()} {phase}: persistent settings/files/browser data/network profile and clean shutdown: PASS')
                    return
            raise TimeoutError('Persistent USB boot/test timed out')
        finally:
            (output/f'linux-persistence-{mode}-{phase}.log').write_bytes(serial)
            if process.poll() is None:
                if stream:
                    try:request({'execute':'screendump','arguments':{'filename':str(output/f'linux-persistence-{mode}-failure.ppm')}})
                    except (OSError,ValueError,RuntimeError):pass
                process.terminate()
                try:process.wait(timeout=10)
                except subprocess.TimeoutExpired:process.kill();process.wait()
            selector.close()
            if stream:stream.close()
            if connection:connection.close()


def check(image,firmware=None):
    image=image.resolve()
    if not image.is_file():raise SystemExit(f'Build the persistent image first: {image}')
    with image.open('rb') as stream:
        digest=hashlib.file_digest(stream,'sha256').hexdigest()
    output=ROOT/'build';output.mkdir(exist_ok=True)
    # A small copy-on-write test file; the delivered USB image stays pristine.
    cache=pathlib.Path.home()/'.cache/kestrel-linux';cache.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='persistence-test-',dir=cache) as work:
        disk=pathlib.Path(work)/'test.qcow2'
        subprocess.run(['qemu-img','create','-f','qcow2','-F','raw','-b',str(image),str(disk)],check=True)
        token=str(uuid.uuid4())
        boot_phase(disk,'write',token,output,firmware)
        boot_phase(disk,'read',token,output,firmware)
    mode='uefi' if firmware else 'bios'
    (output/f'linux-persistence-{mode}.json').write_text(json.dumps({
        'mode':mode,'image':image.name,'image_sha256':digest,'cold_boot_persistence':True,
        'appearance_choice_retained':True,'download_retained':True,
        'browser_directory_retained':True,'synthetic_wifi_profile_retained':True,
        'clean_shutdown':True,'physical_wifi_tested':False},indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image',type=pathlib.Path,default=ROOT/'kestrelos-linux-persistent.img')
    parser.add_argument('--firmware',type=pathlib.Path)
    args=parser.parse_args();check(args.image,args.firmware)
