# Hardware test checklist

A pass over everything on a real player before a release. About 20 minutes.
Run the `curl` lines on the player itself (`ssh fpp@<fpp-ip>`); they talk to
FPP's web server on `localhost`. Watch the matrix and the plugin page
(**Content Setup → Matrix Countdown Clock**) side by side.

```bash
API=http://localhost/api/plugin/fpp-matrixcountdown
# Set any part of the settings (the rest is kept); prints {"status": "saved"}
set() { curl -s -X POST -H 'Content-Type: application/json' -d "$1" $API/config; echo; }
```

Save your settings first, to put them back at the end:

```bash
curl -s $API/config > /tmp/mc-before.json
```

## 0. Before you start

- [ ] Status shows **Online**, Output **drawing at ~20 fps**, and FPP local time is right and **synced to internet time**.
- [ ] The preview shows no "font isn't on this player" warning (or names the font it uses instead).

## 1. Directions and order (days)

Set Christmas, then each combination. Check both the matrix and the page preview.

```bash
for dir in R2L L2R T2B B2T static; do for pos in first last; do
  set "{\"countdown\":{\"model\":\"P5 Panel\",\"target\":{\"type\":\"christmas\"},\"layout\":{\"number_position\":\"$pos\"},\"motion\":{\"direction\":\"$dir\"}}}"
  echo "$dir / number $pos"; read -p "Enter for next " _
done; done
```

- [ ] Right to Left / Left to Right enter fully from one edge and leave fully past the other.
- [ ] Top to Bottom / Bottom to Top: same, vertically. A message wider than the panel goes on two lines.
- [ ] Static: centered and steady.
- [ ] Number first reads "N Days to Christmas", number last "Christmas in N Days", each part in its own font and colour.
- [ ] A pause between passes (set `"repeat_delay": 3`) leaves the panel blank for 3 s between passes.

## 2. Under a day: HH:MM:SS

A custom target **5 minutes** from now (the time is whole minutes):

```bash
T=$(date -d '+5 min' '+%Y-%m-%d %H:%M'); D=${T% *}; H=${T#* }
set "{\"countdown\":{\"target\":{\"type\":\"custom\",\"custom_date\":\"$D\",\"custom_time\":\"$H\",\"custom_repeat_yearly\":false,\"event_name\":{\"custom\":\"Test\"}},\"layout\":{\"under_one_day\":\"hms\"},\"motion\":{\"direction\":\"static\"}}}"
```

- [ ] Shows `00:04:xx to Test`, ticking once a second without the text jiggling.
- [ ] At the target minute it reads `00:00:00`, then the matrix goes **blank** and the overlay model turns off (a running sequence shows through).
- [ ] The page shows "(blank)" and the warning that the date has passed.

## 3. Under a day: hours, then minutes

A custom target **62 minutes** from now, hours only:

```bash
T=$(date -d '+62 min' '+%Y-%m-%d %H:%M'); D=${T% *}; H=${T#* }
set "{\"countdown\":{\"target\":{\"type\":\"custom\",\"custom_date\":\"$D\",\"custom_time\":\"$H\"},\"layout\":{\"under_one_day\":\"hours\"}}}"
```

- [ ] Shows `2 Hours to Test`.
- [ ] About 2 minutes later it switches to `60 Minutes to Test`, then counts down a minute at a time, ending at `1 Minute`.

## 4. Yearly repeat

```bash
set "{\"countdown\":{\"target\":{\"type\":\"custom\",\"custom_date\":\"2020-01-05\",\"custom_repeat_yearly\":true}}}"
```

- [ ] Counts to the next Jan 5 (the page shows the year it picked).

## 5. FPP commands

From a playlist **FPP Command** entry, or **Run Command** on FPP's status page:

- [ ] **Matrix Countdown - State**: Off blanks the matrix; On brings it back; Toggle flips it.
- [ ] **Matrix Countdown - Set Target**: Christmas, New Year's Day, and Custom with a date and name all take effect within a second.

## 6. Weather page

Choose Open-Meteo (or the Tempest) in the Weather card, then:

```bash
set '{"countdown":{"motion":{"direction":"R2L"}},"weather":{"enabled":true,"screen_seconds":5},"social":{"enabled":false}}'
```

- [ ] After the countdown's pass, **one weather page** is held still for 5 s: a symbol on the left, the temperature over the wind (and gusts) on the right; then the countdown scrolls in fresh from the edge.
- [ ] By day it's the **sun**, after dark the **moon** (the status line says which, and whether Open-Meteo, the Tempest or the clock decided).
- [ ] Lower the wind symbol limit to see the **wind** symbol on a calm day:
  ```bash
  set '{"weather":{"symbol":{"wind_mph":1,"gust_mph":1}}}'
  ```
  then put it back with `set '{"weather":{"symbol":{"wind_mph":15,"gust_mph":25}}}'`.
- [ ] The text is readable from across the yard; on the P5 panel nothing is cut off.
- [ ] Turn Wind off: the page shows the temperature only. Turn both off: no weather page.

## 7. Social media

```bash
set '{"countdown":{"motion":{"direction":"R2L"}},"social":{"enabled":true,"screen_seconds":5,"sites":{"facebook":{"enabled":true,"handle":"SmithFamilyLights"},"instagram":{"enabled":true,"handle":"SmithFamilyLights"},"tiktok":{"enabled":true,"handle":"SmithFamilyLights"},"youtube":{"enabled":true,"handle":"SmithFamilyLights"}}}}'
```

- [ ] After the countdown's pass, **one screen** shows all four logos side by side with `@SmithFamilyLights` underneath, held still for 5 s; then the countdown scrolls in fresh from the edge.
- [ ] The logos are recognisable and in colour from across the yard.

```bash
set '{"social":{"screen_seconds":3,"sites":{"instagram":{"handle":"smith_lights"},"tiktok":{"handle":"@Smith_Lights"}}}}'
```

- [ ] **Two screens**, 3 s each: Facebook + YouTube `@SmithFamilyLights`, then Instagram + TikTok `@smith_lights` (case and `@` ignored when matching).
- [ ] With `"direction":"static"` the countdown holds for its time, then each screen for 3 s.
- [ ] Turn **Countdown on** off: only the social screens take turns.
- [ ] The page's **Social media** status line names the screens; switching a site on with an empty handle shows a warning there and in the card.

## 8. Recovery

- [ ] Restart fppd (**Status → Restart FPPD**): the countdown comes back by itself within ~5 s.
- [ ] Reboot the player: the countdown starts on its own.
- [ ] **Stop** then **Start** on the plugin page: it comes back (Start runs it as root).
- [ ] Choose a model that doesn't exist: Output shows the error; choose the real one again and it recovers.

## Finish

```bash
set "$(cat /tmp/mc-before.json)"
```
