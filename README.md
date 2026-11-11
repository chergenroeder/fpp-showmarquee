# fpp-matrixcountdown — Matrix Countdown Clock

An FPP plugin that shows a live countdown on an LED matrix: to **Christmas Day**, **New Year's Day**, or a **date you choose**. The number and the text each have their own font, size and colour, and the message scrolls in any direction or holds still in the center. It can also show the **temperature and wind**, taking turns with the countdown, from the free **Open-Meteo** internet service or your own **WeatherFlow Tempest** station.

```
8 Days to Christmas          Christmas in 8 Days
08:14:32 to Christmas        Christmas in 9 Hours
Temp 37°F                    Wind 8 mph NW gusts 15
```

## Features

- **Three targets, one at a time:** Christmas (Dec 25), New Year's Day (Jan 1), or a custom date and time with an optional **Repeat every year** (birthdays, anniversaries; Feb 29 falls on Feb 28 in other years).
- **Local time.** Counts by the player's own clock and time zone, daylight saving included. Days are calendar days, so Dec 17 reads "8 Days" all day.
- **Under a day:** a ticking **HH:MM:SS** timer, or **hours** (rounded up) that switch to **minutes** in the last hour.
- **At zero the matrix goes blank** for the rest of that day. Christmas and New Year's then count to next year; a custom date without yearly repeat stays blank.
- **Number first or last:** "8 Days to Christmas" or "Christmas in 8 Days". The event name, joining words ("to" / "in") and unit words ("Day", "Days", ...) can all be changed.
- **Two styles:** font, size, colour and smooth edges for the number ("8 Days") and, separately, for the text ("to Christmas"). Digits keep a fixed width, so a ticking timer doesn't jiggle.
- **Five directions:** Right to Left, Left to Right, Bottom to Top, Top to Bottom, and Static (centered). Speed and a pause between passes. For vertical and static, a message wider than the panel goes on two lines.
- **Live preview** on the settings page, drawn by the plugin itself so it matches the matrix exactly. Preview it as now, 8 days out, or under a day.
- **Weather** (optional): temperature and wind (speed, direction, gusts), in °F and mph, from **Open-Meteo** over the internet (no account or key) or from a **Tempest** hub's broadcast on your network (no internet). You pick the source. The countdown, temperature and wind take turns, one pass each.
- **FPP commands** for playlists, the scheduler and MQTT: turn the countdown on or off, or change the target.
- **REST API** for Home Assistant and scripts ([API.md](API.md)).
- **Settings download and upload** as a JSON file.

## Requirements

- FPP 10 or later (tested on FPP 10.3), with Python 3 (included in FPP).
- A **Pixel Overlay model** for the matrix (FPP **Input/Output Setup → Pixel Overlay Models**). Use a model that no other plugin draws on. If Matrix Scroller uses the same model, the page warns you.
- The matrix must be on the same player as the plugin.
- Pillow and the DejaVu fonts. The plugin declares the `python3-pil` and `fonts-dejavu-core` packages as dependencies, so FPP installs them with it (internet access needed the first time) and removes them on uninstall if nothing else uses them.

## Installation

1. In FPP go to **Content Setup → Plugin Manager**.
2. Paste this into **Add Plugin from URL** (or the URL box) and click **Install**:
   ```
   https://raw.githubusercontent.com/chergenroeder/fpp-matrixcountdown/master/pluginInfo.json
   ```
3. Open **Content Setup → Matrix Countdown Clock**, choose your overlay model under **Matrix**, and click **Save**.

The plugin starts with FPP and stops with it. To get new FPP commands after an update, use **Reinstall**, not just Update: only an install registers commands with FPP.

### Uninstalling

Uninstalling stops the plugin. Your settings are kept, so a reinstall picks them up again. To remove them too:

```bash
rm -f /home/fpp/media/config/plugin.fpp-matrixcountdown.json
```

## The settings page

| Section | What it does |
|---|---|
| Status | Online/Offline, what the matrix shows now, output state and frame rate, the player's local time and whether its clock is synced to internet time. Start / Restart / Stop. |
| Count down to | Christmas Day, New Year's Day or Custom date. Custom shows a date, a time (24-hour on the player) and **Repeat every year**. Event name. A line shows the exact moment it counts to. |
| Message | Number first / last, Countdown timer / Hours only, and (folded) the joining and unit words. Each choice shows an example in your own words. |
| Motion | Direction, speed (pixels per second) and pause between passes; for Static, how long each message shows. |
| Number style / Text style | Font (fonts found on the player), size, colour, smooth edges. |
| Weather | **Show weather**; where the weather comes from (Open-Meteo or Tempest); for Open-Meteo, FPP's location or one of your own; Temperature and Wind on/off and their labels; wind direction and gusts. More options: calm-wind text, gust label and threshold; for the Tempest, how old a reading may be, one sensor only, UDP port. A live line shows the last reading and where it came from. |
| Matrix | Overlay model, **Countdown on**, **Output enabled**; frame rate under Advanced. |
| Preview | The message at the model's size, moving as it will on the matrix. With Show weather on, **Now** plays the countdown, temperature and wind in turn, as the matrix will. Preview as Now, 8 days out, Under a day, Temp or Wind (live weather, or a sample if none has arrived). |

Changes take effect when you click **Save**. The button shows `Save *` while there are unsaved changes.

**Frame rate:** FPP shows overlay frames at its own output rate: 20 per second when idle, faster while some sequences play. The plugin follows that rate, so the default 20 is right for most setups.

## Weather

Turn on **Show weather**, then choose where the weather comes from. Nothing is shown, and nothing is sent, until you choose.

### Open-Meteo (internet, recommended)

[Open-Meteo](https://open-meteo.com/) is a free weather service: no account or API key, and it covers the whole world. Its readings are model data for your area, updated every 15 minutes, not a station in your yard.

- **Location:** FPP's own **Latitude** and **Longitude** (FPP **Settings → General**). To use somewhere else, turn on **Use a different location** and type a latitude and longitude. A location typed here is kept on the player in `plugindata/fpp-matrixcountdown/location.json` (readable by its owner only), not in FPP's settings backup.
- **What is sent:** only the latitude and longitude, rounded to 2 decimals (about 1 km), to `api.open-meteo.com` over HTTPS, every 15 minutes (just after :00, :15, :30, :45) while Show weather is on with Open-Meteo chosen.
- **Old readings:** a reading is skipped once 45 minutes old (three missed updates). A failed update is retried after 1, 2, 4 and 8 minutes, and the last reading stays up meanwhile.
- Weather data by Open-Meteo.com, under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).

### Tempest station (local network)

The Tempest hub broadcasts its readings on your network (UDP port 50222). Turn on **Show weather** and the plugin picks them up, as long as the FPP player is on the same network as the hub. To check, run this on the player and look for `heard from: ... hub(s): HB-...`:

```bash
python3 /home/fpp/media/plugins/fpp-matrixcountdown/scripts/tempest_listen.py
```

- **Temperature:** `Temp 72°F`, in whole degrees, updated about once a minute.
- **Wind:** `Wind 8 mph NW`, updated every 3 seconds. `gusts 15` is added when the gust is at least 5 mph above the wind, and under 1 mph shows `Wind Calm`. When Top/Bottom or Static needs two lines, the wind goes "Wind 8 mph NW" over "gusts 15".
- **Styles:** readings use the Number style and words the Text style.
- **Old readings:** a Tempest reading older than 5 minutes is skipped, so the countdown just shows more often.
- **Weather only:** turn **Countdown on** off and leave **Show weather** on.
- **Several stations:** set **Only this sensor** to your Tempest's serial number (ST-...), shown on the live line.

## FPP commands

Use them anywhere FPP runs a command: a playlist **FPP Command** entry, the scheduler, command presets, MQTT, or another player's remote command.

| Command | Arguments |
|---|---|
| **Matrix Countdown - State** | `On`, `Off` or `Toggle`. Off blanks the matrix and turns the overlay model off, so sequences show through. Saved. |
| **Matrix Countdown - Set Target** | `Christmas`, `New Year's Day` or `Custom`, then optional *date* (YYYY-MM-DD), *time* (HH:MM), *event name*, *repeat every year* (true/false). Blank optional arguments keep what's saved. Saved. |

For example, show "Opening Night" until the show, then switch back to Christmas afterwards. That takes two scheduler entries running **Set Target**.

## Troubleshooting

The **Output** line on the settings page says what's wrong. The log is `/home/fpp/media/logs/plugin-fpp-matrixcountdown.log`; set **Settings → Logs → Plugin** to Debug for more detail.

| Output says | Fix |
|---|---|
| `off` | Nothing to draw: **Countdown on** or **Output enabled** is off, or no model is chosen. |
| `blank` | The target has been reached; the matrix stays blank for the rest of that day (or for good, for a past custom date without yearly repeat). |
| `permission denied ... not running as root` | The plugin must run as root to draw. Click **Stop** then **Start**, or restart FPP. (**Restart** keeps the same user.) |
| `overlay model '...' not found` | The model was renamed or deleted. Choose it again under **Matrix**. |
| `drawing needs the plugin on the same player` | The FPP Host setting points at another player; the plugin can only draw on this one. |
| Weather: `choose a weather source` | Show weather is on but no source is picked. Choose Open-Meteo or Tempest in the Weather card. |
| Weather: `no location: set Latitude and Longitude in FPP …` | FPP has no location (Settings → General), or **Use a different location** is on with nothing typed in. |
| Weather: `no internet: can't look up api.open-meteo.com` | The player has no internet or DNS. Check FPP **Settings → Network** (a show network often has no internet; use the Tempest then). |
| Weather: `Open-Meteo's certificate couldn't be checked: check this player's date and time` | The player's clock is wrong, so the secure connection fails. Fix the time in FPP **Settings → Time**. |
| Weather: `Open-Meteo didn't answer within 10 s` or `answered HTTP …` | Open-Meteo is slow or down; the plugin retries on its own and keeps the last reading for up to 45 minutes. |
| Weather: `listening for the Tempest hub… no reading yet` | The player isn't hearing the hub. Run `scripts/tempest_listen.py` on the player: if it hears nothing, the player is on a different network (e.g. FPP's own Wi-Fi). |
| Weather: `cannot listen on UDP port 50222` | Another program holds the port without sharing it. Stop it, or use a different port if your hub is set up to send there. |
| `Pillow is not installed` | **Reinstall** the plugin so FPP installs its dependencies (needs internet), or `sudo apt-get install python3-pil`; then **Restart**. |
| Preview: `font ... isn't on this player; using ... instead` | Pick a font from the list, or reinstall to get DejaVu. |
| Countdown is off by hours or days | Check the time shown on the status line. If it says **NOT synced to internet time**, fix the player's clock or network (FPP **Settings → Time**). |

## Development

```bash
python3 -m venv .venv && .venv/bin/pip install pillow==11.1.0
.venv/bin/python -m unittest discover -s tests        # 100+ tests; without Pillow the drawing tests skip
.venv/bin/python scripts/dev_server.py                 # settings page at http://127.0.0.1:8765/ against a fake FPP
.venv/bin/python scripts/render_preview.py --out /tmp/preview --font /path/Font.ttf   # contact sheet + GIFs
```

| Path | |
|---|---|
| `matrixcountdown.py` | The daemon: settings, REST API on 127.0.0.1:32330, the drawing loop. |
| `countdown/timecalc.py` | Which moment to count to, and what the number reads. |
| `countdown/message.py` | The message as number and text pieces. |
| `countdown/render.py` | Pillow drawing and motion. |
| `countdown/output.py` | Writing frames into the overlay model's buffer (`/dev/shm`). |
| `countdown/fonts.py` | Finding fonts, with a fallback. |
| `countdown/weather.py` | Open-Meteo poller, Tempest UDP listener and the temperature/wind messages. |
| `matrixcountdown.html` | The settings page. |
| `commands/` | FPP commands. |
| `scripts/` | Install, start/stop, and the dev tools. |
| [TESTING.md](TESTING.md) | Hardware test checklist. |
| [DEVELOPMENT_PLAN.md](DEVELOPMENT_PLAN.md) | Design decisions and history. |

## Credits

Built on the structure of [fpp-matrixscroller](https://github.com/mikeneiderhauser/fpp-matrixscroller) by Mike Neiderhauser. Licensed under the GNU GPL v3 ([LICENSE](LICENSE)).
