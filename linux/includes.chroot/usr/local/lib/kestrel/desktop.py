"""Small, testable desktop helpers. No root privileges or disk formatting."""
import collections
import datetime
import json
import os
import pathlib
import shutil
import subprocess
import tarfile


def tile_plan(windows):
    """Resize each column once; floating dialogs never count as columns."""
    groups = collections.defaultdict(dict)
    for window in windows:
        position = window.get('layout', {}).get('pos_in_scrolling_layout')
        workspace = window.get('workspace_id')
        if not window.get('is_floating') and workspace is not None and position:
            groups[workspace].setdefault(position[0], window['id'])
    return {window: 100 / len(columns) for columns in groups.values()
            for window in columns.values()}


def status_module(status):
    if not status.get('persistent'):
        return {'text': 'Temporary', 'class': 'temporary',
                'tooltip': status['description'] + '\nClick to set up USB saving.'}
    free = status['free_bytes']
    total = status.get('total_bytes', 0)
    low = free < 256 * 2**20 or (total > 0 and free / total < .1)
    return {'text': f'Saving · {free / 2**30:.1f}G free',
            'class': 'low-space' if low else 'persistent',
            'tooltip': ('LOW SAVE SPACE\n' if low else '') + status['description']
                       + '\nUnencrypted. Back up before reflashing.'}


def view_alignment(windows):
    """Bring the first resized column into view, restoring the active window."""
    windows = list(windows)
    focused = next((w for w in windows if w.get('is_focused')), None)
    if not focused or focused.get('is_floating'):
        return []
    tiles = [w for w in windows if not w.get('is_floating')
             and w.get('workspace_id') == focused.get('workspace_id')
             and w.get('layout', {}).get('pos_in_scrolling_layout')]
    if not tiles:
        return []
    first = min(tiles, key=lambda w: w['layout']['pos_in_scrolling_layout'])
    return [first['id'], focused['id']] if first['id'] != focused['id'] else []


def backup_home(home, destination):
    """Export regular files and symlinks, never traverse mounts or follow links."""
    home, destination = pathlib.Path(home).resolve(), pathlib.Path(destination).resolve()
    if destination == home or home in destination.parents:
        raise ValueError('Choose a folder outside your home, preferably another USB.')
    if os.stat(home).st_dev == os.stat(destination).st_dev:
        raise ValueError('Choose a separate mounted filesystem, not this live/save filesystem.')
    device = os.stat(home).st_dev
    files = []
    for root, dirs, names in os.walk(home, followlinks=False):
        root = pathlib.Path(root)
        dirs[:] = [name for name in dirs
                   if (root / name).relative_to(home).as_posix() not in
                   ('.cache', '.local/share/Trash')
                   and (root / name).lstat().st_dev == device]
        for name in names + [name for name in dirs if (root / name).is_symlink()]:
            path = root / name
            info = path.lstat()
            if info.st_dev == device and (path.is_symlink() or path.is_file()):
                files.append((path, info.st_size))
    needed = sum(size for _, size in files) + len(files) * 2048 + 2**20
    if shutil.disk_usage(destination).free < needed:
        raise ValueError('Not enough free space at the backup destination.')
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    target = destination / f'rova-home-{stamp}.tar.gz'
    partial = target.with_suffix(target.suffix + '.partial')
    try:
        with partial.open('xb') as stream:
            with tarfile.open(fileobj=stream, mode='w:gz', dereference=False) as archive:
                for path, _size in files:
                    archive.add(path, arcname='home/' + path.relative_to(home).as_posix(), recursive=False)
            stream.flush()
            os.fsync(stream.fileno())
        partial.rename(target)
    except Exception:
        partial.unlink(missing_ok=True)
        raise
    return target


def reset_desktop(home, defaults):
    """Keep the old settings intact beside freshly copied shipped defaults."""
    folder = pathlib.Path(home) / '.config/niri'
    defaults = pathlib.Path(defaults)
    if not (defaults / 'config.kdl').is_file():
        raise ValueError('Packaged recovery defaults are missing.')
    saved = folder.with_name('niri.backup-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    if folder.exists() or folder.is_symlink():
        folder.rename(saved)
    folder.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(defaults, folder)
    return saved


def autotile():
    """Event-driven IPC, no focus stealing and no periodic compositor polling."""
    windows = {}
    previous = None
    process = subprocess.Popen(['niri', 'msg', '--json', 'event-stream'], stdout=subprocess.PIPE, text=True)
    try:
        for line in process.stdout:
            event = json.loads(line)
            if 'WindowsChanged' in event:
                windows = {w['id']: w for w in event['WindowsChanged']['windows']}
            elif 'WindowOpenedOrChanged' in event:
                window = event['WindowOpenedOrChanged']['window']
                if window.get('is_focused'):
                    for old in windows.values():
                        old['is_focused'] = False
                windows[window['id']] = window
            elif 'WindowFocusChanged' in event:
                for window in windows.values():
                    window['is_focused'] = window['id'] == event['WindowFocusChanged']['id']
                continue
            elif 'WindowClosed' in event:
                windows.pop(event['WindowClosed']['id'], None)
            elif 'WindowLayoutsChanged' in event:
                for identity, layout in event['WindowLayoutsChanged']['changes']:
                    if identity in windows:
                        windows[identity]['layout'] = layout
            else:
                continue
            # Width changes don't alter this signature, avoiding resize feedback loops.
            signature = sorted((w['id'], w.get('workspace_id'), w.get('is_floating'),
                                tuple(w.get('layout', {}).get('pos_in_scrolling_layout') or ()))
                               for w in windows.values())
            if signature == previous:
                continue
            previous = signature
            for identity, width in tile_plan(windows.values()).items():
                subprocess.run(['niri', 'msg', 'action', 'set-window-width', '--id', str(identity),
                                f'{width:.6f}%'], stdout=subprocess.DEVNULL, check=False)
            # Niri preserves the active column's viewport anchor when other
            # columns shrink. Refit the range, ending on the original focus.
            for identity in view_alignment(windows.values()):
                subprocess.run(['niri', 'msg', 'action', 'focus-window', '--id', str(identity)],
                               stdout=subprocess.DEVNULL, check=False)
    finally:
        process.terminate()
        process.wait()
