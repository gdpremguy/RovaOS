"""Stop only our build process group before its backing volume runs out of space."""
import argparse
import os
import pathlib
import shutil
import signal
import subprocess
import sys


def guarded(command, filesystem, minimum_free, start_free, check_only=False):
    free = shutil.disk_usage(filesystem).free
    if free < start_free:
        print(f'Not enough space on {filesystem}: {free / 2**30:.1f} GiB free; '
              f'{start_free / 2**30:.1f} GiB required before building.', file=sys.stderr)
        return 2
    if check_only:
        return 0
    if not command:
        raise ValueError('A build command is required')
    process = subprocess.Popen(command, start_new_session=True)

    def stop():
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()

    try:
        while True:
            try:
                return process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                free = shutil.disk_usage(filesystem).free
                if free < minimum_free:
                    print(f'Stopping RovaOS build: {filesystem} has only '
                          f'{free / 2**30:.1f} GiB free. Downloads are retained.', file=sys.stderr)
                    stop()
                    return 3
    finally:
        stop()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--filesystem', type=pathlib.Path, required=True)
    parser.add_argument('--minimum-free-gib', type=float, default=3)
    parser.add_argument('--start-free-gib', type=float, default=8)
    parser.add_argument('--check-only', action='store_true')
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if args.minimum_free_gib <= 0 or args.start_free_gib < args.minimum_free_gib:
        parser.error('Start space must be at least the positive minimum free space')
    sys.exit(guarded(command, args.filesystem, int(args.minimum_free_gib * 2**30),
                     int(args.start_free_gib * 2**30), args.check_only))
