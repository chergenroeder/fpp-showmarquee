# Matrix Countdown Clock — Development Plan

FPP plugin (`fpp-matrixcountdown`) that shows a live countdown to a target date on a pixel-overlay matrix. It is built on the same base as **fpp-matrixscroller**: a Python daemon, a PHP API proxy, and an HTML settings page inside FPP.

---

## 1. Requirements

| # | Requirement | Notes |
|---|-------------|-------|
| R1 | Three target options, **only one active at a time**: Custom Date, Christmas Day, New Year's Day | Radio group in the UI, stored as one `target.type` value, so two can never be on at once |
| R2 | Custom Date uses a date picker | `<input type="date">`, plus an optional time (default 00:00) |
| R3 | Christmas / New Year's need no date input | Fixed: Dec 25 00:00 and Jan 1 00:00. The date field is hidden when either is chosen |
| R4 | All times are in **local time** | Uses the FPP host's system time zone, with correct handling of daylight saving time |
| R5 | Scroll direction: Left→Right, Right→Left, Top→Bottom, Bottom→Top, plus **Static (centered)** | Plus speed (px/s) and repeat delay, as in the scroller |
| R6 | Number first or number last | UI shows live examples: **"8 Days to Christmas"** vs **"Christmas in 8 Days"** |
| R7 | Font, size and color for the **text** | e.g. "to Christmas" |
| R8 | A separate font, size and color for the **number** | e.g. "8 Days" |
| R9 | Under 1 day left: choose **HH:MM:SS countdown** or **hours only** | "08:14:32 to Christmas" vs "9 Hours to Christmas". Hours-only switches to minutes in the last hour ("45 Minutes to Christmas") |
| R10 | At zero the matrix **goes blank** | No celebration message. Blank through the end of the target day, then Christmas/New Year's (and yearly custom dates) start counting to next year |
| R11 | Custom Date has a **"Repeat every year"** checkbox | Off: blank for good once passed. On: rolls over like Christmas |

---

## 2. The key technical decision: render frames ourselves

The scroller draws with FPP's built-in Text effect (`PUT /api/overlays/model/{name}/text`). That effect allows **one font, one size and one color per message**, and its text is fixed when sent. Two of our requirements rule it out:

- **R7/R8:** the number and the text need different fonts and colors.
- **R9:** an HH:MM:SS timer must change every second while it scrolls.

**Approach:** the daemon draws each frame itself with **Pillow** (Python imaging library) and writes the pixels straight into the overlay model's shared-memory buffer. It turns the model on and off through `PUT /api/overlays/model/{name}/state`, the same call the scroller already uses.

**Buffer protocol (confirmed in FPP source, `src/overlays/PixelOverlayModel.cpp`, 2026-11-10):**
1. `PUT /api/overlays/model/{name}/mmap` makes fppd create `/dev/shm/FPP-Model-Overlay-Buffer-{name}` (it is otherwise created only on first use).
2. Header: three little-endian `uint32` values, `width`, `height`, `flags`. Flags bit 0 = dirty; bits 8–15 = bytes per pixel (0 means 3).
3. Pixel data follows: `width × height × bpp` bytes, row by row from the top-left, in RGB order.
4. Write a frame, then set the dirty bit. On each output frame, fppd copies a dirty buffer of an active model into its channels and clears the bit.
5. `PUT .../state {"State": 1}` (0 = off, 1 = on, 2 = transparent, 3 = transparent RGB).

Benefits:
- As many fonts and colors in one line as we want.
- The timer can tick in the middle of a scroll.
- TrueType/OTF and pixel fonts work, not only the `.pfb` Type1 fonts FPP's Text effect accepts.
- The UI preview can draw the same layout.

**Fallback if the spike in Phase 0 fails:** use FPP's Text effect, with one style for the whole message and the text re-sent on each scroll pass. R8 and a live ticking R9 would be lost, so we only fall back if direct output proves impossible.

---

## 3. Countdown rules

```
now    = datetime.now().astimezone()                      # local, aware
target = resolve_target(cfg, now)                         # local, aware
delta  = target - now
```

**Resolving the target**
- Christmas: Dec 25 00:00 of this year. Once Dec 25 has ended, use next year.
- New Year's Day: Jan 1 00:00 of next year. On Jan 1 itself, use this year's (so it stays blank all day).
- Custom with **Repeat every year** on: the same month, day and time, rolling over the day after, like Christmas. Feb 29 falls on Feb 28 in non-leap years.
- Custom with repeat off: the user's date and time. Once past, the matrix stays blank until a new date is set.

**Choosing the display**

| Condition | Display | Example |
|-----------|---------|---------|
| `delta >= 24h` | **Calendar days** = `target.date() - now.date()` | Dec 17, any time → "8 Days" |
| `delta < 24h`, mode = `hms` | `HH:MM:SS`, ticking | "08:14:32" |
| `1h <= delta < 24h`, mode = `hours` | `ceil(hours)` | 8h10m → "9 Hours" |
| `delta < 1h`, mode = `hours` | `ceil(minutes)` | 44m20s → "45 Minutes" |
| `delta <= 0`, still the target day | **Blank** (model turned off) | — |

- Singular and plural: "1 Day" / "2 Days", "1 Hour" / "2 Hours", "1 Minute" / "2 Minutes". The unit words can be edited, for other languages.
- Days are counted from calendar dates, not 24-hour blocks, so a daylight-saving change (a 23- or 25-hour day) never skips or repeats a day.
- **Tests must cover:** a DST change, a leap year (including a yearly Feb 29), the moment after Christmas rolls over, an exact-midnight boundary, the 24h and 1h boundaries, and a custom date in the past (repeat on and off).

**Building the message:** two pieces, each with its own style. The number style covers the number **and** its unit ("8 Days", "08:14:32", "45 Minutes").

| Order | Number piece (number style) | Text piece (text style) | Result |
|-------|-----------------------------|-------------------------|--------|
| Number first | `8 Days` | `to Christmas` | **8 Days to Christmas** |
| Number last | `8 Days` | `Christmas in` | **Christmas in 8 Days** |

The event name ("Christmas", "New Year's Day", or a custom name like "Opening Night") and the joining words ("to" / "in") can each be edited, with sensible defaults.

---

## 4. Config schema (v1)

Stored at `/home/fpp/media/config/plugin.fpp-matrixcountdown.json`, with `config.json` as the bundled defaults.

```json
{
  "global": { "schema_version": 1, "enable_output": true, "fpp_host": "localhost", "fps": 20 },
  "countdown": {
    "enabled": true,
    "model": "",
    "target": {
      "type": "christmas",                 // "custom" | "christmas" | "newyear"
      "custom_date": "2026-12-31",
      "custom_time": "00:00",
      "custom_repeat_yearly": false,
      "event_name": { "custom": "My Event", "christmas": "Christmas", "newyear": "New Year's Day" }
    },
    "layout": {
      "number_position": "first",          // "first" | "last"
      "connector_first": "to",
      "connector_last": "in",
      "units": { "day": "Day", "days": "Days", "hour": "Hour", "hours": "Hours",
                 "minute": "Minute", "minutes": "Minutes" },
      "under_one_day": "hms"               // "hms" | "hours" (minutes in last hour)
    },
    "motion": { "direction": "R2L", "pixels_per_second": 15, "repeat_delay": 0 },
                                           // direction: "L2R" | "R2L" | "T2B" | "B2T" | "static"
    "text_style":   { "font": "DejaVuSans-Bold", "size": 10, "color": "#ff0000", "antialias": false },
    "number_style": { "font": "DejaVuSans-Bold", "size": 12, "color": "#00ff00", "antialias": false }
  }
}
```

---

## 5. Architecture

Kept from the scroller, renamed:

```
fpp-matrixcountdown/
├── pluginInfo.json, menu.inc, plugin.php, api.php    # FPP plugin wiring (proxy to daemon)
├── matrixcountdown.py                                # daemon entry: config, HTTP API, main loop
├── countdown/                                        # pure logic, unit-tested
│   ├── timecalc.py      # resolve_target(), compute_display()
│   ├── message.py       # build the two styled pieces
│   ├── render.py        # Pillow: pieces → image; frame-by-frame scroll position
│   └── output.py        # shared-memory writer + model state on/off
├── matrixcountdown.html                              # settings UI with live preview
├── fonts/                                            # bundled pixel fonts that suit small matrices
├── commands/                                         # FPP commands: on/off, switch target
├── scripts/                                          # install/uninstall, postStart/preStop, daemon_lib
└── tests/                                            # pytest: time math, message, render snapshots
```

- **Daemon port:** 32330, so it can run beside the scroller on 32329.
- **Main loop:** one thread, capped at `fps` (default 20, fppd's idle output rate). After writing a frame it waits for fppd to clear the dirty bit before writing the next, so it follows fppd's real rate (faster while a sequence plays at 40 fps). Each tick computes the countdown (cheap), redraws the message image only when the text changes (once a second at most), places the scroll position from elapsed time × px/s (so speed doesn't depend on frame rate), and writes the frame.
- **One countdown on one overlay model** in v1. It must be a different model from any Matrix Scroller uses; the settings page warns if the chosen model is also set in the scroller's config.

---

## 6. Phases

### Phase 0 — Spike on real FPP hardware ✅ passed 2026-11-10
Test script: `sudo python3 scripts/spike_overlay.py --model "<model>"` (run on the player). It covers every item below and prints a report.
- [x] Find the shared-memory buffer name and layout in FPP source (see Section 2).
- [x] Confirm that name and layout on a real player: FPP 10.3, model "P5 Panel" 192×96. Buffer `/dev/shm/FPP-Model-Overlay-Buffer-P5 Panel`, 55,312 bytes (192×96×3 + a 16-byte header), flags `0x300` = 3 bytes per pixel.
- [x] Test pattern: red, green, blue and white, the top-left corner pixel, and the left-to-right bar all looked right on the matrix.
- [x] Pillow 11.1.0 is present. Two-colour "8 Days to Christmas" scrolled correctly.
- [x] Frame rate: fppd picked up **every** frame (481/481), about 50 ms after each write, so it outputs at **20 fps** when idle. That is fppd's own output rate, so writing faster is wasted. Load average stayed at 0.00.
- [x] Root required: the test fails as the `fpp` user (see Phase 4).
- **Outcome:** direct buffer output works, so the fallback in Section 2 is not needed.

### Phase 1 — Scaffold (½ day)
- [x] Copy the plugin wiring from the scroller: `pluginInfo.json`, `menu.inc`, `api.php` proxy, `daemon_lib.sh`, install/uninstall, postStart/preStop.
- [x] Rename everything (`ms_` → `mc_`, matrixscroller → matrixcountdown, port 32330, log file, config path).
- [x] Bare daemon: loads config (laid over the bundled defaults), validates on save, serves `status`/`config`/`models`/`fonts`/`version`/`reload`/daemon stop/restart, follows FPP's plugin log level. Tested locally.
- [x] New `pluginInfo.json` privacy block.
- [ ] New icon (`icon.png` is the scroller's for now).
- [ ] Create the GitHub repo `chergenroeder/fpp-matrixcountdown`; `pluginInfo.json` already points there.
- [ ] Install on FPP from the repo and check the menu page, API proxy and autostart.

### Phase 2 — Countdown engine (1 day)
- [x] `resolve_target()` with Christmas, New Year and yearly-custom rollover after the target day ends (`countdown/timecalc.py`).
- [x] `compute_display()` covering days / HMS / hours / minutes / blank, plus singular and plural.
- [x] `build_message()` for number-first and number-last (`countdown/message.py`).
- [x] Test suite with an injected clock, covering all edge cases from Section 3: 40 tests using stdlib `unittest`, so the player needs nothing extra. Run them with `python3 -m unittest discover -s tests -v`.
- [x] The daemon's `status` reports the resolved target and the current message.

Notes from building it:
- Remaining time is subtracted in UTC. Python subtracts two datetimes that share a time zone by wall clock, which would count a 23-hour DST day as 24 hours.
- With a midnight target (Christmas, New Year's), "1 Day" shows for only one second. The whole day before is under 24 h, so it shows HH:MM:SS or hours.

### Phase 3 — Renderer ✅ done 2026-11-10 (`countdown/render.py`)
- [x] Load fonts with Pillow (`ImageFont.truetype`), with Pillow's built-in font when a font can't be loaded. The daemon already lists bundled fonts, `media/fonts` and the system fonts.
- [x] Draw the two pieces on one baseline with mixed sizes. Digits sit in fixed-width boxes, so HH:MM:SS keeps one width as it ticks. Antialiasing is off by default (crisp single-colour pixels) and can be switched on per style.
- [x] Movement for all four directions, entering and leaving the edge fully. Position comes from elapsed time × px/s, so speed doesn't depend on frame rate. A changing number doesn't restart the pass, and the repeat delay blanks the panel between passes.
- [x] Top→Bottom / Bottom→Top / Static: two centered lines when one line is wider than the panel, then each line is shrunk until it fits.
- [x] Static: centered, redrawn in place.
- [x] 25 renderer tests (65 in total; they skip cleanly where Pillow isn't installed). Checked by eye with `scripts/render_preview.py`, which writes an LED-style contact sheet and one GIF per direction. Golden PNGs weren't used because font rendering differs between machines.
- [ ] Bundle a few pixel fonts that suit small matrices (optional; the system fonts work).

### Phase 4 — FPP output (1 day)
- [ ] `output.py`: map the buffer, write frames, turn the model on at start and off on stop or disable.
- [ ] Reconnect if FPP restarts or the model is renamed or removed (re-open the buffer, log once).
- [ ] Honor `enable_output` and the repeat delay.
- [ ] **The daemon must run as root.** fppd (root) creates the buffer with mode 0644, so only root can write to it. This was found on FPP 10.3, where the test failed as the `fpp` user. postStart/install already run as root. The web UI's Start button runs as `fpp`, so it must launch the daemon with `sudo` (FPP gives `fpp` passwordless sudo; check this on the player). If the buffer still can't be opened, report "permission denied: daemon is not root" in `status` and on the page instead of failing silently.

### Phase 5 — Web UI (2 days)
- [ ] Target: radio buttons **Custom / Christmas / New Year's**. The date and time pickers and the **Repeat every year** checkbox show only for Custom. Event name field. Next-target readout ("Counting down to Fri Dec 25 2026, 00:00 local").
- [ ] Layout: number-first / number-last radios with the live examples **"8 Days to Christmas"** / **"Christmas in 8 Days"**, plus connector and unit text fields.
- [ ] Under 1 day: radios **HH:MM:SS countdown** / **Hours only (minutes in the last hour)**, with examples.
- [ ] Motion: direction dropdown (L→R, R→L, T→B, B→T, Static), speed, repeat delay (speed and delay hidden for Static).
- [ ] Two style cards, **Text style** and **Number style**, each with font, size and color.
- [ ] **Live preview** on a canvas sized to the chosen model, drawn in the browser from the same rules (fonts loaded via `@font-face` from the plugin). Alternatively, a `GET preview.png` endpoint where the daemon draws the frame itself (exact match, simpler, no animation).
- [ ] Daemon controls, snapshots, dark/light mode, git commit in the footer (from the scroller).
- [ ] Validation: a custom date in the past (repeat off) shows a warning, and saving requires a model to be chosen.

### Phase 6 — API and FPP commands (½ day)
- [ ] REST: `status` (target, remaining time, current message), `config` GET/POST, `reload`, `preview.png`, daemon start/stop/restart, snapshots.
- [ ] FPP commands: *Countdown On/Off*, *Set Target* (custom/christmas/newyear), so playlists and the scheduler can control it.

### Phase 7 — Hardening and release (1 day)
- [ ] Test on hardware: all five directions × both orders × both under-1-day modes. Use a temporary custom target a few minutes away to test the 1h and zero boundaries, and check the matrix goes blank.
- [ ] Check the clock: FPP's time must be right (NTP); show the FPP local time and time zone on the status bar.
- [ ] Write the README and API.md, then do a Plugin Manager install test from the URL.

**Rough total: 8–10 working days**, mostly in Phases 3 and 5.

---

## 7. Testing strategy

| Layer | How |
|-------|-----|
| Time math | pytest with an injected `now`, using `zoneinfo` zones such as `America/New_York` to test DST |
| Message building | Table-driven tests over order × mode × singular/plural |
| Rendering | PNG snapshot tests; a visual diff when fonts change |
| Output | Phase 0 spike script reused as a `--test-pattern` daemon flag |
| End-to-end | On hardware, with a custom target a few minutes ahead |

---

## 8. Reuse from fpp-matrixscroller

- **Reused:** `daemon_lib.sh` (start/stop by command line, root checks), `api.php` proxy pattern, config load/save/migrate, snapshots, FPP command scaffolding, FPP log-level integration, UI shell and dark mode, version footer.
- **Not reused:** message fields, song and sequence overrides, the media/animation/idle modes, and the Text-effect sending path.

---

## 9. Decisions (2026-11-10)

| # | Question | Decision |
|---|----------|----------|
| 1 | Number style scope | Covers the number **and** its unit ("8 Days") |
| 2 | Last hour in hours-only mode | Switch to **minutes** ("45 Minutes") |
| 3 | At zero | **Go blank** through the end of the target day; no celebration message |
| 4 | Custom date after it passes | **"Repeat every year"** checkbox; off = blank for good |
| 5 | Panels / countdowns | **One countdown on one model** in v1 |
| 6 | Sharing a model with the scroller | **Separate models**; UI warns on a clash |
| 7 | Vertical scroll, text too wide | **Two lines**, then shrink a piece if still too wide |
| 8 | Static mode | **Yes**, a fifth "Static (centered)" option |
