# Customising Rova

## 1. Edit the right file

These files are in **`linux/includes.chroot/usr/share/rova/`**:

| Want to change… | Edit… |
| --- | --- |
| Names, headline and shared text | `branding.json` |
| Control Center buttons and layout | `control-center.json` |
| Welcome website text and layout | `welcome.template.html` |
| Website colours, fonts and spacing | `welcome.css` |
| Displayed shortcuts | `shortcuts.json` |
| Desktop-specific backup/recovery text | `welcome-profiles.json` |

**Control Center:** edit a button's `label` to rename it, move it in the
`actions` list to reorder it, or set `"enabled": false` to hide it.
`command` is the program and its arguments, for example `["mousepad"]`.
`columns` controls the number of button columns (1–4). Reopen Control Center
to reload its settings.

**Website:** edit the template, not `welcome.html`—that file is generated.
Keep `{{placeholders}}` unless you want to replace their shared text.

Changing `shortcuts.json` only changes the reference text. Actual Niri keys
are set in `linux/niri/config.kdl`.

## 2. Preview the website

Run from the project root:

```sh
python3 linux/render_welcome.py --profile niri
```

Open **`linux/includes.chroot/usr/share/rova/welcome.html`** in your browser.

## 3. Update the ISO

In Linux/WSL, using the existing Niri builder:

```sh
sudo bash linux/refresh_niri.sh
python3 linux/verify.py rovaos.iso
```

Output: **`rovaos.iso`**. Adding packages needs the full builder instead.
Test before distributing, keep saving/encryption warnings accurate, and back up
your USB before reflashing.
