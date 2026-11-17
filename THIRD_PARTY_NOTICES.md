# Third-party software

The root MIT licence applies to original RovaOS scripts, configuration,
documentation, website and Horizon artwork. Horizon's provenance is recorded in
`assets/wallpapers/HORIZON-NOTICE.txt`.

The build downloads software with its **own licences**, including:

- Debian packages and the Linux kernel.
- Niri, built from the pinned upstream source using `linux/build_niri.sh`
  (GPL-3.0-or-later; consult upstream for its dependencies).
- Arc theme, imported by the Rova GTK stylesheet.
- Papirus application icons, DejaVu fonts, Firefox, GRUB and firmware.

These components are not relicensed under MIT. Their upstream source and
copyright notices remain applicable. No vendored kernel libraries, raster font
data, old borrowed wallpaper or prebuilt Niri package are included in this
source-only repository.

Distributing an ISO has additional obligations: retain required notices and
provide corresponding sources, build information or valid source offers where
the individual licences require them. This repository alone is not a complete
source offer for every package in the ISO. Firmware may have separate
redistribution restrictions.
