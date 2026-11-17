import importlib.util
import json
import pathlib
import shutil
import struct
import subprocess
import tempfile
import unittest
import uuid
import zlib
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('kestrel_persistent', ROOT/'linux/make_persistent.py')
image = importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(image)


def fixture(path):
    size=1024**2;sectors=size//512
    data=bytearray(size);data[:12]=b'Kestrel test'
    data[510:512]=b'\x55\xaa'
    data[446:462]=struct.pack('<B3sB3sII',128,b'\xfe\xff\xff',0,b'\xfe\xff\xff',64,sectors-64)
    data[462:478]=struct.pack('<B3sB3sII',0,b'\xfe\xff\xff',239,b'\xfe\xff\xff',128,64)
    entries=bytearray(128*128)
    for n,(start,end) in enumerate(((64,sectors-34),(128,191))):
        offset=n*128;entries[offset:offset+16]=uuid.uuid4().bytes_le
        entries[offset+16:offset+32]=uuid.uuid4().bytes_le
        struct.pack_into('<QQQ',entries,offset+32,start,end,0)
    header=bytearray(512)
    struct.pack_into('<8sIIIIQQQQ16sQIII',header,0,b'EFI PART',0x10000,92,0,0,
                     1,sectors-1,64,sectors-34,uuid.uuid4().bytes_le,2,128,128,zlib.crc32(entries))
    struct.pack_into('<I',header,16,zlib.crc32(header[:92]))
    data[512:1024]=header;data[1024:1024+len(entries)]=entries
    data[32768:32775]=b'\x01CD001\x01';data[32768+40:32768+72]=b'KESTREL_LINUX'.ljust(32,b' ')
    options=b'persistence persistence-label=kestrel-rw persistence-media=removable-usb'
    data[40000:40000+len(options)]=options
    path.write_bytes(data)


class PartialImageSafetyTests(unittest.TestCase):
    def test_failed_formatter_removes_only_our_partial(self):
        with tempfile.TemporaryDirectory() as directory:
            source = pathlib.Path(directory)/'source.iso'
            output = pathlib.Path(directory)/'usb.img'
            fixture(source)
            before = source.read_bytes()
            with mock.patch.object(image.shutil, 'which', return_value='mke2fs'), \
                    mock.patch.object(image.subprocess, 'run',
                                      side_effect=subprocess.CalledProcessError(1, 'mke2fs')):
                with self.assertRaises(subprocess.CalledProcessError):
                    image.create_image(source, output, 64*image.MIB)
            self.assertFalse(pathlib.Path(str(output)+'.partial').exists())
            self.assertFalse(output.exists())
            self.assertEqual(source.read_bytes(), before)

    def test_concurrent_partial_is_not_deleted_when_exclusive_open_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            source = pathlib.Path(directory)/'source.iso'
            output = pathlib.Path(directory)/'usb.img'
            partial = pathlib.Path(str(output)+'.partial')
            fixture(source)
            original_open = pathlib.Path.open

            def racing_open(path, mode='r', *args, **kwargs):
                if path == partial and mode == 'xb':
                    partial.write_bytes(b'another build owns this')
                return original_open(path, mode, *args, **kwargs)

            with mock.patch.object(image.shutil, 'which', return_value='mke2fs'), \
                    mock.patch.object(pathlib.Path, 'open', racing_open):
                with self.assertRaises(FileExistsError):
                    image.create_image(source, output, 64*image.MIB)
            self.assertEqual(partial.read_bytes(), b'another build owns this')
            self.assertFalse(output.exists())


@unittest.skipUnless(shutil.which('mke2fs') and shutil.which('debugfs'), 'requires Linux e2fsprogs')
class LinuxPersistenceImageTests(unittest.TestCase):
    def test_new_image_gpt_boot_payload_and_real_ext4_seed(self):
        with tempfile.TemporaryDirectory() as directory:
            directory=pathlib.Path(directory);source=directory/'source.iso';output=directory/'usb.img'
            fixture(source);before=source.read_bytes()
            result=image.create_image(source,output,64*1024**2)
            self.assertEqual(source.read_bytes(),before)
            self.assertFalse(result['encrypted'])
            start=result['persistence_start_sector']*512
            with output.open('rb') as stream:
                self.assertEqual(stream.read(446),before[:446])
                primary,entries=image.read_gpt(stream)
                self.assertEqual(entries[256:272],image.LINUX_FS)
                self.assertEqual(entries[128:144],image.EFI_FS)
                stream.seek(32768);self.assertEqual(stream.read(len(before)-32768),before[32768:])
                backup=struct.unpack_from('<Q',primary,32)[0]
                stream.seek(backup*512);header=bytearray(stream.read(512))
                crc=struct.unpack_from('<I',header,16)[0];struct.pack_into('<I',header,16,0)
                self.assertEqual(zlib.crc32(header[:92]),crc)
                self.assertEqual(struct.unpack_from('<Q',header,32)[0],1)
                table=struct.unpack_from('<Q',header,72)[0]
                stream.seek(table*512);self.assertEqual(stream.read(len(entries)),entries)
                stream.seek(start+1024+56);self.assertEqual(stream.read(2),b'\x53\xef')
                stream.seek(start+1024+120);self.assertEqual(stream.read(16).rstrip(b'\0'),b'kestrel-rw')
                stream.seek(start)
                fs=directory/'save.ext4'
                with fs.open('wb') as target:
                    for _ in range(64):target.write(stream.read(1024**2))
            contents=subprocess.check_output(['debugfs','-R','cat /persistence.conf',str(fs)],text=True)
            self.assertEqual(contents,'/ union\n')
            self.assertEqual(json.loads(pathlib.Path(str(output)+'.json').read_text())['iso_sha256'],result['iso_sha256'])

    def test_existing_image_and_source_are_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            directory=pathlib.Path(directory);source=directory/'source.iso';output=directory/'saved.img'
            fixture(source);output.write_bytes(b'valuable saved settings')
            with self.assertRaises(FileExistsError):image.create_image(source,output,64*1024**2)
            self.assertEqual(output.read_bytes(),b'valuable saved settings')
            with self.assertRaises(FileExistsError):image.create_image(source,source,64*1024**2)

    def test_corrupt_gpt_or_old_nonpersistent_iso_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            directory=pathlib.Path(directory);source=directory/'source.iso';output=directory/'usb.img'
            fixture(source);data=bytearray(source.read_bytes());data[540]^=1;source.write_bytes(data)
            with self.assertRaises(ValueError):image.create_image(source,output,64*1024**2)
            self.assertFalse(output.exists())
            fixture(source);data=bytearray(source.read_bytes());data[40000:40128]=b' '*128;source.write_bytes(data)
            with self.assertRaises(ValueError):image.create_image(source,output,64*1024**2)
            self.assertFalse(output.exists())
