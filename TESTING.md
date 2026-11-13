# Hardware test checklist

A pass over everything on a real player before a release. About 20 minutes.
Run the `curl` lines on the player itself (`ssh fpp@<fpp-ip>`); they talk to
FPP's web server on `localhost`. Watch the matrix and the plugin page
(**Content Setup → Show Marquee**) side by side.

```bash
API=http://localhost/api/plugin/fpp-showmarquee
# Set any part of the settings (the rest is kept); prints {"status": "saved"}
set() { curl -s -X POST -H 'Content-Type: application/json' -d "$1" $API/config; echo; }
```

Save your settings first, to put them back at the end:

```bash
curl -s $API/config > ~/mc-before.json    # in your home folder: a reboot (section 12) empties /tmp
```

## 0. Before you start

- [ ] Status shows **Online**, Output **drawing at ~20 fps**, and FPP local time is right and **synced to internet time**.
- [ ] The preview shows no "font isn't on this player" warning (or names the font it uses instead).

## 0b. The settings page

- [ ] On a new install the page opens on **Overview** with **Getting started**: choosing the matrix, turning pages on and setting them up tick their steps off; after **Save** all four are ticked and it hides, and stays hidden after a reload.
- [ ] **How it works** opens and closes (social sites with the same handle share a page); **Help** opens the README on GitHub.
- [ ] On a player that's already set up, **Getting started** at the top shows the checklist (all ticked) on Overview until **Hide**.
- [ ] Before a matrix is chosen the header says "not drawing: choose your matrix"; choosing a big matrix (96 tall) sets both style sizes to suit it (24) and says so.
- [ ] A page that's off says "This page is off" at the top of its tab (Countdown too); its controls are still usable.
- [ ] The page opens on **Overview**: every kind of page with its switch, a summary, ▲ ▼ and **Edit**.
- [ ] **Edit** opens that page's tab; the preview shows just that page. Reloading the page comes back to the same tab.
- [ ] Switch a page on in Overview: its own tab's switch is on too (and the other way round), and its line says **Save to turn it on** until you Save.
- [ ] Click a tab, then use the Left and Right keys: they move between the tabs.
- [ ] Move Schedule up with ▲ and **Save**: the matrix shows the schedule right after the countdown.
- [ ] A section that needs something (Weather on with no source) has a dot on its tab and its Overview line.
- [ ] With no overlay model chosen, a banner on every tab points to **Display**.
- [ ] On a phone the tabs scroll sideways and nothing else does.

## 1. Number order (days)

Set Christmas, then each order. Check both the matrix and the page preview.

```bash
for pos in first last; do
  set "{\"countdown\":{\"model\":\"P5 Panel\",\"target\":{\"type\":\"christmas\"},\"layout\":{\"number_position\":\"$pos\"}}}"
  echo "number $pos"; read -p "Enter for next " _
done
```

- [ ] Centered and still; nothing scrolls. A message wider than the panel goes on two lines.
- [ ] Number first reads "N Days to Christmas", number last "Christmas in N Days", each part in its own font and colour.

## 2. Under a day: HH:MM:SS

A custom target **5 minutes** from now (the time is whole minutes):

```bash
T=$(date -d '+5 min' '+%Y-%m-%d %H:%M'); D=${T% *}; H=${T#* }
set "{\"countdown\":{\"target\":{\"type\":\"custom\",\"custom_date\":\"$D\",\"custom_time\":\"$H\",\"custom_repeat_yearly\":false,\"event_name\":{\"custom\":\"Test\"}},\"layout\":{\"under_one_day\":\"hms\"}}}"
```

- [ ] Shows `00:04:xx to Test`, ticking once a second without the text jiggling.
- [ ] At the target minute it reads `00:00:00`, then the countdown drops out: the other pages that are on keep taking turns, and the Countdown tab's preview is blank. With no other page on, the matrix goes **blank** and the overlay model turns off (a running sequence shows through).
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

From a playlist **FPP Command** entry, **Run Command** on FPP's status page, or the **Scheduler** (an FPP Remote can't run playlists, so use the scheduler there):

- [ ] **Show Marquee - Output**: Off blanks the matrix and turns the overlay model off (Output says `off`, **Output enabled** is unticked on Display); On brings back the same pages; Toggle flips it. It stays that way after a reboot.
- [ ] **Show Marquee - Countdown**: Off takes the countdown page out of the turns (with no other page on, the matrix goes blank); On brings it back; Toggle flips it.
- [ ] **Show Marquee - Set Target**: Christmas, New Year's Day, and Custom with a date and name all take effect within a second.

## 5b. Show page

- [ ] On the **Show** tab, type the show's name and turn the page on: the preview shows it as large as fits; **Save**: it's the first page on the matrix.
- [ ] **Upload logo** with a square logo: the preview shows it on the left, the name beside it; **Replace logo** and **Remove** appear. On the matrix it changes without pressing Save.
- [ ] A wide logo (a banner) goes above the name. Turn off **Show the name with the logo**: the logo fills the matrix on its own.
- [ ] A logo with a transparent or black border is trimmed so it fills its space. The file picker lists only images; a file that isn't one is refused: `curl -s -X POST -H 'Content-Type: application/json' -d '{"image":"aGVsbG8="}' $API/logo` says "Logo not saved: …".
- [ ] **Remove** asks first, then the page shows just the name. With no name and no logo the tab has a dot.
- [ ] Uninstall removes the logo; on FPP 10.4+ a **Reinstall** keeps it.

## 6. Weather page

Choose Open-Meteo (or the Tempest) on the Weather tab, then:

```bash
set '{"global":{"screen_seconds":5},"weather":{"enabled":true},"social":{"enabled":false}}'
```

- [ ] The countdown and **the weather page** take turns, 5 s each, both held still: a symbol on the left, the temperature over the wind (and gusts) on the right.
- [ ] On a clear, calm day it's the **sun**, after dark the **moon** (the status line says which, and whether Open-Meteo, the Tempest or the clock decided).
- [ ] **Conditions** (Open-Meteo): on a cloudy, rainy, snowy, foggy or stormy day the symbol matches the sky outside (Open-Meteo updates every 15 minutes), and the status line names it. Rain, snow, storms and fog show even when it's windy; clouds give way to the wind symbol.
- [ ] **Conditions** (Tempest): in rain the **rain** symbol comes up within a minute of the first drops and stays 10 minutes after the last; near freezing it's **sleet**. With lightning nearby (2 strikes within 20 km in 15 minutes) it's the **storm**, and the status line says "lightning nearby".
- [ ] Turn off **Symbol shows rain, snow, clouds, fog and storms**: only the sun, moon and wind.
- [ ] **Units** °C and km/h: the page reads "22°C" and "Wind 13 km/h …", and the limits under More options show km/h beside the mph.
- [ ] Lower the wind symbol limit to see the **wind** symbol on a calm day:
  ```bash
  set '{"weather":{"symbol":{"wind_mph":1,"gust_mph":1}}}'
  ```
  then put it back with `set '{"weather":{"symbol":{"wind_mph":15,"gust_mph":25}}}'`.
- [ ] The text is readable from across the yard; on the P5 panel nothing is cut off.
- [ ] The wind line reads "Wind 8 mph NW" (or "Wind Calm"); change the Wind **Label** and it changes.
- [ ] Turn Wind off: the page shows the temperature only. Turn both off: no weather page, a warning under the switches, and a dot on the Weather tab and its Overview line.

## 7. Social media

```bash
set '{"global":{"screen_seconds":5},"social":{"enabled":true,"sites":{"facebook":{"enabled":true,"handle":"SmithFamilyLights"},"instagram":{"enabled":true,"handle":"SmithFamilyLights"},"tiktok":{"enabled":true,"handle":"SmithFamilyLights"},"youtube":{"enabled":true,"handle":"SmithFamilyLights"}}}}'
```

- [ ] After the countdown (5 s), **one screen** shows all four logos side by side with `@SmithFamilyLights` underneath for 5 s, then the countdown again.
- [ ] The logos are recognisable and in colour from across the yard.

```bash
set '{"global":{"screen_seconds":3},"social":{"sites":{"instagram":{"handle":"smith_lights"},"tiktok":{"handle":"@Smith_Lights"}}}}'
```

- [ ] The countdown, then **two screens**, 3 s each: Facebook + YouTube `@SmithFamilyLights`, then Instagram + TikTok `@smith_lights` (case and `@` ignored when matching).
- [ ] Switch the countdown off (Overview): only the social screens take turns.
- [ ] The page's **Social media** status line names the screens; switching a site on with an empty handle shows a warning there and in the card.

## 8. Show prep

```bash
set '{"global":{"screen_seconds":5},"showprep":{"enabled":true,"app":"pulsemesh","link":""}}'
```

- [ ] After the countdown, **the show prep page**: a QR code on the left with a light border, "Scan to get the **PulseMesh** app before the show" on the right.
- [ ] Scan the code on the matrix with an iPhone camera from the street: it opens pulsemesh.io/download and goes on to the App Store. With an Android phone: Google Play.
- [ ] Switch to Tune2 (`"app":"tune2"`): the code opens www.tune2.app/downloads; its App Store and Google Play links work.
- [ ] Your own link (`"link":"https://example.com"`) replaces it; clearing it (`"link":""`) goes back to the app's page.
- [ ] Try it at the brightness you run the show at: if phones struggle, lower the matrix brightness a little.

## 9. Daily schedule

On the **Schedule** tab, turn on **Show on the matrix**, then for each, check the card's "On the matrix" line, the preview and the matrix:

- [ ] **Same every night**, 5:30 PM–10:00 PM: "Show Times" / "Nightly 5:30–10 PM" (one line, so no pointer).
- [ ] **Weeknights + weekends**: the weeknight times carry over from Same every night. Set weekends to end at 11:00 PM: "Sun–Thu 5:30–10 PM" / "Fri & Sat 5:30–11 PM", every row's nights in the Text style and times in the Number style, and a small ▸ in front of tonight's line.
- [ ] Make the weekend Sat & Sun: "Mon–Fri …" / "Sat & Sun …".
- [ ] **Each night different**: each night starts with the times above. Change Thursday: it gets its own line.
- [ ] Turn Monday off: Monday's row greys out and Monday leaves the matrix.
- [ ] An end of 12:00 AM reads "… PM–12 AM".
- [ ] **Tonight only**: "Tonight 5:30–10 PM"; with tonight off, "No show tonight" and the next show.
- [ ] A late show: end Friday at 12:30 AM. Just after midnight it still says "Tonight" with Friday's times (and the week page still points at Friday); after 12:30 AM it moves to Saturday.
- [ ] **Clock** 24-hour: "17:30–22:00".

## 10. Custom messages

On the **Messages** tab, turn on **Show on the matrix**:

- [ ] **Add message** "Merry Christmas!" (Enter) "from the Smiths", picture Tree: the tree on the left, two centered lines on the right, in the Text style's colour.
- [ ] Add "Only {days} days left!" using the `{days}` button, Colour: Number style, picture Star: the number is filled in.
- [ ] Colour **Own colour**: the colour picker opens at gold; pick a colour and the text is that colour (the swatch beside the list changes it later).
- [ ] A long message ("Thank you for visiting! Please drive slowly and enjoy the show") wraps and still reads from the street.
- [ ] "It's {temp} out" with the weather page off and no weather source chosen: it says (in amber) "not showing now: nothing for {temp} right now: choose a weather source…", and the matrix skips it.
- [ ] Choose a source on the Weather tab, leaving its page off: the tab says the weather still comes from there for `{temp}`, and within a minute (Tempest) or 15 (Open-Meteo) the message shows the temperature. The weather page stays out of the turns.
- [ ] Only between dates: today to today shows it; tomorrow to tomorrow skips it ("outside its dates").
- [ ] ▲ ▼ reorder the messages on the matrix; ✕ deletes one; Save, then Revert keeps them.

## 11. Start, uninstall and reinstall

- [ ] **Stop**, then **Start** on the settings page: the plugin comes back, running as root (Output says drawing, not "permission denied").
- [ ] FPP's command list has **Show Marquee - Start**; running it while the plugin is running does nothing.
- [ ] FPP 10.4+: **Reinstall** keeps the settings, a typed-in weather location and the Show logo.
- [ ] **Uninstall**: `config/plugin.fpp-showmarquee.json` and `plugindata/fpp-showmarquee/` are gone; nothing else in `config/` changed.

## 12. Recovery

- [ ] Restart fppd (**Status → Restart FPPD**): the pages come back by themselves within ~5 s.
- [ ] Reboot the player: the pages start on their own.
- [ ] **Stop** then **Start** on the plugin page: it comes back (Start runs it as root).
- [ ] A model that doesn't exist (the list only offers real ones, so set it here): `set '{"countdown":{"model":"Missing"}}'`: Output shows "overlay model 'Missing' not found"; choose the real one again on Display and it recovers.

## Finish

```bash
set "$(cat ~/mc-before.json)"
```
