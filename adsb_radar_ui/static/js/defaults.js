/* defaults.js - the settings a new browser starts with on the desktop page (loaded first, before radar.js).
 * A setting the viewer has already chosen is never changed: only those not stored yet are filled in, once
 * per DEFAULTS_VERSION; RESET UI clears everything, so the page starts again from these.
 * 2026-11-06: the owner's settings — TopSky labels with CS ALT HDG SPD SQK REG TYPE, no overlap, vector
 * 0.5 min, trail 30 s, history line; approach lines, airports, water, coast, FIR, TMA/CTA, P/R/D, sectors and
 * TSA/TRA with their limits; active P/R/D and TSA/TRA with the inactive ones hidden; no rings, no points;
 * 23 NM; the TRAFFIC LIST, EFHK TRAFFIC and METAR & TAF windows open (each at its own default place).
 * The app (/app) keeps its own defaults (app.js).
 */
(function () {
  var DEFAULTS_VERSION = '1';
  var D = {
    theme: 'gray',
    rangeNm: '23',
    labelStyle: 'topsky', labelMode: 'auto', preventOverlap: '1',
    showCallsign: '1', showAlt: '1', showHdg: '1', showSpd: '1', showSquawk: '1', showType: '1',
    showVector: '1', vectorMins: '0.5', showTrail: '1', trailLenSec: '30', showHistory: '1',
    staleTimeoutMin: '2', posLossTimeoutSec: '30',
    showRings: '0', ringSpacing: 'auto',
    showAirports: '0', showNavaids: '0', showFixes: '0', navRangeNm: '100',
    ov_fi_approach: '1', ov_efhk_apt: '1', ov_efhk_aqua: '1', ov_efhk_border: '0', ov_efhk_coast: '1',
    ov_fi_restricted: '1', ov_fi_sectors: '1', ov_fi_tsa: '1',
    lblTma: '1', lblSectors: '1', lblRestricted: '1',
    actPrd: '1', actTsa: '1', actMode: 'hide',
    overlayDecimate: '1',
    qnhAuto: '1',
    trafficSort: 'altAsc',
    tlOn: '1', trOn: '1', wxOn: '1', wxTab: 'wx'
  };
  try {
    if (localStorage.getItem('defaultsV') === DEFAULTS_VERSION) return;
    for (var k in D) if (Object.prototype.hasOwnProperty.call(D, k) && localStorage.getItem(k) === null) localStorage.setItem(k, D[k]);
    localStorage.setItem('defaultsV', DEFAULTS_VERSION);
  } catch (e) { /* storage off: the built-in defaults */ }
})();
