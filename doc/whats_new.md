# What's new in RADAR

Short notes for users of the radar, newest first. Each version is one day of
development (v.DDMMYYYY). The window under the logo shows the ten newest versions.

Format: a version starts with `## v.DDMMYYYY — title`; under it bullets (`- `,
sub-bullets indented by two spaces) or plain paragraphs. **bold**, *italic* and
`code` are shown as such.

## v.05112026 — Replay, pilot reports

- **Replay** — play back any moment of the last **30 days**: the scope shows the traffic exactly as it was, every second, with the labels, the extended label's values, the GA alarm and the history line. Open it with **Replay → Replay bar** in the left panel.
  - **▶** plays and pauses (also the space bar), **−10 min / −1 min / +1 min / +10 min** jump, and **1× 2× 5× 10× 30× 60×** set the speed. The banner at the top says *REPLAY*, the UTC time and the speed.
  - Type a UTC time in the **UTC** box (`14:40`, `1440` or `14:40:30`) and press Enter or *Go*; choose the day from the list (days with no recording are greyed) or step with **◀ ▶**. The slider covers the whole UTC day; the go-arounds are marked on it with **GA**.
  - **Link** copies a link to this moment, with the map's centre, range and the selected aircraft — anyone opening it sees the same replay. **● LIVE** returns to the live traffic; **✕** closes the bar.
  - In the **EFHK traffic** window, **▶** at the end of a row replays that landing (from 5 minutes before) or departure (from 2 minutes before) with the aircraft selected.
  - In a replay the QNH (Auto) is taken from the METAR of that time.
- **Pilot reports** — the *METAR & TAF* window has a second tab, **Reports**: the pilot reports (ARS / AIREP), WXREPs, SIGMETs and AIRMETs, and the METARs with a windshear group, from the last **12 h** or **24 h**, newest first, as collected by MODE-S Wind. Choose which kinds to show and whether only those near EFHK. Severe (SEV) and heavy reports are in red.
  - A dot on the tab (and on *METAR & TAF* in the left panel and the app's menu) tells that there is a new report near EFHK that you have not seen.
  - **On scope** marks the reports that have a position (ARS / AIREP) on the scope with a small diamond, its phenomenon and level.
  - The app has the same tabs on its *METAR & TAF* page.
- **Recording** — the radar records everything it shows, every second, for 30 days: every aircraft within 150 NM of EFHK with its labels and the extended label's values, the go-arounds, landings and departures, and the METARs.
- **Landings** — an aircraft passing over the runway higher up (above 1000 ft) is no longer counted as a landing in the EFHK traffic list.
- **No more "None" labels** — an aircraft that sends no callsign is labelled with its ICAO24 code (as intended) instead of the word *None*.

## v.04112026 — Mobile app, go-around alarm, history line of the selected aircraft, TopSky labels with an extended label, EFHK traffic and METAR & TAF windows, move and zoom the map with the mouse, 1-second updates, What's new, own position

- **Mobile app** — open **radar.oh2gax.org/app** on a phone (or the *Mobile version* link under the logo): the scope full screen, all choices in the **☰** menu, in the ATC Gray style. *Add to Home Screen* in the browser makes it open like an app.
  - Drag with one finger to move the map, pinch with two to zoom, tap an aircraft (or its label) to select it — TopSky's extended label and the history line — and tap the empty scope to release it. **+** / **−** / **⌂** at the bottom right.
  - **◎** shows your own position from the phone's GPS and centres the map on it; tap again to switch it off.
  - The menu: label style Classic / TopSky and what the labels show, vector, trail and history line, the map lines (coastline, water, airport, borders, FIR, ATS routes), the theme, Auto QNH, and *Keep the screen on*. The theme button in the bar steps through the themes.
  - **EFHK traffic** and **METAR & TAF** open as their own pages; a tap on a traffic row shows that flight's track on the scope.
  - The app keeps its own settings: changing something on the phone does not change the desktop page, and *Reset* in the app clears only the app's.
- **EFHK approach lines** — the final approaches of all six runways (04L / 04R / 22L / 22R / 15 / 33) as dashed extended centrelines, 15 NM out with a gap at every 5 NM, as on MODE-S Wind's ATC map. Switch them on in the app's *Map → Approach lines*, or on the desktop under *Overlays → Approach*. TopSky labels keep clear of them.
- **Select by the label** — with TopSky labels a click (or a tap) on an aircraft's label now selects that aircraft too.
- **History line on / off** — *Labels & Navaids → History line* (on by default).
- **Go-around alarm** — when an aircraft goes around at EFHK, a red **GA** appears after its callsign in the label (TopSky and Classic): flashing for the first minute, then steady until it lands (or leaves the area, at most 30 minutes). A touch-and-go counts as a go-around too.
  - The radar finds the go-around itself, within a few seconds, from the 1-second positions: an aircraft established on an approach that starts to climb, or climbs away after crossing the threshold — the same rules as in MODE-S Wind. The altitudes are corrected with the QNH of the latest EFHK METAR.
- **Emergency squawk** — 7500 / 7600 / 7700 now stays red after the callsign also in the TopSky extended label.
- **History line** — click an aircraft (with Classic or TopSky labels) and a thin line shows where it has flown during this whole flight: the approach, a go-around, holding, the climb out. The line grows as the aircraft flies; click the aircraft again, click the empty scope or press **Esc** to remove it.
  - High resolution: the radar now records every aircraft's positions itself (`tracks.db`, kept for 24 hours) — straight flight about every 5 s, but every point while it turns, climbs or descends, so turns and go-arounds come out smooth. A part with no positions for over 2 minutes is drawn dashed.
  - In the **EFHK traffic** window every row can be clicked: the track of that landing or departure is drawn, also for aircraft that are no longer on the scope, with a tag at its end (e.g. `DLH2YT 05:51 ARR 22L GA`). Click the row again to remove it. Flights from before this version, or older than 24 hours, have no track.
- **TopSky label style** — *Labels & Navaids → Label style: TopSky (ATC)* draws the labels as on a controller's radar display: callsign / level, trend and selected level (`032↓030`) / ground speed in tens of knots and type (`21 A320`), with a leader line. The labels move by themselves so that they do not cover each other, the aircraft, the vectors, the trails or the navaid names, and they keep their place while it stays free. An emergency squawk is shown in red after the callsign. *Classic* keeps the original labels.
- **Extended label** — with TopSky labels, move the mouse over an aircraft to see six lines: callsign, type and registration; level, selected level, vertical rate and autopilot / approach mode; GS, TAS, IAS and Mach; magnetic heading, magnetic track, drift and roll; wind with its head / tail and cross components, and the outside air temperature; distance and bearing from the radar centre, NACp and squawk.
  - Click an aircraft to keep its extended label open; click it again or click the empty scope to close it.
  - The air data come from the aircraft's own Mode S replies (Comm-B), received by MODE-S Wind's receiver and decoded here; wind and temperature are averaged over the last minute. A value not heard for 20 s shows as `---`.
- **METAR & TAF** — the new *METAR & TAF* box: enter an airport's ICAO code (EFHK by default, any other such as EFTU), press *Apply* or Enter, and tick *Show*. A window on the scope shows the latest METAR and TAF with their times and how old they are (a METAR older than 90 minutes in red). It opens at the top right; drag it by its title bar and resize it from its lower-right corner — the place, size and airport are remembered. The reports come from the same NOAA source as in MODE-S Wind and are refreshed every 10 minutes.
- **EFHK traffic** — tick *EFHK traffic → Show arrivals & departures*: a window lists the landings and departures at EFHK, newest first, with UTC time, callsign, registration, type and runway. Choose **ARR**, **DEP** or **BOTH** (then an A/D column tells which) and **1h / 3h / 6h / 12h / 1d**; a line marks each change of the UTC day. A landing after a go-around is marked **GA** (**GA2** after two).
  - The list comes from MODE-S Wind, which runs beside the radar: every landing on all runways, and the departures whose climb it measured. The radar now also detects landings and departures itself, and adds those MODE-S Wind does not have — mostly departures without Comm-B replies (the row's tooltip says *detected by the radar*).
  - Click a row to see that flight's track (see *History line*). An aircraft still on the scope (dotted underline) also blinks and is selected; with TopSky labels its extended label opens.
  - The window opens on the right under the METAR & TAF window; move and resize it like that one. Your choices are remembered.
- **Move the map with the mouse** — drag the scope to move the centre; a plain click still selects an aircraft. The new **⌂** button under **+** / **−** brings the centre back to EFHK. The centre is remembered, as with *Manual Center*.
- **Zoom with the mouse wheel** — the place under the mouse stays where it is, from 2 NM to 400 NM. **+** / **−** go in 10 NM steps above 10 NM and halve / double below.
- **Faster, smoother map** — the map lines are loaded once (compressed, kept by the browser) and appear at once; while you drag or zoom the picture moves with the mouse and is redrawn sharp several times a second. When nothing changes the scope is redrawn only a few times a second, so the page uses far less of the computer.
- **Updates every second** — the aircraft are now updated every second (before every 5 s). Aircraft with ADS-B get a fresh position every second, decoded here from MODE-S Wind's Beast feed (the main feed is refreshed only every 2 s); others (MLAT) as before.
- **What's new** — this window: the link under the logo shows the changes of the latest versions. A small dot after the link marks a version you have not opened yet.
- **Zoom buttons on the scope** — **+** and **−** are now see-through buttons in the top-left corner of the scope, under the range (clearer on hover); the empty strip under the scope is gone.
- **Own position** — tick *Show* in the new *Own position* box and enter your latitude and longitude in decimal degrees (e.g. 60.2500, 24.8500); a small triangle marks it on the scope (light grey in the Gray theme). Remembered in this browser.

## v.03112026 — Auto QNH, registrations from MODE-S Wind, many fixes

- **Auto QNH** — *Altimeter → Auto* takes the QNH from the latest EFHK METAR (refreshed every 10 minutes); the METAR time is shown under it, and the whole METAR when you hover over it. Untick *Auto* to set the QNH by hand.
- **Registration and type for nearly every aircraft** — from MODE-S Wind's aircraft database, which is updated every morning, completed from the tar1090 database (about 620 000 aircraft) when an aircraft is missing.
- **Feed lost is shown** — when the data stop, the status line turns red; after 30 s the old targets are cleared and it says *FEED LOST*, so the scope never shows frozen aircraft as live.
- **Faster start** — the page loads only the airports, navaids and waypoints within the navaid range (16 kB instead of 10 MB).
- **Trails stay in place** — after zooming, moving the centre or resizing the window the trails stay behind their aircraft.
- **Map lines no longer vanish** — when zoomed in, coastlines, routes and borders that cross the view are drawn in full; after *Manual Center* the lines follow the new centre.
- **Traffic list** — a click on a callsign opens one tab (not two), and clicks are no longer lost while the list updates.
- **ICAO24 filter** — ranges can be separated by spaces as well as commas.
- **Timeouts** — *Off* in *Stale timeout* and *Position-loss timeout* really switches them off; a stale aircraft is also removed from the traffic list.
- **Version number** — the logo shows the version as a date, v.DDMMYYYY.

## v.12022026 — RADAR v9.0.0 Beta

- **Registration and type fields** — shown in the labels and the traffic list, from the feed or the BaseStation.sqb database.
- **MLAT positions** — used for the position when an aircraft sends no ADS-B position.
