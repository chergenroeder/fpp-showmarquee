# fpp-matrixcountdown REST API

All endpoints go through FPP's web server:

```
http://<fpp-ip>/api/plugin/fpp-matrixcountdown/<endpoint>
```

FPP passes them on to the plugin's daemon, which listens only on the player itself (`http://127.0.0.1:32330/api/plugin/matrixcountdown/<endpoint>`).

Anyone who can open the player's FPP pages can use this API, as with FPP's own. Errors come back as `{"error": "..."}`; through FPP's proxy the HTTP status is 200 even then, so check for `error`.

---

## Status

### `GET status`

```json
{
  "running": true,
  "commit": "f10a983",
  "uptime_s": 5321,
  "local_time": "2026-11-10T21:45:12-05:00",
  "timezone": "EST",
  "utc_offset": "-0500",
  "clock_synced": true,
  "pillow": "11.1.0",
  "enable_output": true,
  "enabled": true,
  "model": "P5 Panel",
  "target_type": "christmas",
  "config_errors": [],
  "target": {
    "when": "2026-12-25T00:00-05:00",
    "name": "Christmas",
    "repeats": true,
    "display": "days",
    "seconds_left": 3809688
  },
  "message": {
    "plain": "45 Days to Christmas",
    "pieces": [["number", "45 Days"], ["text", "to Christmas"]]
  },
  "output": { "state": "drawing", "error": "", "fps": 19.8, "root": true }
}
```

| Field | |
|---|---|
| `clock_synced` | `true`/`false` from NTP, `null` if unknown. |
| `target` | `null` if a custom target has no valid date. `display` is `days`, `hms`, `hours`, `minutes` or `blank`. |
| `message.plain` | What the matrix shows; `""` when blank. |
| `output.state` | `drawing`, `blank` (target reached), `off` (disabled or no model), `error` (see `output.error`), `starting`. |

### `GET version`

`{"commit": "f10a983"}`

---

## Settings

### `GET config`

The full settings:

```json
{
  "global": { "schema_version": 1, "enable_output": true, "fpp_host": "localhost", "fps": 20 },
  "countdown": {
    "enabled": true,
    "model": "P5 Panel",
    "target": {
      "type": "christmas",
      "custom_date": "2027-03-14",
      "custom_time": "18:30",
      "custom_repeat_yearly": false,
      "event_name": { "custom": "Opening Night", "christmas": "Christmas", "newyear": "New Year's Day" }
    },
    "layout": {
      "number_position": "first",
      "connector_first": "to",
      "connector_last": "in",
      "units": { "day": "Day", "days": "Days", "hour": "Hour", "hours": "Hours", "minute": "Minute", "minutes": "Minutes" },
      "under_one_day": "hms"
    },
    "motion": { "direction": "R2L", "pixels_per_second": 15, "repeat_delay": 0 },
    "text_style":   { "font": "DejaVuSans-Bold", "size": 10, "color": "#ff0000", "antialias": false },
    "number_style": { "font": "DejaVuSans-Bold", "size": 10, "color": "#00ff00", "antialias": false }
  }
}
```

| Setting | Values |
|---|---|
| `target.type` | `christmas`, `newyear`, `custom` |
| `target.custom_date` / `custom_time` | `YYYY-MM-DD` / `HH:MM` (24-hour, player's local time) |
| `layout.number_position` | `first`, `last` |
| `layout.under_one_day` | `hms`, `hours` |
| `motion.direction` | `R2L`, `L2R`, `T2B`, `B2T`, `static` |
| `motion.pixels_per_second` | 1–500 |
| `motion.repeat_delay` | seconds ≥ 0 |
| `*_style.font` | a name from `GET fonts`; `""` = Pillow's built-in font. A missing font falls back to an installed bold sans font. |
| `*_style.size` | 4–128 |
| `*_style.color` | `#rrggbb` |
| `global.fps` | 1–60 (FPP's own output rate caps it) |

### `POST config`

Send any part of the settings; it is laid over the current settings, so `{"countdown": {"model": "P5 Panel"}}` changes only the model. Saved at once and drawn within a frame.

- OK: `{"status": "saved"}`
- Invalid: `{"error": "Invalid config", "details": ["countdown.motion.direction must be one of ..."]}`. Nothing is saved.

### `POST reload`

Re-read the settings file from disk. `{"status": "reloaded"}`

---

## Quick controls

These are what the FPP commands use.

### `POST state`

```json
{ "enabled": true }        // or false, or "toggle"
```

Turns the countdown on or off and saves it. Returns `{"enabled": true}`.

### `POST target`

```json
{ "type": "custom", "date": "2027-03-14", "time": "18:30", "name": "Opening Night", "repeat": false }
```

Only `type` is required (`christmas`, `newyear`, `custom`; "New Year's Day" is also accepted). Left-out fields keep their saved values, so `{"type": "custom"}` brings back the saved custom date. Saved. Returns `{"target": {...}}`. An invalid date returns an error and saves nothing.

---

## Preview

### `POST preview`

Draws a message the way the matrix would, from settings that don't have to be saved. The settings page uses it.

```json
{ "config": { "countdown": { "layout": { "number_position": "last" } } }, "width": 192, "height": 96, "as": "now" }
```

`as`: `now`, `days` (8 days before the target), `under_day` (8 h 14 m 32 s before). Unlike `POST config`, `config` here is laid over the **defaults**, not the saved settings.

```json
{
  "width": 192, "height": 96,
  "target": { "when": "2026-12-25T00:00-05:00", "when_text": "Fri Dec 25 2026, 00:00", "name": "Christmas", "repeats": true },
  "display": "days",
  "message": "Christmas in 45 Days",
  "direction": "R2L", "pixels_per_second": 15.0, "repeat_delay": 0.0,
  "strip": "<base64 PNG of the drawn message>", "strip_width": 120, "strip_height": 13,
  "warning": "Number font “X” isn't on this player; using “DejaVuSans-Bold” instead."
}
```

`strip` is `null` when the message is blank. `warning` appears only when a font was replaced.

---

## Lists

### `GET models`

Pixel overlay models in FPP: `[{"name": "P5 Panel", "width": 192, "height": 96}]`

### `GET fonts`

Font names the plugin can draw with: `["C059-Bold", "DejaVuSans", "DejaVuSans-Bold", ...]`. Add `?refresh=1` to rescan after adding fonts (to `/home/fpp/media/fonts/`, for example).

---

## Daemon

| Endpoint | |
|---|---|
| `GET daemon/start` | Start the daemon (as root, via sudo) if it isn't running. `{"status": "running" \| "starting" \| "already_running"}` |
| `POST daemon/restart` | Restart in place (same user). `{"status": "restarting"}` |
| `POST daemon/stop` | Stop; the model is blanked and turned off. `{"status": "stopping"}` |

---

## Home Assistant example

```yaml
rest_command:
  countdown_on:
    url: http://<fpp-ip>/api/plugin/fpp-matrixcountdown/state
    method: POST
    content_type: application/json
    payload: '{"enabled": true}'
  countdown_to_new_year:
    url: http://<fpp-ip>/api/plugin/fpp-matrixcountdown/target
    method: POST
    content_type: application/json
    payload: '{"type": "newyear"}'

sensor:
  - platform: rest
    name: Matrix countdown
    resource: http://<fpp-ip>/api/plugin/fpp-matrixcountdown/status
    value_template: "{{ value_json.message.plain }}"
    scan_interval: 30
```
