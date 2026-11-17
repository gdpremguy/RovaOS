# Display, performance and clock defaults

- The X11 desktop defaults to 125% whole-screen enlargement using a RandR
  0.8 transform, not a font/DPI override. Native output resolution is retained;
  the logical desktop is smaller (1920×1200 becomes 1536×960). Fractional
  interpolation can soften text and costs some GPU work.
- Existing user `displays.xml` settings take precedence. Open Control Center →
  Display to change and save your preferred settings. Multiple active screens
  and screens that would have less than 800×600 logical space are left alone.
  Drivers rejecting the transform are restored to native scaling.
- Compositing and window/popup shadows default off to reduce graphics overhead.
  Existing persistent users retain their saved window-manager preferences.
- Adelaide is UTC+10:30 during daylight saving (including November 2026), and
  UTC+09:30 in winter. Both the system and panel use Australia/Adelaide.
  Explicit Australian NTP servers and fallback servers correct the system clock
  when connected. No fixed -90 minute correction is applied.
- If the clock is still wrong, run `kestrel-clock-report` on the affected laptop
  and share its output. A timezone alone cannot fix an incorrectly set hardware
  clock or a failed network-time sync. Do not change the PC's RTC speculatively.
