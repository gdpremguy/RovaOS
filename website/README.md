# RovaOS download website

A static, mobile-friendly site centred on RovaOS's main feature: a workspace
that travels on a USB between compatible PCs. No analytics, external fonts,
framework, account, or backend is required.

The website guides downloads and USB setup. It is **not** an internal-drive
installer and cannot flash a USB from a browser.

## Build and preview

First rebuild and verify `rovaos.iso` using the Linux image tools. Then:

```powershell
python -B website/build.py
python -m http.server 8765 --bind 127.0.0.1 --directory build/website
```

Open <http://127.0.0.1:8765>. Stop the server with Ctrl+C. Serve the generated
directory, not the project root (which contains private captures and save images).

The builder checks that this is a RovaOS Linux ISO and that its SHA-256 matches
`rovaos.iso.sha256`. It copies the ISO, checksum, wallpaper, and site into
`build/website/`, and fills the page's download size, UTC build date and hash.
`release.json` records exactly which image the page offers. The large ISO copy
needs additional disk space; generated website output is covered by `/build/`
in `.gitignore`. Do not upload the unrendered HTML template.

## Publish

No domain or hosting account is configured by this project. Building does not
make the site public.

**Single host:** upload the contents of `build/website/` to an HTTPS static host
that allows large downloads. Keep `downloads/rovaos.iso` and its checksum together.
Make sure `.iso` files are served as downloads (`application/octet-stream` is
fine), HTTPS is enabled, and download bandwidth/file-size limits are adequate.
Do not expose the builder's directory or the entire project.

**Small website + separate ISO hosting (recommended):**

1. Upload the verified ISO to a GitHub Release or HTTPS object storage such as
   Cloudflare R2. Upload the matching checksum too.
2. Use its **direct public asset URL**, not a release HTML page:

   ```powershell
   python -B website/build.py --download-url "https://YOUR-HOST/YOUR-RELEASE/rovaos.iso"
   ```

   Replace the example with the real URL. This mode does not copy the ISO.
3. Upload the generated small website to your static host. If using GitHub Pages,
   deploy generated website files via an artifact; don't commit the ISO to Git.
   GitHub's normal repository file limit is much smaller than this ISO.
4. Check the public download, checksum, mobile layout and USB guide. Download the
   public ISO and independently compare its hash before sharing the site.

An existing generated directory may retain a previous local ISO when switching
to external hosting. Use a **fresh output directory** with `--output` for the
small-site deployment, or exclude that old ISO from your upload.

## Edit

- `index.html`: copy, setup instructions and accessibility structure.
- `styles.css`: responsive Horizon design.
- `script.js`: optional checksum-copy button; downloads work without JavaScript.
- `assets/mark.svg`: geometric Rova mark.
- `../assets/wallpapers/rova-horizon.png`: desktop illustration background.

The desktop illustration is intentionally labelled; it isn't a screenshot or
a claim of boot testing. Hardware compatibility and preview limitations are
explicit. Don't advertise automatic saving, encryption or universal PC support.
Keep third-party attribution/licences when distributing the OS. Before a broad
release, publish the corresponding source and required licence notices for
software you distribute; this website does not replace those obligations.
