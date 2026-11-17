# Niri desktop

RovaOS uses Niri, Waybar, Fuzzel, foot, mako and Rova Settings. Niri is compiled
from the revision pinned in `../build_niri.sh`; no prebuilt compositor is
committed. See [build instructions](../README.md).

## Configuration

- `config.kdl`: window management, outputs, environment and key bindings.
- `waybar.json`, `waybar.css`: grouped top bar, outline and soft shadow.
- `fuzzel.ini`: application launcher.
- `../includes.chroot/`: installed helpers, GTK overrides and shared content.

The default wallpaper is Rova Horizon. `Rova-Summit` remains the internal GTK
identifier for compatibility with existing preferences.

## Controls

- Super+Space: applications.
- Super+Enter: terminal; Super+B: browser.
- Super+comma: Rova Settings; Super+S: quick settings.
- Super+arrows: focus; Super+Ctrl+left/right: move columns.
- Super+O: overview; Super+V: toggle floating.
- Super+Shift+E: confirmed logout.

Use Display & monitors to test scale/layout changes; unconfirmed changes revert.
Saving & backup exports home files/settings, not a complete system image.
Recover desktop preserves the previous Niri configuration in a dated backup.
Firmware recovery entries are not a guarantee of graphical support on every GPU.

USB saves and backup archives are unencrypted. Set a live-account password before
using manual locking. Automatic locking is not enabled by default.

For desktop-file changes, use `../refresh_niri.sh` only with an existing completed
builder, then run `../verify.py` against the resulting ISO. Existing persistent
preferences can override new defaults.
