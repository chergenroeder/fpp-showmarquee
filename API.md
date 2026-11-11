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
  "output": { "state": "drawing", "error": "", "fps": 19.8, "root": true },
  "showing": { "slot": "wind", "message": "Wind 2 mph NNE" },
  "weather": {
    "enabled": true, "listening": true, "error": "",
    "hub": "HB-00069444", "device": "ST-00084993", "source": "192.168.1.147",
    "packets": { "obs_st": 12, "rapid_wind": 240, "hub_status": 70, "device_status": 12 },
    "last_packet_age_s": 1,
    "temp_f": 37.4, "temp_age_s": 31,
    "wind_mph": 2.1, "wind_dir": "NNE", "wind_age_s": 1,
    "gust_mph": 2.5, "humidity": 40.0,
    "messages": { "temperature": "Temp 37°F", "wind": "Wind 2 mph NNE" }
  }
}
```

| Field | |
|---|---|
| `clock_synced` | `true`/`false` from NTP, `null` if unknown. |
| `target` | `null` if a custom target has no valid date. `display` is `days`, `hms`, `hours`, `minutes` or `blank`. |
| `message.plain` | What the matrix shows; `""` when blank. |
| `output.state` | `drawing`, `blank` (nothing to show), `off` (disabled or no model), `error` (see `output.error`), `starting`. |
| `showing` | What the matrix is drawing now: `slot` is `countdown`, `temperature` or `wind`. `message` (above) is always the countdown. |
| `weather` | Only `enabled`, `listening` and `error` until the listener starts. Values are `null` until a reading arrives; ages are in seconds. `messages` are empty strings when a reading is too old or switched off. |

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
    "motion": { "direction": "R2L", "pixels_per_second": 15, "repeat_delay": 0, "static_hold": 5 },
    "text_style":   { "font": "DejaVuSans-Bold", "size": 10, "color": "#ff0000", "antialias": false },
    "number_style": { "font": "DejaVuSans-Bold", "size": 10, "color": "#00ff00", "antialias": false }
  },
  "weather": {
    "enabled": false,
    "port": 50222,
    "device": "",
    "stale_minutes": 5,
    "temperature": { "enabled": true, "label": "Temp" },
    "wind": { "enabled": true, "label": "Wind", "direction": true, "gusts": true,
              "gust_label": "gusts", "gust_min_diff_mph": 5, "calm_text": "Calm" }
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
| `motion.static_hold` | 1–600 s: how long each message shows in Static when weather takes turns |
| `weather.enabled` | listen for the Tempest hub and show weather |
| `weather.port` / `device` | UDP port (50222) / only this sensor's serial, e.g. `ST-00084993` (`""` = any) |
| `weather.stale_minutes` | 0.5–1440: skip readings older than this |
| `weather.wind.gust_min_diff_mph` | show gusts when at least this far above the wind |
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

`as`: `now`, `days` (8 days before the target), `under_day` (8 h 14 m 32 s before), `temperature`, `wind`. The weather modes use the live reading (even if that message is switched off), or a sample (72°F, 8 mph NW, gusts 15) with a `note` when there is none. Unlike `POST config`, `config` here is laid over the **defaults**, not the saved settings.

```json
{
  "width": 192, "height": 96,
  "target": { "when": "2026-12-25T00:00-05:00", "when_text": "Fri Dec 25 2026, 00:00", "name": "Christmas", "repeats": true },
  "display": "days",
  "message": "Christmas in 45 Days",
  "direction": "R2L", "pixels_per_second": 15.0, "repeat_delay": 0.0,
  "static_hold": 5.0,
  "strip": "<base64 PNG of the drawn message>", "strip_width": 120, "strip_height": 13,
  "strips": [
    { "slot": "countdown", "message": "Christmas in 45 Days", "strip": "<base64 PNG>", "strip_width": 120, "strip_height": 13 },
    { "slot": "temperature", "message": "Temp 37°F", "strip": "<base64 PNG>", "strip_width": 52, "strip_height": 13 }
  ],
  "warning": "Number font “X” isn't on this player; using “DejaVuSans-Bold” instead."
}
```

`strips` lists the messages that take turns, in order: with `as: "now"` and Weather on, `countdown`, `temperature` and `wind` (live, or a sample with a `note` if none has arrived; switched-off or stale ones are left out). The other modes return one. Each item is `{"slot", "message", "strip", "strip_width", "strip_height"}`; the top-level `strip` is the first. `static_hold` is how long each shows in Static. `strip` is `null` when the message is blank. `warning` appears only when a font was replaced.

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
