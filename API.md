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
  "showing": { "slot": "weather", "message": "[Moon] 37°F 2 mph NNE" },
  "weather": {
    "enabled": true, "source": "tempest", "listening": true, "error": "",
    "hub": "HB-00069444", "device": "ST-00084993", "hub_ip": "192.168.1.147",
    "packets": { "obs_st": 12, "rapid_wind": 240, "hub_status": 70, "device_status": 12 },
    "last_packet_age_s": 1,
    "temp_f": 37.4, "temp_age_s": 31,
    "wind_mph": 2.1, "wind_dir": "NNE", "wind_age_s": 1,
    "gust_mph": 2.5, "humidity": 40.0,
    "solar_wm2": 0.0, "lux": 0.0,
    "page": { "symbol": "moon", "lines": ["37°F", "2 mph NNE"], "plain": "[Moon] 37°F 2 mph NNE" },
    "is_day": false, "day_from": "tempest"
  },
  "social": {
    "enabled": true,
    "screens": [
      { "sites": ["facebook", "youtube"], "handle": "SmithFamilyLights", "plain": "[Facebook] [YouTube] @SmithFamilyLights" },
      { "sites": ["instagram"], "handle": "smith_lights", "plain": "[Instagram] @smith_lights" }
    ],
    "problems": { "tiktok": "TikTok is on but has no handle" }
  }
}
```

| Field | |
|---|---|
| `clock_synced` | `true`/`false` from NTP, `null` if unknown. |
| `target` | `null` if a custom target has no valid date. `display` is `days`, `hms`, `hours`, `minutes` or `blank`. |
| `message.plain` | What the matrix shows; `""` when blank. |
| `output.state` | `drawing`, `blank` (nothing to show), `off` (disabled or no model), `error` (see `output.error`), `starting`. |
| `showing` | What the matrix is drawing now: `slot` is `countdown`, `weather` (the weather page), or `social:<sites>` for a social media screen (e.g. `social:facebook+youtube`, whose `message` is `[Facebook] [YouTube] @SmithFamilyLights`). `message` (above) is always the countdown. |
| `weather` | `source` is the source in use: `open-meteo`, `tempest`, or `""` (Weather off or no source chosen; `error` is then `choose a weather source` when Weather is on). With Open-Meteo there are also `location` (`{"lat", "lon", "from": "fpp" \| "plugin"}`, rounded to 2 decimals, or `null` when there is none), `last_fetch_age_s` and `next_fetch_s`; `hub`, `device`, `hub_ip` and `packets` are Tempest only. With Open-Meteo, `error` can be set while the last reading is still shown (a failed update). Only `enabled`, `source`, `listening` and `error` until the source starts. Values are `null` until a reading arrives; ages are in seconds. `page` is what the weather page shows now (`symbol` is `sun`, `moon` or `wind`; `lines` are the temperature, wind and gust lines that are on and fresh), or `null` when there's nothing to show. `is_day` and `day_from` (`open-meteo`, `tempest` or `clock`) say how the sun or moon was chosen. `solar_wm2` and `lux` are the Tempest's light readings (`null` with Open-Meteo). |
| `social` | `screens`: the social media screens in the order they show, one per distinct handle (sites with the same handle, ignoring case and `@`, share a screen). `problems`: sites that are on but can't show, by site key. |

### `GET version`

`{"commit": "f10a983"}`

---

## Settings

### `GET config`

The full settings:

```json
{
  "global": { "schema_version": 5, "enable_output": true, "fpp_host": "localhost", "fps": 20, "screen_seconds": 5 },
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
    "text_style":   { "font": "DejaVuSans-Bold", "size": 10, "color": "#ff0000", "antialias": false },
    "number_style": { "font": "DejaVuSans-Bold", "size": 10, "color": "#00ff00", "antialias": false }
  },
  "weather": {
    "enabled": false,
    "source": "",
    "open_meteo": { "use_fpp_location": true, "latitude": null, "longitude": null },
    "port": 50222,
    "device": "",
    "stale_minutes": 5,
    "temperature": { "enabled": true },
    "wind": { "enabled": true, "direction": true, "gusts": true,
              "gust_label": "gusts", "gust_min_diff_mph": 5, "calm_text": "Calm" },
    "symbol": { "wind_mph": 15, "gust_mph": 25 }
  },
  "social": {
    "enabled": false,
    "sites": {
      "facebook":  { "enabled": false, "handle": "" },
      "instagram": { "enabled": false, "handle": "" },
      "tiktok":    { "enabled": false, "handle": "" },
      "youtube":   { "enabled": false, "handle": "" }
    }
  }
}
```

| Setting | Values |
|---|---|
| `target.type` | `christmas`, `newyear`, `custom` |
| `target.custom_date` / `custom_time` | `YYYY-MM-DD` / `HH:MM` (24-hour, player's local time) |
| `layout.number_position` | `first`, `last` |
| `layout.under_one_day` | `hms`, `hours` |
| `weather.enabled` | show weather (from the chosen source) |
| `weather.source` | `open-meteo`, `tempest`, or `""` (not chosen: nothing is shown or sent). Settings saved before 2.1 with Weather on become `tempest`. |
| `weather.open_meteo.use_fpp_location` | `true`: FPP's Latitude/Longitude (Settings → General); `false`: the location below |
| `weather.open_meteo.latitude` / `longitude` | −90–90 / −180–180, or `null`. Kept in `plugindata/fpp-matrixcountdown/location.json` (mode 0600), never in the config file; `GET config` adds them and `POST config` stores them there. Required when `use_fpp_location` is `false`. |
| `weather.port` / `device` | UDP port (50222) / only this sensor's serial, e.g. `ST-00084993` (`""` = any) |
| `weather.stale_minutes` | 0.5–1440: skip Tempest readings older than this (Open-Meteo readings: 45 min, fixed) |
| `weather.wind.gust_min_diff_mph` | show gusts when at least this far above the wind |
| `weather.symbol.wind_mph` / `gust_mph` | 0–200: show the wind symbol when the wind (or the gusts) is at least this; otherwise the sun by day, the moon at night |
| `social.enabled` | show the social media screens |
| `social.sites.<site>.enabled` / `handle` | site is `facebook`, `instagram`, `tiktok` or `youtube`. Handle: up to 30 letters, digits, `.`, `_`, `-`; a leading `@` is accepted and removed when saved. A site that's on with no handle is skipped. |
| `*_style.font` | a name from `GET fonts`; `""` = Pillow's built-in font. A missing font falls back to an installed bold sans font. |
| `*_style.size` | 4–128 |
| `*_style.color` | `#rrggbb` |
| `global.fps` | 1–60 (FPP's own output rate caps it) |
| `global.screen_seconds` | 1–600, default 5: how long each page (the countdown, the weather page, each social media screen) shows before the next. Nothing scrolls. Settings from before schema 5 take their old Static hold time, else the weather's or social media's seconds. |

### `POST config`

Send any part of the settings; it is laid over the current settings, so `{"countdown": {"model": "P5 Panel"}}` changes only the model. Saved at once and drawn within a frame.

- OK: `{"status": "saved"}`
- Invalid: `{"error": "Invalid config", "details": ["global.screen_seconds must be from 1 to 600 seconds"]}`. Nothing is saved.

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

`as`: `now`, `days` (8 days before the target), `under_day` (8 h 14 m 32 s before), `weather`, `social` (every social media screen, even with Social Media switched off; a sample with all four logos and a `note` when no site has a handle). `weather` uses the live reading, or a sample (72°F, 8 mph NW, gusts 15) with a `note` when there is none; it is an `error` when Temperature and Wind are both off. Unlike `POST config`, `config` here is laid over the **defaults**, not the saved settings.

```json
{
  "width": 192, "height": 96,
  "target": { "when": "2026-12-25T00:00-05:00", "when_text": "Fri Dec 25 2026, 00:00", "name": "Christmas", "repeats": true },
  "display": "days",
  "message": "Christmas in 45 Days",
  "seconds": 5.0,
  "strip": "<base64 PNG of the first page>", "strip_width": 192, "strip_height": 96,
  "strips": [
    { "slot": "countdown", "message": "Christmas in 45 Days", "strip": "<base64 PNG>", "strip_width": 192, "strip_height": 96 },
    { "slot": "weather", "message": "[Moon] 37°F 2 mph NNE", "strip": "<base64 PNG>", "strip_width": 192, "strip_height": 96 }
  ],
  "warning": "Number font “X” isn't on this player; using “DejaVuSans-Bold” instead."
}
```

`strips` lists what takes turns, in order: with `as: "now"`, `countdown`, then with Weather on the `weather` page (live, or a sample with a `note` if none has arrived), then with Social Media on one `social:<sites>` screen per handle. The other modes return one (`social` returns every screen). Each item is `{"slot", "message", "strip", "strip_width", "strip_height"}`, and every `strip` is the whole panel-sized picture: nothing scrolls, each page shows on its own for `seconds` (`global.screen_seconds`). The top-level `strip` is the first. A blank countdown is left out; `strip` is `null` when nothing is left. `warning` appears when a font was replaced, or when a handle is too wide for the panel even at the smallest size.

---

## Lists

### `GET models`

Pixel overlay models in FPP: `[{"name": "P5 Panel", "width": 192, "height": 96}]`

### `GET fonts`

Font names the plugin can draw with: `["C059-Bold", "DejaVuSans", "DejaVuSans-Bold", ...]`. Add `?refresh=1` to rescan after adding fonts (to `/home/fpp/media/fonts/`, for example).

### `GET logos`

The social media logos as the plugin draws them, 48×48 base64 PNGs, for the settings page: `{"logos": {"facebook": "<base64 PNG>", "instagram": ..., "tiktok": ..., "youtube": ...}}`

---

## Daemon

| Endpoint | |
|---|---|
| `POST daemon/start` | Start the daemon (as root, via sudo) if it isn't running. `{"status": "running" \| "starting" \| "already_running"}` |
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
