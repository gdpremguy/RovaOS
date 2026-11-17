# RovaOS naming and compatibility

The product is **RovaOS**; desktop labels use **Rova**, including **Rova Settings**.
New Niri builds produce `rovaos.iso`; Xfce builds produce `rovaos-xfce.iso`.
The old experimental custom kernel is not included in this repository.

Editable content is in `linux/includes.chroot/usr/share/rova/` and installed in
`/usr/share/rova/`. Public commands include `rova-settings`, `rova-tools`,
`rova-firstboot` and `rova-network-report`.

## What deliberately stays compatible

- The existing persistence label `kestrel-rw` is a disk-format identifier.
  Renaming a brand must not relabel or reformat a user's save partition.
- Persistence tools recognise both `ROVA_LINUX` and `KESTREL_LINUX` ISO IDs,
  with the same GPT, boot-option, identity and removable-device checks.
- Existing `kestrel-*` helpers, service names, runtime markers, build-cache
  paths and the live account/home remain valid. `rova-*` command aliases and
  a compatibility theme/content path avoid breaking saved desktop launchers.
- The pinned compositor package retains its original version identifier and
  binary provenance. No upstream code or third-party attribution is renamed.
- Low-level custom-kernel save/profile magic strings retain their format IDs.

Those are technical compatibility identifiers, not application branding. Existing
ISO/IMG files and their hashes are not renamed or rewritten by the rebrand.
An older full-root persistence overlay can still override shipped files; this
is not a promise of a seamless in-place OS upgrade. Back up before reflashing,
and test a spare USB before relying on saved data. No physical disk migration
or automatic data deletion is performed.
