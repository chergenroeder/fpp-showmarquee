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
- [x] New icon (Phase 7).
- [x] Create the GitHub repo `chergenroeder/fpp-matrixcountdown` (public).
- [x] Install on FPP from the repo and check the menu page, API proxy and autostart.

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

### Phase 4 — FPP output ✅ done and checked on hardware 2026-11-10 (`countdown/output.py`)
- [x] `output.py`: open the buffer (after `PUT .../mmap`), write frames (RGB, or RGBW with white 0), and set the dirty bit. The model is turned on while drawing; it is blanked and turned off when the countdown is blank, disabled, the model changes, or the daemon stops.
- [x] Main loop in the daemon. It waits for fppd to take each frame, so it follows fppd's real rate, capped at `fps`. A config change takes effect at once.
- [x] Reconnect: every 5 s it checks whether fppd has replaced the buffer (an fppd restart) or the model was turned off by something else. It then reopens the buffer or turns the model back on. If opening fails, it retries every 5 s.
- [x] Honor `enable_output`, the countdown's `enabled` switch, and the repeat delay (Phase 3).
- [x] **Root:** the web UI's Start button runs the daemon with `sudo -n`; the log redirect runs as root too, because root owns the log file. If the buffer can't be opened, `status.output.error` says why: not root, model not found, FPP unreachable, or FPP Host isn't this player.
- [x] `status.output` = `{state: drawing|blank|off|error, error, fps, root}`, also shown on the stand-in page.
- [x] 15 tests against a fake fppd (`tests/fake_fpp.py`), covering a real HTTP API, a buffer file and an output thread. They check drawing, going blank and off, stopping, errors and recovery, switching models, fppd restarts, disabling output, RGBW and permissions. 80 tests in total.
- [x] Checked on the player (FPP 10.3, "P5 Panel" 192×96): the Christmas countdown scrolled, Stop then Start from the page worked (the sudo path), and it recovered by itself after an fppd restart.
- [ ] Not done: drawing to a matrix on *another* player. The buffer is local, so FPP Host must be this player. If that's ever wanted, it needs a different output path.

### Phase 5 — Web UI ✅ done and checked on the player 2026-11-10 (`matrixcountdown.html`)
- [x] Target: radio buttons **Christmas / New Year's / Custom**. The date and time pickers and **Repeat every year** show only for Custom. The event name field edits the name of the chosen target. A readout shows the next target in FPP local time.
- [x] Layout: number-first / number-last radios with live examples built from your event name, joining words and units. The joining words and unit words sit under a fold.
- [x] Under 1 day: radios **Countdown timer** / **Hours only**, with examples, and a note on minutes in the last hour and going blank at zero.
- [x] Motion: direction dropdown (Right to Left, Left to Right, Bottom to Top, Top to Bottom, Static); speed and pause are hidden for Static; a two-line note for vertical/static.
- [x] **Number style** and **Text style** cards: font (fonts found on the player, plus "built-in"; a missing font is flagged), size, colour, smooth edges.
- [x] **Live preview** drawn by the daemon itself (`POST preview` with the unsaved settings), so fonts and layout match the matrix exactly. The page animates it with the same motion as the daemon, at the chosen model's size, with an LED-style grid. "Preview as": Now / 8 days out / Under a day. "Now" refreshes every second so the timer ticks.
- [x] Daemon Start/Restart/Stop, a status box (now showing, output state and fps, FPP local time), version footer, Bootstrap variables so FPP's dark mode applies.
- [x] Validation: a past custom date (repeat off) gets a warning and a blank preview. No model gets a warning. A model also used by Matrix Scroller gets a warning (read from the scroller's config if it's installed). The server rejects bad values on Save and says which field. Unsaved changes are marked, and leaving the page asks first.
- [x] `scripts/dev_server.py`: fake fppd + real daemon + an FPP-like page wrapper, for working on the page without a player. Used to check the page at desktop and phone widths, in light and dark mode.
- [x] Checked inside FPP on the player (after the font fallback fix).

### Phase 6 — API and FPP commands ✅ done and checked on the player 2026-11-10
- [x] REST (`/api/plugin/fpp-matrixcountdown/...`): `status`, `config` GET/POST, `reload`, `preview`, `models`, `fonts`, `version`, daemon start/stop/restart, plus:
  - `POST state` `{"enabled": true|false|"toggle"}`: countdown on/off, saved.
  - `POST target` `{"type": "christmas"|"newyear"|"custom", "date", "time", "name", "repeat"}`: only `type` is required; a custom target keeps its saved date, time and name when they're left out. It is saved, and invalid values save nothing.
- [x] FPP commands (`commands/descriptions.json`; registered at install through `callbacks.sh`, as in the scroller):
  - **Matrix Countdown - State**: On / Off / Toggle.
  - **Matrix Countdown - Set Target**: Christmas / New Year's Day / Custom, with optional date, time, event name and repeat.
  - Both talk to the daemon on 127.0.0.1 with a 2 s limit, so a stopped daemon can't hold up fppd's scheduler, and they report its errors.
- [x] Settings **Download / Upload** (JSON) on the page, instead of the scroller's named snapshots: there is only one countdown. An upload is laid over the current settings and must be reviewed and saved.
- [x] 12 tests run the real API handler and the real command scripts (quoting, blank optional args, errors, daemon down). 100 tests in total.
- [x] On the player: both commands appear in FPP's command list and work.

### Phase 7 — Hardening and release (built 2026-11-10)
- [ ] Hardware pass with [TESTING.md](TESTING.md): all five directions × both orders × both under-1-day modes. A custom target a few minutes away covers the 1 h and zero boundaries, then FPP commands and recovery.
- [x] Clock: `status.clock_synced` (from `timedatectl`'s NTPSynchronized) is shown on the status line, with a warning when the clock isn't synced.
- [x] `POST config` now lays a partial body over the **current** settings, not the defaults, so `{"countdown": {"model": "X"}}` no longer resets everything else.
- [x] README.md (install, settings, FPP commands, troubleshooting, development) and API.md (every endpoint, settings reference, Home Assistant example).
- [x] Own icon: a stopwatch whose ring runs down (`scripts/make_icon.py`), replacing the scroller's.
- [ ] Fresh install from the Plugin Manager URL on a player without the plugin (or after uninstalling it).
- [ ] Category **Messaging** ("Messaging, Signage & Countdown"): FPP takes categories only from the central list `FalconChristmas/fpp-data/pluginList.json` (third field of each entry), not from `pluginInfo.json`. Until a pull request adds `["fpp-matrixcountdown", "<pluginInfo URL>", "Messaging", "<date>"]` there, it shows under Other and installs only by URL.

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

---

## Version 2 — Weather from a Tempest station (started 2026-11-10)

Add messages showing the user's WeatherFlow Tempest **temperature** and **wind speed**.

**Decisions**
- Source: the hub's **local UDP broadcast** (port 50222). It needs no internet, account or token, wind updates every ~3 s and temperature every ~1 min. Tempest's cloud REST API (personal token) can be a later fallback for players on another network.
- Units: **°F** and **mph**.

**Protocol** (WeatherFlow UDP reference v143)
- `rapid_wind`: `ob = [epoch, wind m/s, direction °]`, about every 3 s.
- `obs_st`: `obs[0] = [epoch, lull, avg, gust (m/s), direction °, interval s, pressure mb, air temp °C, humidity %, lux, UV, solar W/m², rain mm, precip type, strike km, strikes, battery V, report interval min]`, about every 60 s.
- Also `hub_status` (10 s) and `device_status` (60 s). Listen with `SO_REUSEADDR`/`SO_REUSEPORT` so other listeners (Home Assistant, WeeWX) keep working.

**Check:** `scripts/tempest_listen.py` (no sudo). On this network (2026-11-10, from a Mac), it heard hub **HB-00069444** at 192.168.1.147 with Tempest sensor **ST-00084993**:
- 75 s gave obs_st=4, rapid_wind=49, hub_status=14, device_status=3.
- **Every packet arrived twice** (probably two network interfaces), so the reader must drop duplicates by timestamp.
- A sample reading: 38.2°F, wind 0 mph, pressure 837 mb, humidity 0.0% (suspicious; the sensor may report 0 when it fails), battery 2.68 V.
- [x] Run it on the FPP player: **fpp-matrix.local hears the hub** (2026-11-10). 75 s gave obs_st=2, rapid_wind=25, hub_status=7, device_status=2, **no duplicates** (so the Mac's doubles were its own two interfaces). Reading: 38.0°F, wind 0–1 mph SW/SSW, gust 1 mph. Keep dropping duplicates anyway, since other players may see them.

**Design decisions (2026-11-10)**

| # | Question | Decision |
|---|----------|----------|
| 1 | Sharing the matrix | **Take turns each pass**: countdown, then temperature, then wind, then the countdown again. In Static mode each message holds for a set number of seconds. |
| 2 | Readings | **Temperature, wind speed, wind direction and gusts** |
| 3 | Calm wind (< 1 mph) | **"Calm"**, e.g. "Wind Calm" |
| 4 | Styles | **Reuse the countdown styles**: the reading ("72°F", "8 mph NW") uses the Number style and the words ("Temp", "Wind", "gusts") the Text style. No new style settings. |

**Proposed defaults** (editable in settings; to confirm while building)
- Temperature message: `Temp 72°F` (label editable, may be empty for just `72°F`). Whole degrees.
- Wind message: `Wind 8 mph NW`, with `gusts 15` added when the gust is at least 5 mph above the average. Wind uses the latest `rapid_wind` (3 s) for speed and direction, and the gust from `obs_st`.
- Stale data: a reading older than **5 minutes** is skipped silently, so the countdown just shows more often. The page's status shows the last reading and its age.
- Each weather message can be switched on/off; a master "Weather" switch; the countdown can also be turned off for weather-only.


**Built (2026-11-10)**
- [x] `countdown/weather.py`: `TempestListener`, a background thread on UDP 50222 that shares the port (`SO_REUSEADDR`/`SO_REUSEPORT`). It drops repeats by (sensor, type, epoch), can filter to one sensor, and falls back to the obs_st minute-average wind when rapid_wind stops. `temperature_message()` / `wind_message()` follow the decisions above.
- [x] `Message.lines`: which pieces share a line when a message must split. The wind splits as "Wind 8 mph NW" over "gusts 15"; "Wind Calm" stays on one line.
- [x] Taking turns in the daemon loop: countdown → temperature → wind, skipping any that are blank, stale or off. Messages switch at the end of each pass (`Mover.passes`), before the frame is drawn, so the old message never peeks in; Static switches every `motion.static_hold` seconds. The countdown can be off for weather only.
- [x] Settings (`weather.*`, `motion.static_hold`), validation, `status.weather` and `status.showing`, preview `as: temperature | wind` (live reading or a sample).
- [x] Settings page: a Weather card (switch, temperature/wind toggles and labels, direction, gusts; more options folded), a live weather line in the status box, Temp and Wind preview modes, "Show each message (s)" for Static.
- [x] 19 tests (packets, duplicates, sensor filter, a real UDP socket, messages, two-line layout, taking turns with a fake fppd and live UDP packets). 120 tests in total.
- [x] Live check on the dev server against this network's real hub: `Temp 37°F` and `Wind 2 mph NNE` took turns with the countdown.
- [x] Preview "Now" plays every message in turn when Show weather is on, the same way the matrix does (one pass each, or the hold time when Static), using live weather or a sample. Checked live: "Wind 2 mph NNE" → "45 Days to Christmas" → "Temp 38°F". 5 tests.
- [ ] On fpp-matrix.local: turn on Show weather and watch the countdown, temperature and wind take turns on the P5 Panel.

---

## Review against FPP's plugin template (2026-11-11)

Checked against [FalconChristmas/fpp-plugin-Template](https://github.com/FalconChristmas/fpp-plugin-Template) (`PLUGIN_GUIDELINES.md`, `PLUGIN_SELF_REVIEW.md`, `PLUGININFO_FORMAT.md`, `pluginInfo.schema.json` at f2b3dc2). Fixed:

1. `pluginInfo.json` failed the schema (`systemChanges` kind `packages`). Packages are now declared in `dependencies.packages` (`python3-pil`, `fonts-dejavu-core`): FPP 10+ installs them before `fpp_install.sh`, reference-counts them, and removes them on uninstall. The file passes the schema; privacy texts are within the listing check's length limits (summary ≤ 200, `what` ≤ 150).
2. The overlay model name is checked (`model_name_problem()`: no `/`, `\`, `..` or control characters) both when settings are saved and before the `/dev/shm` path is built, since a root process opens that path.
3. `daemon/start` is a POST, in `api.php`, the page and API.md (no state change on GET).
4. `fpp_install.sh` no longer runs `apt-get update`/`install`; it only warns if Pillow is missing.
5. `versions[]` is FPP 10.0+ only; FPP 9 was never tested.
6. `daemon_lib.sh` sources `${FPPDIR}/scripts/common` for MEDIADIR/LOGDIR (relaxing `set -eu` while it loads), falling back to defaults off-box.
7. The start scripts send the daemon's stdout/stderr to `/dev/null`; the daemon logs uncaught exceptions (main and threads) itself through the rotation-aware `WatchedFileHandler`.
8. The preview's panel background uses Bootstrap's `bg-black` instead of a hex colour.

Tests: 128 (model names, bad model on save, `daemon_lib.sh` loading a `common` stand-in under `set -eu`).

Not changed (optional): deleting settings on a real uninstall with `FPP_PLUGIN_REINSTALL` (FPP 10.4+); settings are kept, as the README says.

- [ ] On fpp-matrix.local: Reinstall through the Plugin Manager (FPP installs the declared packages); check `media/logs/fpp_plugin_manager.log` and that `apache2-error.log` has no `fpp-matrixcountdown` lines; Stop then Start on the page (now a POST).
- [ ] Before submitting to fpp-data: run `pluginInfo.json` through the template's Plugin preview and Privacy disclosure builder.

---

## Version 2.1 — Internet weather from Open-Meteo (planned 2026-11-11)

Let the user pick where the weather comes from: an **internet service (Open-Meteo)** or the **local Tempest**, for players with no Tempest or one on another network.

**Why Open-Meteo** (compared 2026-11-11 with NWS, MET Norway, OpenWeatherMap, Pirate Weather, Tempest cloud)
- No account or API key, so it works with no setup. It covers the whole world.
- Free for non-commercial use (a free, open-source FPP plugin counts), about 10,000 calls/day. Polling every 15 min uses 96.
- It returns the same values the Tempest gives, so the existing `Reading`, `temperature_message()` and `wind_message()` work unchanged.
- Others were set aside for now: NWS is US only and needs two calls; OpenWeatherMap and Pirate Weather need a key; the Tempest cloud API needs a token (a possible third source later).

**API** (checked with a live call, 2026-11-11)
`GET https://api.open-meteo.com/v1/forecast?latitude=..&longitude=..&current=temperature_2m,relative_humidity_2m,wind_speed_10m,wind_direction_10m,wind_gusts_10m&wind_speed_unit=ms&timeformat=unixtime`
- Returns `current = {time (epoch), interval: 900, temperature_2m °C, relative_humidity_2m %, wind_speed_10m m/s, wind_direction_10m °, wind_gusts_10m m/s}`. Asking for °C and m/s keeps the units the Tempest code already converts from.
- Values are model data, updated every 15 min (`interval`), not station readings. Wind is a 10 m estimate, so it can differ from a Tempest on a roof.
- Data is CC BY 4.0: the settings page credits Open-Meteo.

**Decisions (2026-11-11)**

| # | Question | Decision |
|---|----------|----------|
| 1 | Choosing the source | **The user picks.** `weather.source` is `"open-meteo"`, `"tempest"` or `""` (not chosen), and starts as `""`. Turning Weather on shows the two choices with **neither recommended** (Open-Meteo, then the Tempest, labelled as for Tempest owners whose hub is on the same network as the player; changed 2026-11-11); until one is picked, Weather shows nothing and sends nothing. One source at a time; no automatic fallback. (This meets guideline 14.2, which says a feature with a remote provider must not default to it; decided 2026-11-11.) |
| 2 | Location | **FPP's own Latitude/Longitude by default** (FPP **Settings → General**; read live, never copied). The plugin settings can **override** them with the user's own lat/lon. If FPP has no location and none is typed, the page says so and nothing is sent. A city/ZIP lookup can come later. |
| 3 | How often | **Every 15 minutes**, matching Open-Meteo's 15-minute update. Fetch shortly after each quarter hour (:01, :16, :31, :46) so each fetch gets new data. Not a setting. |
| 4 | Stale data | Too old after **3 × 15 = 45 minutes**. A failed fetch keeps the last good reading until then and retries after 1, 2, 4, 8 min, then every 15. The Tempest keeps its own 5-minute limit. |
| 5 | Gusts | `wind_gusts_10m`, with the same "gust at least N mph above the average" rule. |
| 6 | Privacy | The location goes only to api.open-meteo.com, only while Weather is on with that source. The page says so next to the choice. |

**FPP plugin standards check** (against the template guidelines reviewed above, f2b3dc2)

| Guideline | What 2.1 does |
|---|---|
| 14.1 Name every off-box recipient | A `privacy.sends` entry: to `https://api.open-meteo.com`, what "this player's latitude and longitude, rounded to about 1 km", why "to get the current temperature and wind", `alwaysOn: false`. Open-Meteo is named in the `description`, and the `summary` (≤ 200 chars) is rewritten to cover both sources. |
| 14.2 Off until turned on; remote features default to local | Weather is off by default, and no source is preselected: the user picks Open-Meteo or the Tempest, with neither recommended. So no default setting sends anything, and the remote provider is never chosen for them. |
| 14.3 Send only what's needed | Only lat/lon, **rounded to 2 decimals** (about 1 km; Open-Meteo's grid is coarser anyway), and the fixed list of fields. No hostname, serial or FPP version. The User-Agent names the plugin only. |
| 14.11 Personal data in `plugindata/` | A typed-in location is personal data about where the user lives. It is stored in `<mediadir>/plugindata/fpp-matrixcountdown/location.json`, mode `0600`, not in `config/` (which goes into crash bundles and backups). FPP's own Latitude/Longitude are read when needed, never copied. Coordinates are kept out of the log at the default level. |
| Red light: "Sends unencrypted to the internet" | HTTPS only. |
| Self-review: outbound call with no timeout, retry with no cap | 10 s timeout; retries capped at 15 min apart; the poller thread catches its own errors (the `threading.excepthook` from the template review is only a last resort). |
| Self-review: offline box, clock a day wrong | Show the real reason on the page: "no internet", "Open-Meteo didn't answer", or for a certificate error "check this player's date and time" (FPP **Settings → Time**), not just "check your internet". Every error the daemon reports appears in the status line, never a stuck "Waiting…". |
| CSP: no off-box page loads | The page loads nothing from Open-Meteo; the credit is a plain link. |
| No new packages | `urllib.request` and `ssl` from the standard library; `dependencies.packages` is unchanged. |
| No state change on GET | Saving the source or location goes through the existing `POST config`. A future "Find city" lookup would be a GET that changes nothing. |

**Build steps**
- [ ] `countdown/weather.py`: `OpenMeteoPoller`, a background thread with the same interface as `TempestListener` (`start`, `stop`, `reading()`, `running`, `error`). It fetches over HTTPS with `urllib.request` (10 s timeout, plugin User-Agent), at :01/:16/:31/:46, with the retry rule above. It fills a `Reading` with `source = "open-meteo"`, timing each value from the `current.time` the server returns. Error texts as in the standards table.
- [ ] Location: a `location()` helper that uses the override from `plugindata/.../location.json` (0600) if set, else FPP's `Latitude`/`Longitude` from `/api/settings` on this player (to verify on fpp-matrix.local, which didn't answer on 2026-11-11). It rounds to 2 decimals and reports where the location came from ("FPP settings" or "set here").
- [ ] `_ensure_listener()`: start whichever source the settings ask for; restart when the source or location changes.
- [ ] Settings: `weather.source` in `config.json` (default `""`; validation accepts `""`, `"open-meteo"`, `"tempest"`); `weather.location_override` (on/off) and the coordinates kept in `plugindata`, written by `POST config`. Validation: lat −90 to 90, lon −180 to 180, and a clear error when no location is available. A saved config with Weather on and no `source` (built before 2.1) is treated as `tempest`, so an existing setup doesn't start sending.
- [ ] `weather_status()`: with no source picked, say "choose a weather source"; otherwise show the source, where the location came from, the last fetch time and any error. The status line reads e.g. "Open-Meteo: 38°F, wind 7 mph W (updated 4 min ago)".
- [ ] Settings page: a Weather source choice with nothing selected at first: "Internet: Open-Meteo" then "Tempest weather station (for Tempest owners whose hub is on the same network as this player)", with the recipient named beside Open-Meteo. Turning Weather on with no source picked highlights the choice, and Save says one is needed for weather to show. Open-Meteo shows "Location: FPP settings (40.01, −100.00)" plus an "Use a different location" switch with lat/lon fields; Tempest shows its port and sensor options. Credit link to Open-Meteo. Bootstrap classes only.
- [ ] `pluginInfo.json`: the new `sends` entry, the `description` and `summary` naming Open-Meteo, and the Tempest `systemChanges` entry kept. Re-run the schema and the length limits.
- [ ] README: the source choice, where the location comes from, what is sent, the new error messages. API.md: the new settings and status fields.
- [ ] Tests: decode a saved Open-Meteo reply; missing or null fields; a failed fetch keeps the last reading until 45 min; the retry schedule; quarter-hour timing; FPP location vs override; rounding; the override file is 0600 and stays out of `config/`; an old config without `source` stays on Tempest; a fresh config has no source and starts no thread; Weather on with no source sends nothing; switching source restarts the right thread; validation; certificate and timeout errors give the right text. All against a fake HTTPS/HTTP server, never the real API.
- [ ] Live checks: on the dev server against the real API; on fpp-matrix.local with its FPP location, then with an override, with the countdown, temperature and wind taking turns on the P5 Panel; network unplugged and clock a day off, checking what the page says.
- [ ] Run `pluginInfo.json` through the template's Plugin preview and Privacy disclosure builder: "Sends data" should be yellow ("Sends when enabled"), not red.

**Built (2026-11-11)**
- [x] `countdown/weather.py`: `OpenMeteoPoller` (HTTPS, 10 s timeout, plugin User-Agent; fetches at once, then at :01/:16/:31/:46; retries after 1, 2, 4, 8 min; a settings save refetches only if the location changed; the thread catches its own errors). `fetch_open_meteo()` turns failures into page messages (no internet, timeout, HTTP code and reason, certificate → "check this player's date and time"). `Location`/`make_location()` round to 2 decimals and treat 0, 0 as unset. `Reading.max_age_s` gives Open-Meteo its 45-minute limit; value ages come from the server's time, clamped to 15 min so a wrong player clock can't hide a fresh reading.
- [x] Daemon: `weather.source` (`""` by default, so nothing is sent until one is chosen), `weather.open_meteo.use_fpp_location`; FPP's `Latitude`/`Longitude` read from `/api/settings` (confirmed on fpp-matrix.local; FPP marks both `pii`), cached a minute. A typed-in location goes to `plugindata/fpp-matrixcountdown/location.json` (0600, removed when cleared), never into `config/` or the log; `GET config` adds it for the page. Schema 2: settings saved with Weather on and no source become `tempest`. Status: `source`, `location`, `last_fetch_age_s`, `next_fetch_s`; the Tempest's hub IP is now `hub_ip`.
- [x] Settings page: the source choice (nothing selected at first, Open-Meteo, then the Tempest for owners whose hub is on the same network as the player; no "recommended" badge), what is sent and to whom, FPP's location or "Use a different location" with lat/lon, the Open-Meteo credit, Tempest-only options shown only for the Tempest, a warning (and a Save note) when Weather is on without a source.
- [x] `pluginInfo.json`: a `sends` entry for api.open-meteo.com; description, summary and `other` updated. Passes the template schema; lengths within limits. README and API.md updated.
- [x] 27 tests in `tests/test_open_meteo.py` against a fake Open-Meteo (155 in total, all passing).
- [x] Live check on the dev server against the real API (test location 40, −100): `Temp 39°F` and `Wind 6 mph W gusts 15` took turns with the countdown in the preview; the config file had no coordinates, the location file was 0600, the log had none.
- [ ] On fpp-matrix.local: install this version, choose Open-Meteo with FPP's location, and watch the countdown, temperature and wind on the P5 Panel. Then unplug the network and set the clock a day off, and check what the page says.
- [ ] Run `pluginInfo.json` through the template's Plugin preview and Privacy disclosure builder ("Sends data" should be yellow).

**Later ideas (not in 2.1)**
- Tempest cloud REST API as a third source (personal token, kept in `plugindata/` under a key name containing `Token`, per 14.4).
- Fall back to Open-Meteo when the Tempest goes quiet.
- City/ZIP lookup with Open-Meteo geocoding (another `sends` entry).
- More messages from the same reply: humidity, today's high/low, a short "Rain" or "Snow" word.

---

## Version 3 — Social Media (planned 2026-11-11, revised 2026-11-11)

A third kind of message: **social media screens** for **Facebook, Instagram, TikTok and YouTube**. Each site has its own on/off switch and its own handle. A screen is **logos on the top line and the handle on the bottom line**, held still (never scrolled), with no "Follow us" wording. With this, the plugin has three message sections: **Countdown**, **Weather** and **Social Media**, all taking turns on the same model.

```
 Same handle on all four:        Different handles: one screen each,
 +----------------------+        shown one after another
 |  [f] [◎] [♪] [▶]     |        +----------------------+   +----------------------+
 |  @SmithFamilyLights  |        |      [f]  [▶]        |   |      [◎]  [♪]        |
 +----------------------+        |  @SmithFamilyLights  |   |    @smith_lights     |
                                 +----------------------+   +----------------------+
```

**Why it fits without a new approach:** the plugin already draws every frame itself with Pillow and writes it to the overlay buffer (section 2). A social screen is just one more panel-sized image, drawn once and held for its time. FPP's Image effect (used by fpp-santa-tracker) isn't needed.

**Requirements**

| # | Requirement | Notes |
|---|-------------|-------|
| S1 | A screen is **logos on line one, `@handle` on line two** | No lead-in text. Logos as large as the panel allows. |
| S2 | Four sites: Facebook, Instagram, TikTok, YouTube | Fixed list in v3; a site can be added later with one table entry and one logo |
| S3 | Each site has its **own on/off** and **own handle** | |
| S4 | Sites with the **same handle share one screen**: all their logos side by side above the one handle | |
| S5 | **Different handles get consecutive screens**, one per handle | In the site order above, by the first site that uses each handle |
| S6 | Social screens are **never scrolled**, whatever the Motion direction is | They are always held still and centered |
| S7 | **Seconds per screen**: a number input for how long each social screen shows | Default 5 s, 1–600 s. Separate from Motion's "Show each message (s)" for Static. |
| S8 | A **Social Media** master switch, like Show weather | Off by default |
| S9 | Takes turns with the countdown and weather | Countdown pass → temperature → wind → social screen 1 → screen 2 → ... → countdown again |

**Design decisions**

| # | Question | Decision |
|---|----------|----------|
| 1 | Same handle? | Compared after cleaning (no `@`, spaces trimmed) and **ignoring upper/lower case**, since all four sites treat handles that way. The screen shows the handle as typed for the first of its sites. |
| 2 | Screen order | Groups in site order (Facebook, Instagram, TikTok, YouTube), each group placed by its first site. Within a group, logos in the same order. |
| 3 | Layout on the panel | The handle line is measured first in its style (below), shrunk one size at a time until it fits the width. The logos get the height that's left (panel height − handle height − a 1–2 px gap), also limited so all of a group's logos plus gaps fit the width. Logos are square, the same size, centered as a row; the whole screen is centered vertically. On a 64×32 panel with a 10 px handle that gives logos about 18–20 px tall (four fit across at 14 px; two at 20 px). |
| 4 | Logo artwork | **Drawn in code** with Pillow shapes (`countdown/social.py`) at 4× the size the layout picks, then scaled down, so each size is sharp and no image files are bundled. Full brand colours, including Instagram's gradient. (Changed while building: originally one master PNG per site plus hand-tuned small ones; drawing in code reads clearly down to 12 px.) |
| 5 | Handle style | The **Text style**'s font and colour (the handle is the only text). The size there is the starting size; it only shrinks if the handle is too wide. |
| 6 | Handle too wide even at the smallest size | Shown centered and cut off at both edges, and the settings page warns "this handle doesn't fit on a W-pixel panel" next to it. Never scrolled. |
| 7 | Going back to the countdown | After the last social screen the countdown starts a fresh pass from the edge (`Mover.reset()`), so it never appears halfway across. |
| 8 | The handle | Typed with or without `@`; stored without it and always shown with one. Allowed: letters, digits, `.` `_` `-`, up to 30 characters. A site switched on with an empty handle is skipped, and the page says so. |
| 9 | Trademarks | All four allow their logo next to a profile handle; their brand rules ask that it isn't altered. The README will say the logos are trademarks of their owners, shown only to point people to the user's own profiles. To check before listing in fpp-data: whether bundling the logo files needs anything more. |
| 10 | Privacy | Nothing leaves the player; the plugin only draws what the user typed. Handles are public and stay in `config/`. No `privacy.sends` entry. |

**Config (schema 3)**

```json
"social": {
    "enabled": false,
    "screen_seconds": 5,
    "sites": {
        "facebook":  { "enabled": false, "handle": "" },
        "instagram": { "enabled": false, "handle": "" },
        "tiktok":    { "enabled": false, "handle": "" },
        "youtube":   { "enabled": false, "handle": "" }
    }
}
```
An older config gets `social.enabled = false` from the defaults merge. `SCHEMA_VERSION` goes to 3.

**Code changes**

| Where | Change |
|---|---|
| `countdown/social.py` (new) | `SITES` table (key, display name); `clean_handle()`; `social_screens(cfg) -> List[Screen]`, where `Screen = (sites: tuple, handle: str)`, grouped and ordered as above; `load_logo(site, size)` with a cache; `draw_screen(screen, w, h, text_style) -> Image`, the panel-sized picture (also used by the page's logo previews). |
| `countdown/render.py` | `Renderer` gets a `still(image)` path: return a cached panel image unchanged, no `Mover`. The countdown/weather path is untouched. |
| `matrixcountdown.py` | Turn-taking: today every turn ends after one pass (or `static_hold`). A turn now has a **kind**: `scroll` (countdown, temperature, wind; ends as today) or `still` (each social screen, named `social:1`, `social:2`, ...; ends after `social.screen_seconds`). After the last still screen, `mover.reset()`. Also: `validate_config` for `social.*`; `status.social` (screens, any site on with no handle, handles that won't fit); `status.showing` gives e.g. `[Facebook][YouTube] @SmithFamilyLights`. |
| Preview (`POST preview`) | New `as: social`, which returns every social screen as PNGs. "Now" plays the social screens in turn, each for its seconds, as the matrix does. |
| `GET logos` (new) | The logos as 48 px PNGs for the settings page, drawn by the same code as the matrix. |
| `commands/` | Optional: **Matrix Countdown - Social** `On`/`Off`/`Toggle` for the scheduler. |
| `pluginInfo.json` | Description and privacy summary mention social media; no new `sends`. |

**Settings page: three message sections**

1. **Countdown**: today's *Count down to* and *Message* cards under one heading; the **Countdown on** switch moves from the Matrix card to this header.
2. **Weather**: unchanged.
3. **Social Media** (new card): a *Show social media* switch in the header, then a **Seconds per screen** number input (1–600, with up/down arrows) and one row per site: its logo, an on/off switch, and an `@` input for the handle. Under the rows, a line says what the matrix will show, e.g. "2 screens: Facebook + YouTube @SmithFamilyLights, then Instagram + TikTok @smith_lights". Warnings for a site that's on with no handle, or a handle too wide for the panel.

**Shared** by all three and kept below them: *Motion* (with a note that social screens never scroll), *Number style / Text style* (the Text style also sets the handle's font and colour), *Matrix*, and *Preview* (new mode: Social).

**Build steps**
- [x] Logos drawn in code; checked on a contact sheet at 128, 20 and 12 px and on 64×32 and 128×64 screens with 1, 2 and 4 logos.
- [x] `social.py`: handle cleaning, grouping, `layout_screen()` / `draw_screen()`, `ScreenCache`.
- [x] Daemon: turn kinds (a `Screen` is held for `social.screen_seconds`; a `Message` ends after a pass or `static_hold`), `mover.reset()` after social, config, validation, handles saved without `@`, schema 3, `status.social`, `GET logos`. The still path lives in the daemon's `draw()` with a `ScreenCache`, so `render.py` is unchanged.
- [x] Preview: `as: social` and social screens in "Now", each item with `still`; `screen_seconds`; a warning when a handle is too wide.
- [x] Settings page: three sections (1 · Countdown, 2 · Weather, 3 · Social Media, then "Shared by all three": Motion, styles, Matrix); **Countdown on** moved to the Count down to header; Social Media card with Seconds per screen, a row per site (logo, switch, `@` handle), the "what will show" line and warnings; a Social preview button; a Social media status line.
- [x] README (Social media section, trademark note, troubleshooting), API.md, TESTING.md (section 6), `pluginInfo.json` description and summary. The optional FPP command is not built.
- [x] Tests: `clean_handle()` and handle rules; grouping (all the same, all different, two pairs, case and `@`, off/empty/bad handles skipped, master off); layout (logo size from the panel and handle height, width limit for 4 logos, handle shrinking, too wide); drawing (logo sizes and brand colours, logos above the handle and centered, too-wide flag, cache); preview (`now` order and `still`, `social` mode, sample, too-wide warning, validation, `@` removed on save, `GET logos`); the real loop with a fake fppd (countdown → each screen for its seconds, screens hold still, social only, Static).
  31 tests in `tests/test_social.py` (186 in total, all passing).
- [x] Dev server check: the Social Media card, logos, "2 screens: …" line, status line, and the Social preview holding each screen for its seconds.
- [ ] Live check on fpp-matrix.local (TESTING.md section 6): one shared handle on four sites, then two handles; check the logos read clearly from across the yard.

**Later ideas (not in v3)**
- More sites (X, Threads, Bluesky, Snapchat): a row in `SITES` and a logo.
- A QR code screen to the user's page (large panels only).
- Show the social screens only every N countdown passes.

---

## Version 4 — Weather page (planned 2026-11-11)

Replace the two scrolling weather messages ("Temp 72°F", "Wind 8 mph NW gusts 15") with **one still page**, held like the social media screens, with a **weather symbol on the left**: a **sun** by day, a **moon** at night, or a **wind** symbol when it's windy.

```
 64×32, calm day               windy night                 calm night, no gusts
 +----------------------+      +----------------------+    +----------------------+
 |  \ | /    72°F       |      |  ~~~~     38°F       |    |   (      41°F        |
 | -- O --   3 mph SW   |      | ~~~~~~   18 mph NW   |    |    (     Calm        |
 |  / | \               |      |  ~~~~   gusts 27     |    |                      |
 +----------------------+      +----------------------+    +----------------------+
```

**Requirements**

| # | Requirement | Notes |
|---|-------------|-------|
| W1 | Weather is **one page**, held still (never scrolled), whatever the Motion direction | Replaces the temperature and wind messages that scroll today |
| W2 | A **symbol on the left**: sun, moon or wind | Chosen from the reading (rules below) |
| W3 | The readings on the right: temperature on top, wind below, gusts under that when shown | Same values and rules as today (°F, mph, direction, gusts when ≥ N mph above the wind, "Calm" under 1 mph) |
| W4 | **Seconds on screen**: how long the weather page shows | Its own setting in the Weather card, like Social Media's Seconds per screen. Default 5 s, 1–600 s. |
| W5 | Takes turns as before | Countdown → **weather page** → social screens → countdown again |

**Design decisions (to confirm before building)**

| # | Question | Proposal |
|---|----------|----------|
| 1 | Which symbol | **Wind** when the wind is at least **15 mph** or the gusts at least **25 mph** (both settings, under "More wind options"). Otherwise **sun** by day and **moon** at night. Wind wins over sun/moon, because it's the more useful thing to show. |
| 2 | Day or night: Open-Meteo | Add `is_day` to the fields already requested (`current=...,is_day`). It's 1 between sunrise and sunset at the location. No extra call and nothing more is sent. (To check with a live call.) |
| 3 | Day or night: Tempest | The `obs_st` packet already carries **solar radiation** (W/m², index 11) and **lux** (index 9); keep them in `Reading`. **Day when solar radiation is above 5 W/m²** (lux above 50 if solar is missing). Night readings are 0, and heavy overcast at noon still gives well over 5. Around dawn and dusk it switches over within a minute or two of sunrise and sunset, which is fine for a symbol. |
| 4 | Day or night not known yet | Sun from 7:00 to 19:00 on the player's clock, moon otherwise, until a reading says. |
| 5 | Labels | **No "Temp" / "Wind" words on the page**: the symbol and the units say what the numbers are, and the right-hand side is narrow (about 36 px on a 64-wide panel). The Temp and Wind label settings are removed. "gusts" stays as the gust line's word (its label setting stays). |
| 6 | Temperature or wind switched off | The page shows only what's on: temperature only, or wind only. The symbol still shows. With both off, there is no weather page. |
| 7 | Stale readings | As today: a value past its stale limit is left off the page. With nothing fresh, the page is skipped. |
| 8 | Styles | Temperature in the **Number style**; wind and gusts in the **Text style**. Each line starts at its style's size and shrinks to fit the width beside the symbol, like the social handle. |
| 9 | Layout | The symbol is square, as tall as the panel allows but **no wider than 40 % of it** (32 px tall on 64×32 → 26 px, leaving 36 px for text). The lines are stacked and centered as a block to the right of it, the block centered vertically. On a short panel (16 tall) the gust line is dropped before the text gets too small to read (below 5 px). |
| 10 | Symbol artwork | **Drawn in code** like the logos (4× then scaled down). **Sun**: a yellow (#FFC400) disc with 8 rays. **Moon**: a pale yellow-white (#F4E9B0) crescent. **Wind**: three light-blue (#7FD3FF) curved lines with curled ends. |
| 11 | Animation | None in v4: still, like the social screens. A gentle movement (rays turning, wind lines drifting) is a later idea. |

**What changes for existing setups**
- Weather stops scrolling, and the temperature and wind no longer take separate turns: one weather page replaces both.
- Motion now applies only to the countdown. Its **Show each message (s)** (Static) is relabelled **Show the countdown (s)**.
- Settings schema 4: adds `weather.screen_seconds` (5), `weather.symbol.wind_mph` (15) and `weather.symbol.gust_mph` (25). Drops `weather.temperature.label` and `weather.wind.label`. Older settings load with those defaults; the dropped labels are ignored.
- API: `showing.slot` is `weather` instead of `temperature` / `wind`. `status.weather.messages` becomes `status.weather.page` (`{"symbol": "sun", "lines": ["72°F", "3 mph SW"]}`) plus `is_day`. Preview mode `as: "weather"` replaces `temperature` and `wind`.

**Code changes**

| Where | Change |
|---|---|
| `countdown/weather.py` | `Reading` gains `is_day`, `solar_wm2`, `lux` (with their times). Open-Meteo asks for `is_day`; the Tempest reader keeps solar radiation and lux. New `weather_page(reading, cfg, now) -> Optional[WeatherPage]` (`symbol`, `temp_text`, `wind_text`, `gust_text`) replaces `weather_messages()`, reusing today's formatting. `day_or_night()` follows decisions 2–4. |
| `countdown/symbols.py` (new) | `draw_symbol("sun" \| "moon" \| "wind", size)`, cached, drawn like `social.draw_logo()`. |
| `countdown/still.py` (new) | What a social screen and the weather page share: line fitting (shrink a line to a width), centering, and the `ScreenCache` (moved from `social.py`). `draw_weather_page(page, w, h, number_style, text_style)` lives here too. |
| `matrixcountdown.py` | The turn-taking loop treats the weather page as a still item held for `weather.screen_seconds` (a `still_seconds()` helper per kind, so social and weather share one path). Validation for the new settings, schema 4, status and preview changes as above. |
| `matrixcountdown.html` | Weather card: **Seconds on screen**; the Temperature / Wind switches stay (with their examples now "72°F" and "8 mph NW gusts 15"); label fields removed; the wind-symbol thresholds under "More wind and source options"; a line naming the symbol that would show now ("Showing the moon: night at the player's location"). The Preview's Temp and Wind buttons become one **Weather** button. Motion note: "Weather and social media screens never scroll." |
| Docs | README (Weather section, settings table, the three symbols), API.md, TESTING.md (a weather page section: day, night, windy), `pluginInfo.json` description. |

**Build steps**
- [ ] Confirm decisions 1, 3, 5 and 9.
- [ ] Live call to Open-Meteo with `is_day`; check the Tempest's solar/lux values on fpp-matrix.local at night and around sunset (`scripts/tempest_listen.py` can print them).
- [ ] Symbols; check them on a contact sheet and on 64×32, 128×64 and 64×16 pages before going on.
- [ ] `weather.py` reading fields and `weather_page()`; `still.py`; the loop and preview; settings, schema 4, status.
- [ ] Settings page and docs.
- [ ] Tests: symbol choice (windy by speed, windy by gusts, day, night, unknown → clock), Tempest solar/lux day/night, Open-Meteo `is_day` decoded, page lines with temperature or wind off, stale values dropped, nothing fresh → no page, layout (symbol ≤ 40 % width, lines fit, gust line dropped on a 16-tall panel), the loop holding the weather page for its seconds between the countdown and social screens, an older config loading with the new defaults, preview `as: weather`.
- [ ] Live check on fpp-matrix.local: day and night pages, and a windy page (lower the wind threshold to see it on a calm day).

**Later ideas (not in v4)**
- Clouds, rain, snow and fog symbols from Open-Meteo's `weather_code` (Tempest: rain from its precipitation type).
- A gentle animation of the symbol.
- Humidity or today's high/low as another line.

**Built (2026-11-11)**
- [x] `countdown/symbols.py`: sun, moon and wind drawn in code (4× then scaled down); checked on a contact sheet at 128, 26 and 14 px. The wind's curls were re-spaced so they don't touch at small sizes.
- [x] `countdown/weather.py`: `Reading.is_day` (Open-Meteo, now asked for with `is_day`), `solar_wm2` / `lux` (Tempest `obs_st` indexes 11 and 9); `day_or_night()` and `weather_page()` → `WeatherPage(symbol, temp, wind, gust, is_day, day_from)`, replacing `weather_messages()` / `temperature_message()` / `wind_message()`. The symbol follows the wind and gusts even with the wind line switched off.
- [x] `countdown/still.py`: `is_still()`, `hold_seconds()`, `StillCache` (moved from `social.py`, now for both kinds) and the weather layout. Changed from the plan while building: on 64×32 "18 mph NW" can't fit readably beside a 40 % symbol, so the layout tries the symbol at 40 %, 35 % and 30 % of the width, and then shorter versions of the page (no gust line, then the wind without its direction, then one line) until every line is at least size 8. Lines in the same style share a size, so wind and gusts match.
- [x] Daemon: the weather page is one still turn (`weather`), held for `weather.screen_seconds`; schema 4 (`screen_seconds`, `symbol.wind_mph` / `gust_mph`; old `label`s removed from saved settings); validation; status `page`, `is_day`, `day_from`, `solar_wm2`, `lux`; preview `as: weather`, and every still item carries its own `seconds`.
- [x] Settings page: Weather card with Seconds on screen, label fields gone, symbol limits under "More wind, symbol and source options", a note on how the symbol is chosen; the status line names the symbol and what decided day or night; Preview has one **Weather** button; Motion's Static hold reads "Show the countdown (s)".
- [x] Docs: README (Weather section with the three pages, settings, preview, file list), API.md, TESTING.md section 6, `pluginInfo.json` description and the Open-Meteo `why`.
- [x] Tests: page lines, gusts, calm, options off, stale, wind symbol by speed/gusts/limits, day/night from Open-Meteo, the Tempest's solar and lux, and the clock; layout (symbol ≤ 40 %, lines fit, shared size, gust line dropped on 64×16, variants); drawing; symbols; Open-Meteo `is_day` asked for and read; preview; old settings migrating; validation; the real loop holding the page still for its seconds. 200 tests in total, all passing.
- [x] Dev server check: Weather preview (moon by the clock at night, sample reading), Now playing countdown → weather → social, the Weather card.
- [ ] Live call to Open-Meteo with `is_day`, and the Tempest's solar/lux at night on fpp-matrix.local.
- [ ] Live check on fpp-matrix.local (TESTING.md section 6): day, night and windy pages on the P5 panel.

---

## Version 5 — No scrolling; one seconds per page (built 2026-11-11)

Asked for: remove scrolling from every section; each section shows on its own, for a number of seconds set once for all of them (default 5).

**Decisions**
- The countdown is drawn the way Static drew it: centered, on two lines when wider than the panel (each shrinking further if needed). The HH:MM:SS timer still ticks in place.
- **One setting, `global.screen_seconds`** (1–600, default 5), replaces `countdown.motion` (direction, speed, pause, Static hold), `weather.screen_seconds` and `social.screen_seconds`. Each page gets it: the countdown, the weather page, and each social media screen (two handles = two pages).
- Settings from before (schema 5 migration, on load): a Static countdown's hold time is kept as the new setting; otherwise the weather's, then social media's seconds; otherwise 5. The old keys are removed from the saved file. An old settings file uploaded through the page has those keys dropped on save.

**Built**
- [x] `render.py`: `Mover` and the four scroll directions removed; `layout_strip()` always splits a too-wide message; `Renderer.frame(message)` centers it.
- [x] `still.py`: `page_seconds(cfg)` replaces `hold_seconds()`. Daemon loop: every page ends after `page_seconds`; the pass counting and `mover.reset()` are gone.
- [x] Preview: every `strips` item is a panel-sized picture; the reply has one `seconds` instead of `direction`, `pixels_per_second`, `repeat_delay`, `static_hold`, `screen_seconds` and `weather_seconds`. The page's preview no longer has a mover: it shows each picture for `seconds`.
- [x] Settings page: the Motion card is replaced by a **Pages** card with **Seconds per page**; the Weather and Social Media cards lose their own seconds inputs.
- [x] `scripts/render_preview.py`: a contact sheet of centered frames and a ticking-timer GIF instead of one GIF per direction.
- [x] README, API.md, TESTING.md, `pluginInfo.json`.
- [x] Tests: scroll-motion tests removed; centered frame, ticking timer stays in place, every page held for the global seconds (countdown included), migration from each kind of old setting, an uploaded old file losing its keys, validation. 193 tests, all passing.
- [x] Dev server check: Pages card, no Motion card; the matrix and the preview switch pages every 3 s with `screen_seconds` 3.
- [ ] On fpp-matrix.local: TESTING.md sections 1, 6 and 7.

---

## Version 6 — Show prep page (built 2026-11-11)

Asked for: a section that tells viewers to download the show's audio app before the show, with the user choosing **PulseMesh** or **Tune2**, and a QR code a phone can scan to get to the app store for that app.

**Research (2026-11-11)**
- PulseMesh: App Store `https://apps.apple.com/us/app/pulsemesh/id6695758719`, Google Play `io.pulsemesh.app`. **`https://pulsemesh.io/download`** is a viewer page ("Get the PulseMesh app") that redirects each phone to its store, with the web player `https://player.pulsemesh.io` as a fallback.
- Tune2: App Store `https://apps.apple.com/ie/app/tune2/id6547844420`, Google Play `com.tune.two`. No single link that picks the store; **`https://www.tune2.app/downloads`** has both store links (and Tune2 Sync for display owners).
- QR size: both links (29 and 31 characters) fit the smallest code that holds them (version 2, 25 × 25 at error correction L); a 2-module lit border makes 29 squares, so 3 LEDs per square on a 96-tall matrix (87 LEDs). The store links themselves would need version 3–4 (29–33 squares).

**Decisions (2026-11-11, with the user)**
- Tune2's code opens its downloads page (chosen over two codes, iPhone and Android, or a typed link). Either app can be given the user's own link instead.
- The user's matrix is 192 × 96.

**Built**
- [x] `countdown/showprep.py`: `APPS` (name, default link), `show_prep_page()`, `link_problem()`, `show_prep_status()`, `qr_matrix()` (python3-qrcode, imported only when drawing) and `best_qr()`: the biggest code that fits at whole LEDs per square, trying error correction H, Q, M, L (higher wins a tie).
- [x] `still.py`: `draw_show_prep()`: the code on the left (dark squares on a light (225,225,225) background with a 2-square border, phones need the light border), the message word-wrapped on the right, the app's name in the Number style. Word gaps are at least 30 % of the size (some fonts' spaces vanish). The page says when the code doesn't fit, the text has to go below size 8, or the library is missing (the message still shows).
- [x] Daemon: `showprep` settings (`enabled`, `app`, `message`, `link`) and validation; its turn after the social screens; `status.showprep`; preview `as: showprep` (a PulseMesh sample when no app is chosen) and in "Now".
- [x] `pluginInfo.json`: `python3-qrcode` added to `dependencies.packages` (Debian bookworm 7.4.2, architecture all); description. `fpp_install.sh` warns if it's missing.
- [x] Settings page: a "4 · Show Prep" card (switch, app choice with where each code goes, message, own link, a line naming the link), a Show prep preview button, a status line.
- [x] Tests: 19 in `tests/test_showprep.py`, including the drawn code read back square by square and compared to the library's. 212 in total, all passing.
- [x] Dev server check, and a real scan: Chromium's `BarcodeDetector` read `https://pulsemesh.io/download` and `https://www.tune2.app/downloads` from the preview images.
- [ ] On fpp-matrix.local: **Reinstall** (not just Update) so FPP installs python3-qrcode; then TESTING.md section 8, scanning from the street with an iPhone and an Android phone.

---

## Version 7 — Daily schedule (built 2026-11-11)

Asked for: a section showing the show times, easy to set up for shows that run the same hours every night, longer hours on weekends, or a custom week (e.g. Sun–Thu ending earlier than Fri and Sat).

**Design**
- **Show nights first**, as seven day buttons, in every mode: a dark night (closed Mondays) is one click, whatever the times are.
- **Three ways to set the times**, as one segmented choice: *Same every night* (one start/end), *Weeknights + weekends* (two start/ends, plus which nights are the weekend, Fri & Sat by default), *Each night different* (a start/end per night). All three are kept in the settings, so switching back and forth loses nothing; switching to *Each night different* fills each night with the times shown before, and *Same → Weeknights + weekends* carries the times over to weeknights.
- **On the matrix**: *The week* (one line per set of times, nights grouped even when not next to each other: "Sun–Thu", "Fri & Sat", "Mon, Wed & Fri", "Nightly"; tonight's line in the Number style) or *Tonight only* ("Tonight 5–10 PM", or "No show tonight" / "Next: Sun 5–10 PM").
- **Wording**: compact times ("5:30–10 PM", "5 PM–12 AM" past midnight, "11 AM–1:30 PM"), or 24-hour ("17:30–22:00"). Week order starts on Sunday; a run that wraps the week (Sat & Sun, Fri–Sun) is one label.
- Later ideas: a season (first and last show dates); read the times from FPP's own scheduler; "Showing now until 10 PM" during the show.

**Built**
- [x] `countdown/schedule.py`: `night_times()`, `week_lines()`, `day_span()`, `format_range()`, `schedule_page()` (`SchedulePage(title, lines, kind)`), `schedule_status()`, `schedule_problems()` (what's missing, for the page) and `settings_problems()` (validation; empty times allowed while setting up).
- [x] `still.py`: the week as a centered two-column table (nights, times), one size for all, shrinking to fit, the title dropped before text goes below size 8; the tonight page stacked and centered, larger.
- [x] Daemon: `schedule` settings and validation, its turn after show prep, `status.schedule`, preview `as: schedule` (a sample when nothing is set) and in "Now". Defaults are a working schedule (every night, 5:30–10 PM) so switching it on shows something.
- [x] Settings page: a "5 · Daily Schedule" card (show-night buttons, the three ways, a per-night table that greys out dark nights, week/tonight, title, clock, an "On the matrix" line using the same grouping as the daemon, warnings for missing times), a Schedule preview button, a status line.
- [x] Docs: README (Daily schedule section), API.md, TESTING.md section 9, `pluginInfo.json`.
- [x] Tests: 22 in `tests/test_schedule.py`. 234 in total, all passing.
- [x] Dev server check: Same → Weeknights + weekends carried the times, Each night different filled from it, turning Monday off greyed its row; the card's line and the preview agreed ("Sun & Tue–Thu 5:30–10 PM · Fri & Sat 5:30–11 PM").
- [ ] On fpp-matrix.local: TESTING.md section 9.
- [x] Changed after a look at it on the dev server (2026-11-11): tonight's nights were drawn in the Number style, which made that line all one colour and looked off. Every line now keeps nights in the Text style and times in the Number style, and tonight gets a small ▸ (in the Number style's colour) in a narrow column on the left, kept on every line so the table doesn't shift. No pointer when there is only one line ("Nightly").

