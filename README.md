# fpp-matrixcountdown — Matrix Countdown Clock

An FPP plugin that shows a live countdown on an LED matrix: to **Christmas Day**, **New Year's Day**, or a **date you choose**. The number and the text each have their own font, size and colour. It can also show the **temperature and wind** beside a sun, moon or wind symbol, from the free **Open-Meteo** internet service or your own **WeatherFlow Tempest** station, and your **Facebook, Instagram, TikTok and YouTube** handles with each site's logo. Nothing scrolls: each one shows on its own, centered and still, for the number of seconds you choose (5 by default), then the next comes on.

```
8 Days to Christmas          Christmas in 8 Days
08:14:32 to Christmas        Christmas in 9 Hours
```

## Features

- **Three targets, one at a time:** Christmas (Dec 25), New Year's Day (Jan 1), or a custom date and time with an optional **Repeat every year** (birthdays, anniversaries; Feb 29 falls on Feb 28 in other years).
- **Local time.** Counts by the player's own clock and time zone, daylight saving included. Days are calendar days, so Dec 17 reads "8 Days" all day.
- **Under a day:** a ticking **HH:MM:SS** timer, or **hours** (rounded up) that switch to **minutes** in the last hour.
- **At zero the matrix goes blank** for the rest of that day. Christmas and New Year's then count to next year; a custom date without yearly repeat stays blank.
- **Number first or last:** "8 Days to Christmas" or "Christmas in 8 Days". The event name, joining words ("to" / "in") and unit words ("Day", "Days", ...) can all be changed.
- **Two styles:** font, size, colour and smooth edges for the number ("8 Days") and, separately, for the text ("to Christmas"). Digits keep a fixed width, so a ticking timer doesn't jiggle.
- **Pages, not scrolling:** the countdown, the weather page and each social media screen show one after another, held still, each for **Seconds per page** (default 5). A countdown wider than the panel goes on two lines.
- **Live preview** on the settings page, drawn by the plugin itself so it matches the matrix exactly. Preview it as now, 8 days out, or under a day.
- **Weather** (optional): one still page with a **sun**, **moon** or **wind** symbol beside the temperature and wind (speed, direction, gusts), in °F and mph, from **Open-Meteo** over the internet (no account or key) or from a **Tempest** hub's broadcast on your network (no internet). You pick the source.
- **Social media** (optional): each site's logo above your `@handle`, Sites with the same handle share one screen; different handles get a screen each, shown one after another.
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
| Count down to | **Countdown on**; Christmas Day, New Year's Day or Custom date. Custom shows a date, a time (24-hour on the player) and **Repeat every year**. Event name. A line shows the exact moment it counts to. |
| Message | Number first / last, Countdown timer / Hours only, and (folded) the joining and unit words. Each choice shows an example in your own words. |
| Pages | **Seconds per page**: how long the countdown, the weather page and each social media screen show before the next one comes on (default 5). |
| Number style / Text style | Font (fonts found on the player), size, colour, smooth edges. |
| Weather | **Show weather**; where the weather comes from (Open-Meteo or Tempest); for Open-Meteo, FPP's location or one of your own; Temperature and Wind on/off; wind direction and gusts. More options: when to show the wind symbol, calm-wind text, gust label and threshold; for the Tempest, how old a reading may be, one sensor only, UDP port. A live line shows the last reading, where it came from and which symbol is up. |
| Social Media | **Show social media**, and for each of Facebook, Instagram, TikTok and YouTube an on/off switch and the handle. A line says which screens the matrix will show. |
| Matrix | Overlay model, **Output enabled**; frame rate under Advanced. |
| Preview | The matrix at the model's size, as it will look. **Now** plays the countdown, the weather page and the social screens in turn, each for the seconds per page. Preview as Now, 8 days out, Under a day, Weather (live weather, or a sample if none has arrived), or Social (every social screen, even before Show social media is on). |

Changes take effect when you click **Save**. The button shows `Save *` while there are unsaved changes.

**Frame rate:** FPP shows overlay frames at its own output rate: 20 per second when idle, faster while some sequences play. The plugin follows that rate, so the default 20 is right for most setups.

## Weather

Turn on **Show weather**, then choose where the weather comes from. Nothing is shown, and nothing is sent, until you choose.

```
 calm day                      windy                         calm night
 +----------------------+      +----------------------+      +----------------------+
 |  \ | /    72°F       |      |  ~~~~     38°F       |      |   (      41°F        |
 | -- O --   3 mph SW   |      | ~~~~~~   18 mph NW   |      |    (     Calm        |
 |  / | \               |      |  ~~~~   gusts 27     |      |                      |
 +----------------------+      +----------------------+      +----------------------+
```

- **One page.** It shows for **Seconds per page** (default 5), taking turns with the countdown and social media: countdown → weather → social screens → countdown again.
- **The symbol:** the **wind** when the wind is at least 15 mph or the gusts at least 25 mph (both under "More wind, symbol and source options"); otherwise the **sun** by day and the **moon** at night. Open-Meteo says whether it's day at your location; a Tempest goes by its light sensor (day above 5 W/m² of sunlight). Until either says, 7:00–19:00 on the player's clock counts as day.
- **The lines:** the temperature (`72°F`, whole degrees) in the **Number style**; the wind (`8 mph NW`, or `Calm` under 1 mph) and gusts (`gusts 15`, when at least 5 mph above the wind) in the **Text style**. Each style starts at its size and shrinks to fit beside the symbol. On a small panel the page drops the gust line, then the wind direction, rather than use text too small to read.
- **Temperature or wind off:** the page shows only the other one. With both off there is no weather page.
- **Old readings** are left off the page; with nothing fresh, the page is skipped and the countdown just shows more often.
- **Weather only:** turn **Countdown on** off and leave **Show weather** on.

### Open-Meteo (internet)

[Open-Meteo](https://open-meteo.com/) is a free weather service: no account or API key, and it covers the whole world. Its readings are model data for your area, updated every 15 minutes, not a station in your yard.

- **Location:** FPP's own **Latitude** and **Longitude** (FPP **Settings → General**). To use somewhere else, turn on **Use a different location** and type a latitude and longitude. A location typed here is kept on the player in `plugindata/fpp-matrixcountdown/location.json` (readable by its owner only), not in FPP's settings backup.
- **What is sent:** only the latitude and longitude, rounded to 2 decimals (about 1 km), to `api.open-meteo.com` over HTTPS, every 15 minutes (just after :00, :15, :30, :45) while Show weather is on with Open-Meteo chosen.
- **Old readings:** a reading is skipped once 45 minutes old (three missed updates). A failed update is retried after 1, 2, 4 and 8 minutes, and the last reading stays up meanwhile.
- Weather data by Open-Meteo.com, under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).

### Tempest station (local network)

For Tempest owners whose Tempest hub is on the same network as the FPP player (the Pi). The hub broadcasts its readings on that network (UDP port 50222), and the plugin picks them up; no internet needed. A player on a different network (e.g. FPP's own Wi-Fi) hears nothing. To check, run this on the player and look for `heard from: ... hub(s): HB-...`:

```bash
python3 /home/fpp/media/plugins/fpp-matrixcountdown/scripts/tempest_listen.py
```

- **Updates:** temperature and sunlight about once a minute, wind every 3 seconds. A page that's up shows new readings as they arrive.
- **Old readings:** a Tempest reading older than 5 minutes is skipped.
- **Several stations:** set **Only this sensor** to your Tempest's serial number (ST-...), shown on the live line.

## Social media

Turn on **Show social media**, then switch on each site you use and type its handle (with or without the `@`).

```
 Same handle on every site:       Different handles: a screen each, one after another
 +----------------------+         +----------------------+   +----------------------+
 |  [f] [◎] [♪] [▶]     |         |      [f]  [▶]        |   |      [◎]  [♪]        |
 |  @SmithFamilyLights  |         |  @SmithFamilyLights  |   |    @smith_lights     |
 +----------------------+         +----------------------+   +----------------------+
```

- **Logos on top, handle below.** No other words. The logos are as large as the panel allows once the handle fits underneath.
- **Same handle, one screen.** Sites whose handles match (ignoring upper/lower case and the `@`) share a screen, logos side by side. Different handles get a screen each, in the order Facebook, Instagram, TikTok, YouTube.
- **A page each.** Each screen shows for **Seconds per page** (default 5), then the next comes on.
- **Taking turns:** countdown → weather page → each social screen → countdown again. Turn **Countdown on** off for social media only.
- **Style:** the handle uses the **Text style**'s font and colour. It starts at that size and shrinks if it's too wide; if it still doesn't fit at the smallest size the preview warns you and its ends are cut off, so pick a narrower font.
- **Handles:** up to 30 letters, digits, dots, underscores and dashes. A site that's on with no handle is skipped, and the page says so.
- Nothing is sent anywhere: the plugin only draws what you type. Facebook, Instagram, TikTok and YouTube logos are trademarks of their owners, shown only to point people to your own profiles.

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
| Preview: `@... is too wide for a ...-pixel matrix` | The handle doesn't fit even at the smallest size. Pick a narrower Text font. |
| Social media: `... is on but has no handle` | Type the handle for that site, or switch it off. |
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
| `countdown/render.py` | Pillow drawing of the countdown, centered. |
| `countdown/output.py` | Writing frames into the overlay model's buffer (`/dev/shm`). |
| `countdown/fonts.py` | Finding fonts, with a fallback. |
| `countdown/weather.py` | Open-Meteo poller, Tempest UDP listener, day or night, and what goes on the weather page. |
| `countdown/symbols.py` | The sun, moon and wind symbols (drawn in code). |
| `countdown/still.py` | Still pages: the weather page layout, how long each page holds, and the cache shared with the social screens. |
| `countdown/social.py` | Social media screens: handles, grouping by handle, the logos (drawn in code) and the screen layout. |
| `matrixcountdown.html` | The settings page. |
| `commands/` | FPP commands. |
| `scripts/` | Install, start/stop, and the dev tools. |
| [TESTING.md](TESTING.md) | Hardware test checklist. |
| [DEVELOPMENT_PLAN.md](DEVELOPMENT_PLAN.md) | Design decisions and history. |

## Credits

Built on the structure of [fpp-matrixscroller](https://github.com/mikeneiderhauser/fpp-matrixscroller) by Mike Neiderhauser. Licensed under the GNU GPL v3 ([LICENSE](LICENSE)).
