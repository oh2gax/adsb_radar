# What's new in RADAR

Short notes for users of the radar, newest first. Each version is one day of
development (v.DDMMYYYY). The window under the logo shows the ten newest versions.

Format: a version starts with `## v.DDMMYYYY — title`; under it bullets (`- `,
sub-bullets indented by two spaces) or plain paragraphs. **bold**, *italic* and
`code` are shown as such.

## v.07112026 — User guide in Finnish

- **RADAR-käyttöopas suomeksi** — the user guide is now also in Finnish: *What's new · Guides → USER GUIDES → RADAR-käyttöopas (suomeksi)*, 17 pages, the same content as the English guide (the program's own names, such as the buttons, stay in English as on the screen). In the app: ☰ → *What's new · Guides*.

## v.06112026 — Data status, new default view, frequencies

- **Windows stay put** — hiding the left pane (« / ») no longer moves the TRAFFIC LIST, EFHK TRAFFIC, METAR & TAF and What's new windows: each remembers where you put it on the screen and goes back there; a window under the pane when it comes back moves aside only as long as the pane is shown.
- **Frequencies on the map** — *MAP → Freq* (off by default): **SECTORS** puts each ACC sector's Helsinki Control frequency under its name (`SECT A` / `127.425`), **TMA/CTA** the unit and its frequencies under the TMAs, CTAs, FIZs and CTRs (`EFHK TMA LOWER` / `HELSINKI RADAR` / `119.100 129.850`, `EFHK CTR` / `HELSINKI TOWER` / `118.600`) — from AIP Finland, updated with every AIRAC. Shown with or without the *Limits* boxes, while the area's lines are on. In the app: ☰ → *Map*.
- **Data status** — *STATUS → DATA* in the left pane (in the app: ☰ → *DATA*) shows the data the radar downloads: the AIRAC amendment of AIP Finland in use, when it was checked and the next check, and the **next AIRAC** with the day it will be installed; for the active areas the NOTAM (NAV WRNG) and the AUP / UUP — last check, next check (every 30 minutes), last change and how many activations or areas. A failed check shows in red.
- **New default view** — a new browser (and *RESET UI*) now opens with TopSky labels, the airspace lines with their limits, the active areas with the inactive ones hidden, 23 NM, and the TRAFFIC LIST, EFHK TRAFFIC and METAR & TAF windows open. Settings you have chosen yourself stay as they are.

## v.05112026 — Replay, pilot reports, new left pane, user guide, AIP Finland, active airspace

- **Active airspace in red** — *MAP → Active*: **P/R/D** shows the restricted and danger areas activated by NOTAM (firing, UAV flights, exercises) and **TSA/TRA** the military training areas of the daily Airspace Use Plan (AUP / UUP), in red with a tag: the area, its limits and when it ends (`EFR92A / SFC–FL310 →1400Z`). The radar checks AIS Finland every 30 minutes and follows the schedules (an area booked MON-FRI 0600-1500 is red only then). *Inactive* **SHOW** draws the other areas when their *Lines* button is on, **HIDE** leaves only the active ones. In a replay you see the areas that were active at that moment. In the app: ☰ → *Map*.
- **TSA / TRA training areas** — the military training areas of AIP Finland (ENR 5.2) as a new line set, *Lines → TSA/TRA* (dash-dot).
- **About** — the What's new window has a third tab, **ABOUT**: what RADAR is and where its data come from.
- **Filter by registration or callsign** — the FILTER (formerly ICAO24 filter) now also takes registrations (`OH-LZC`, or `OHLZC`) and callsigns (`FIN7LH`) besides ICAO24 codes and ranges; `*` stands for any characters (`FIN*` all Finnair flights, `OH-*` all Finnish registrations). Enter applies it, and *FILTER ON* in the scope's corner reminds you it is on. In the app: ☰ → *Filter*.
- **Solo** — *TARGETS → Solo*: while an aircraft is selected, only it is drawn on the scope; click the empty scope (or Esc) and all traffic is back. The TRAFFIC window still lists everyone, so a click on another row moves Solo to that aircraft. In the app: ☰ → *Display → Solo*.
- **EFHK traffic: REG / ICAO24** — choose whether the column after the callsign shows the registration (the default) or the ICAO24 code; the app's EFHK traffic page has the column too.
- **Up-to-date navaids, waypoints and airspace** — the Finnish navaids, IFR waypoints, routes and airspaces now come from the official **AIP Finland** (Fintraffic ANS) and are updated automatically: the radar checks every day and switches to a new AIRAC amendment the day it takes effect. STATUS in the left pane shows which one is in use (e.g. *AIRAC 01.10.2026*).
  - The old data were years out of date: of the waypoints shown in Finland only 3 still existed, and many of the beacons around Helsinki-Vantaa (ESP, KOR, U, H …) have been withdrawn.
  - *Points → NAVAID*: the VORs, DMEs and locators of the AIP. *Points → WPT*: the 295 en-route points and the aerodromes' own SID / STAR / approach points — these only when zoomed in to 25 NM or closer.
  - *Lines*: **TMA/CTA** (the TMAs, CTAs and CTRs, on by default), **FIR** (the Finland FIR, on by default), **SECTORS** (the ACC sectors), **ATS** (the 28 RNAV routes — above FL 95 Finland is free route airspace, so there are few routes) and **P/R/D** (the prohibited, restricted and danger areas). The same switches are in the app's *Map* menu.
  - **Limits** — *MAP → Limits* labels the airspaces as on a chart: the name and class with a small box, the upper limit over the lower one (`FL285` over `2500`). Three switches — **TMA/CTA** (also the CTRs), **SECTORS** (the sector letter) and **P/R/D** (identifier and limits) — each shown while its lines are on. A label goes where its area has room and only when the area is big enough on the screen, so zooming in shows more of them. Also in the app's *Map* menu.
  - **Approach lines of every Finnish airport** — *APPROACH* now draws the final approach of every runway with an instrument approach at all 24 airports of the AIP (52 runway ends), from the runway threshold along the runway's exact bearing, 15 NM out with a gap at 5 and 10 NM. The EFHK lines are now exact too (before, their directions were rounded to whole degrees). The old ILS line set has gone.
  - For information only, not for navigation.
- **New left pane** — the settings on the left now look like the windows on the scope: the scope's own colours, a thin line between sections, and buttons instead of tick boxes — a button is **dark while it is on**, and a row of buttons picks one of a few choices (e.g. `CLASSIC | TOPSKY`, `.5 | 1 | 2 | 3 | 5` min). The pane is narrower, so the map is wider.
  - The sections (VIEW, WINDOWS, LABELS, TARGETS, MAP, ALTIMETER, OWN POSITION, FILTER, STATUS) open and close from their title; a closed one shows a short summary (e.g. `Q0997 auto`). The pane remembers which are open.
  - The UTC clock and the feed status are at the top; **WINDOWS** opens the windows on the scope: TRAFFIC LIST, EFHK TRAFFIC, METAR & TAF and REPLAY.
  - **«** at the top hides the whole pane for a full-width scope; **»** under the zoom buttons brings it back.
  - *Lines* has one button per map line set (APPROACH, AIRPORTS, WATER, ATS, BORDERS, COAST, FIR, TMA/CTA, SECTORS, P/R/D); the airports, navaids and waypoints are reloaded at once when *Within* changes. All your settings are kept.
- **User guide** — the new **RADAR user guide** (PDF, 15 pages): the scope, the labels and the alarms, the left pane, the windows, replay, the phone version, where the data come from and a quick reference. Open it from **What's new · Guides** at the top of the left pane → **USER GUIDES** (in the app: ☰ → *What's new · Guides*).
- **What's new window** — has two tabs, WHAT'S NEW and USER GUIDES, and now moves by its title and resizes from its corner like the other windows, and remembers its place and size; it stays open while you use the scope (× or Esc closes it).
- **TRAFFIC window** — the traffic list is now a window on the scope (*WINDOWS → TRAFFIC LIST*): move it by its title, resize it from its corner. Callsign, level as in the TopSky label (`032↓030`: hundreds of feet, trend, selected level), squawk (emergency squawks in red), distance, registration and type; click **CALLSIGN**, **LVL** or **NM** to sort (again: the other way). A click on a row selects that aircraft on the scope (history line, extended label), a second click releases it; **↗** opens it on flightradar24 / ADS-B Exchange. *Copy* copies the list.
- **Replay** — play back any moment of the last **30 days**: the scope shows the traffic exactly as it was, every second, with the labels, the extended label's values, the GA alarm and the history line. Open it with *WINDOWS → REPLAY* in the left pane, or in the app with ☰ → **Replay**.
  - **▶** plays and pauses (also the space bar), **−10 min / −1 min / +1 min / +10 min** jump, and **1× 2× 5× 10× 30× 60×** set the speed. The banner at the top says *REPLAY*, the UTC time and the speed.
  - Choose the UTC time from the two lists **HH : MM** and press *Go* (the lists show the replay time until you change them); choose the day from the list (days with no recording are greyed) or step with **◀ ▶**. The slider covers the whole UTC day; the go-arounds are marked on it with **GA**.
  - **Link** copies a link to this moment, with the map's centre, range and the selected aircraft — anyone opening it sees the same replay. **● LIVE** returns to the live traffic; **✕** closes the bar.
  - In the **EFHK traffic** window, **▶** at the end of a row replays that landing (from 5 minutes before) or departure (from 2 minutes before) with the aircraft selected.
  - In a replay the QNH (Auto) is taken from the METAR of that time.
  - **In the app**: ☰ → *Replay* opens the replay controls as a sheet at the bottom of the scope — the day, the time as **HH : MM** lists (the phone's scroll wheels) with *Go*, the day slider with the go-arounds, big −10′ −1′ ▶ +1′ +10′ buttons and the speeds. The top bar turns black and says *REPLAY* with the replay time. **Share** sends a link to this moment with the phone's share menu, and the *EFHK traffic* page has a **▶** on every row.
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
