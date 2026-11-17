# RovaOS

A portable Linux desktop that runs from a USB. Enable USB saving to carry your
files and settings between compatible Intel/AMD PCs without installing onto
their internal drives.

The current desktop uses Debian, Niri, Waybar and the Rova Horizon theme.
This is preview software: saves are unencrypted, hardware compatibility varies,
and the ISO alone starts a temporary session. Back up before flashing.

## What's here

| Folder | Purpose |
| --- | --- |
| `linux/` | ISO build scripts, desktop configuration, runtime helpers and saving tools |
| `website/` | Public download website and USB setup guide |
| `assets/wallpapers/` | Original Horizon PNG, editable SVG and provenance note |
| `tools/` | Horizon artwork generator |
| `tests/` | Linux desktop, persistence and website tests |

This repository contains the **current Linux edition only**. The old custom
kernel, its drivers/games, vendored libraries, old build notes and hardware
capture tools are deliberately excluded. No ISOs, saved data, captures, logs,
binary packages or editor state are included.

## Build and contribute

- [Build the ISO](linux/README.md)
- [Edit the desktop](linux/customising-desktop.md)
- [Build or host the download website](website/README.md)
- [USB saving details](linux/usb-persistence.md)

Run tests with Python 3.11+:

```sh
python3 -B -m unittest discover -s tests
```

Linux is recommended; some tests require e2fsprogs or other Linux tools.
Tests that need a built ISO skip until one is available.

Original project code and artwork are [MIT licensed](LICENSE). Downloaded
packages retain their own licences; see [third-party notices](THIRD_PARTY_NOTICES.md).
The MIT licence does not relicense Debian, Linux, Niri or their dependencies.
