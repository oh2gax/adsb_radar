# About RADAR

The ABOUT tab of the What's new window (and the app's What's new page): what RADAR is and where its data
come from. The same small Markdown as whats_new.md (paragraphs, `-` bullets, **bold**, `code`).

## RADAR (adsb_radar)

RADAR is an ATC-style web radar display of the air traffic around Helsinki-Vantaa (EFHK), in the browser and as a phone app (`/app`). It shows the aircraft heard by the MODE-S Wind receiver in Tuusula every second, with Classic or TopSky labels and the extended label's air data from the aircraft's own Mode S replies, the go-around alarm, the history line of a flight, the EFHK arrivals and departures, METAR, TAF and pilot reports, the Finnish airspace with the areas active today, and a replay of the last 30 days.

For information and hobby use only — **not for navigation or air traffic control**.

## Data and credits

- **Traffic**: the MODE-S Wind receiver (ADS-B, MLAT and Mode S / Comm-B replies), received and decoded by its own software.
- **AIP Finland** (eAIP: navaids, waypoints, ATS routes, FIR, TMA / CTA / CTR, ACC sectors, prohibited, restricted and danger areas, TSA / TRA training areas, runway thresholds and approach charts): AIS Finland, Fintraffic Air Navigation Services, www.ais.fi. "Aeronautical data is available for further refining and research without a separate fee or agreement" (AIP GEN 0.1).
- **Active areas**: the NAV WRNG pre-flight information bulletin (NOTAM) and the Airspace Use Plan AUP / UUP of the Airspace Management Cell, AIS Finland / Fintraffic ANS, www.ais.fi.
- **METAR and TAF**: NOAA / National Weather Service (tgftp.nws.noaa.gov).
- **Pilot reports, WXREPs and SIGMETs**: the Finnish aviation weather service, collected by MODE-S Wind.
- **Airports and navaids outside Finland**: OurAirports (public domain).
- **State borders**: Natural Earth (public domain).
