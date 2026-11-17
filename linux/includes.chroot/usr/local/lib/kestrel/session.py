"""Truthful live/persistent status, based on the filesystem backing overlay writes."""
import json
import os
import pathlib
import subprocess


def session_status():
    result = {'persistent': False, 'description': 'Temporary session — changes are lost at shutdown.',
              'free_bytes': 0, 'source': ''}
    try:
        if os.geteuid() != 0:
            cached = json.loads(pathlib.Path('/run/kestrel-session.json').read_text())
            if cached.get('persistent') is True:
                stats = os.statvfs('/')
                cached['free_bytes'] = stats.f_bavail*stats.f_frsize
                cached['total_bytes'] = stats.f_blocks*stats.f_frsize
            return cached
        root = json.loads(subprocess.check_output(
            ['findmnt', '--json', '--target', '/', '--output', 'OPTIONS'], text=True))['filesystems'][0]
        options = dict(part.split('=', 1) for part in root['options'].split(',') if '=' in part)
        upper = options.get('upperdir')
        if not upper:
            return result
        backing = json.loads(subprocess.check_output(
            ['findmnt', '--json', '--target', upper, '--output', 'SOURCE,FSTYPE,OPTIONS'],
            text=True))['filesystems'][0]
        # A writable block-backed upper layer, not merely an attached partition.
        if backing['source'].startswith('/dev/') and backing['fstype'] in ('ext4', 'ext3', 'ext2') and 'rw' in backing['options'].split(','):
            stats = os.statvfs('/')
            result.update(persistent=True, description='Persistent USB — settings and files survive shutdown.',
                          free_bytes=stats.f_bavail*stats.f_frsize,
                          total_bytes=stats.f_blocks*stats.f_frsize, source=backing['source'])
    except (OSError, subprocess.CalledProcessError, KeyError, ValueError, IndexError):
        result['description'] = 'Persistence not confirmed — treat this session as temporary.'
    return result
