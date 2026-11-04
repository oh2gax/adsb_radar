
const canvas = document.getElementById('radarCanvas');
const ctx = canvas.getContext('2d');
let DPR = window.devicePixelRatio || 1;
const NBSP_GLOBAL = '\u00A0';

// --- Theme handling ---
let theme = localStorage.getItem('theme') || 'gray';
function refreshColors(){
  const src = document.body || document.documentElement;
  const rs = (n)=> getComputedStyle(src).getPropertyValue(n).trim();
  window.colors = {
    bg: rs('--radar-bg'),
    ring: rs('--radar-ring'),
    center: rs('--radar-center'),
    text: rs('--radar-text'),
    symbol: rs('--radar-symbol'),
    trail: rs('--radar-trail'),
    navaid: rs('--radar-navaid'),
    airport: rs('--radar-airport'),
    fix: rs('--radar-fix'),
    own: rs('--radar-own') || rs('--radar-symbol'),
  };
}
function applyTheme(){
  document.body.classList.remove('theme-green','theme-full-el','theme-gray','theme-full-el-yellow');
  if(theme === 'green') document.body.classList.add('theme-green');
  else if(theme === 'full-el') document.body.classList.add('theme-full-el');
  else if(theme === 'full-el-yellow') document.body.classList.add('theme-full-el-yellow');
  else document.body.classList.add('theme-gray');

  const gbc = document.getElementById('grayBgControls');
  if(gbc) gbc.style.display = (theme==='gray') ? '' : 'none';

  if(theme==='gray'){
    const gb = localStorage.getItem('grayBg') || '#cfcfcf';
    document.documentElement.style.setProperty('--gray-bg', gb);
  }

  const side = document.querySelector('.side');
  if(side){ side.style.removeProperty('background'); side.style.removeProperty('background-color'); }

  refreshColors();
  localStorage.setItem('theme', theme);
}
document.addEventListener('DOMContentLoaded', ()=>{ applyTheme(); });

// --- Defaults requested ---
// range default 20nm
let rangeNm = parseFloat(localStorage.getItem('rangeNm') || '20');
let showCallsign = localStorage.getItem('showCallsign') !== '0';
let labelMode = localStorage.getItem('labelMode') || 'auto';
// Label style: 'classic' (the original labels) or 'topsky' (topsky.js: leader lines, extended label)
let labelStyle = localStorage.getItem('labelStyle') === 'topsky' ? 'topsky' : 'classic';
let showAlt = localStorage.getItem('showAlt') !== '0';
// Hdg OFF by default unless user set it
let showHdg = (localStorage.getItem('showHdg') ?? '0') === '1';
let showReg = (localStorage.getItem('showReg') ?? '1') === '1';
// Trail ON by default
let showTrail = (localStorage.getItem('showTrail') ?? '1') === '1';
// Speed, Squawk, Vector default ON
let showSpd = (localStorage.getItem('showSpd') ?? '1') === '1';
let showSquawk = (localStorage.getItem('showSquawk') ?? '1') === '1';
let showVector = (localStorage.getItem('showVector') ?? '1') === '1';
// Prevent overlap default ON
let preventOverlap = (localStorage.getItem('preventOverlap') ?? '1') === '1';
// Vector 0.5 min default
let vectorMins = parseFloat(localStorage.getItem('vectorMins') || '0.5');
let showType = (localStorage.getItem('showType') ?? '0') === '1';
// Air/Naid ON, Fixes (Waypoints) OFF
let showAirports = (localStorage.getItem('showAirports') ?? '1') === '1';
let showNavaids = (localStorage.getItem('showNavaids') ?? '1') === '1';
let showFixes = (localStorage.getItem('showFixes') ?? '0') === '1';
// Navaid range 100
let navRangeNm = parseFloat(localStorage.getItem('navRangeNm') || '100');
// Stale 2 min
let staleTimeoutMin = parseFloat(localStorage.getItem('staleTimeoutMin') || '2');
// Pos-loss 30s
let posLossTimeoutSec = parseFloat(localStorage.getItem('posLossTimeoutSec') || '30');
// Sort Alt low->high
let trafficSort = localStorage.getItem('trafficSort') || 'altAsc';
// Trail length 60s
let trailLenSec = parseFloat(localStorage.getItem('trailLenSec') || '60');
// QNH 1013
let qnh = parseFloat(localStorage.getItem('qnh') || '1013');
// Rings on, spacing auto
let showRings = (localStorage.getItem('showRings') ?? '1') === '1';
let ringSpacing = localStorage.getItem('ringSpacing') || 'auto';

const FT_PER_HPA = 27;
let icaoRanges = [];  // parsed ICAO24 filter, set after parseRanges is defined
let aircraft = new Map();
let trails = new Map();
let trailLastSample = new Map();
let acState = new Map(); // hex -> {lastPosLat,lastPosLon,lastPosTime,lastMoveTime,stationarySince}

const center = { ...window.RADAR_CENTER };

// Elements
const trafficListEl = document.getElementById('trafficList');
const statusEl = document.getElementById('status');
const utcClockEl = document.getElementById('utcClock');
const themeSelect = document.getElementById('themeSelect');
const grayBgInput = document.getElementById('grayBgInput');
const applyGrayBgBtn = document.getElementById('applyGrayBg');
const resetUiBtn = document.getElementById('resetUi');
const centerLatInput = document.getElementById('centerLatInput');
const centerLonInput = document.getElementById('centerLonInput');
const applyCenterBtn = document.getElementById('applyCenter');
const centerReadoutEl = document.getElementById('centerReadout');

const rangeInput = document.getElementById('rangeNm');
const zoomInBtn = document.getElementById('zoomIn');
const zoomOutBtn = document.getElementById('zoomOut');
const btnZoomIn = document.getElementById('btnZoomIn');
const btnZoomOut = document.getElementById('btnZoomOut');
const icaoFilterTA = document.getElementById('icaoFilter');
const applyFilterBtn = document.getElementById('applyFilter');
const showCallsignCb = document.getElementById('showCallsign');
const showAltCb = document.getElementById('showAlt');
const showHdgCb = document.getElementById('showHdg');
const showTrailCb = document.getElementById('showTrail');
const trailLenSel = document.getElementById('trailLenSec');
const showSpdCb = document.getElementById('showSpd');
const showSquawkCb = document.getElementById('showSquawk');
const showVectorCb = document.getElementById('showVector');
const preventOverlapCb = document.getElementById('preventOverlap');
const vectorMinsSel = document.getElementById('vectorMins');
const labelModeSel = document.getElementById('labelMode');
const labelStyleSel = document.getElementById('labelStyle');
const showAirportsCb = document.getElementById('showAirports');
const showNavaidsCb = document.getElementById('showNavaids');

const showFixesCb = document.getElementById('showFixes');
const navRangeSel = document.getElementById('navRangeNm');
const reloadNavBtn = document.getElementById('reloadNav');
const staleTimeoutSel = document.getElementById('staleTimeout');
const posTimeoutSel = document.getElementById('posTimeout');
const trafficSortSel = document.getElementById('trafficSort');
const qnhInput = document.getElementById('qnhInput');
const qnhUpBtn = document.getElementById('qnhUp');
const qnhDownBtn = document.getElementById('qnhDown');
// NEW rings controls
const showRingsCb = document.getElementById('showRings');
const ringSpacingSel = document.getElementById('ringSpacing');

// Restore saved center
const savedCLat = parseFloat(localStorage.getItem('centerLat') || 'NaN');
const savedCLon = parseFloat(localStorage.getItem('centerLon') || 'NaN');
if(Number.isFinite(savedCLat) && Number.isFinite(savedCLon)){ center.lat = savedCLat; center.lon = savedCLon; }
if(centerLatInput) centerLatInput.value = Number(center.lat).toFixed(4);
if(centerLonInput) centerLonInput.value = Number(center.lon).toFixed(4);
if(centerReadoutEl) centerReadoutEl.textContent = `${Number(center.lat).toFixed(4)}, ${Number(center.lon).toFixed(4)}`;

// Init control values
if(rangeInput) rangeInput.value = rangeNm;
if(icaoFilterTA) icaoFilterTA.value = localStorage.getItem('icaoRanges') || '';
if(showCallsignCb) showCallsignCb.checked = showCallsign;
if(showAltCb) showAltCb.checked = showAlt;
if(showHdgCb) showHdgCb.checked = showHdg;
if(showTrailCb) showTrailCb.checked = showTrail;

if(trailLenSel) trailLenSel.value = String(trailLenSec);
if(showSpdCb) showSpdCb.checked = showSpd;
if(showSquawkCb) showSquawkCb.checked = showSquawk;
if(showVectorCb) showVectorCb.checked = showVector;
if(preventOverlapCb) preventOverlapCb.checked = preventOverlap;
if(vectorMinsSel) vectorMinsSel.value = String(vectorMins);
if(labelModeSel) labelModeSel.value = labelMode;
if(labelStyleSel) labelStyleSel.value = labelStyle;
if(showAirportsCb) showAirportsCb.checked = showAirports;
if(showNavaidsCb) showNavaidsCb.checked = showNavaids;
if(showFixesCb) showFixesCb.checked = showFixes;
if(navRangeSel) navRangeSel.value = String(navRangeNm);
if(staleTimeoutSel) staleTimeoutSel.value = String(staleTimeoutMin);
if(posTimeoutSel) posTimeoutSel.value = String(posLossTimeoutSec);
if(trafficSortSel) trafficSortSel.value = trafficSort;
// NEW rings UI init
if(showRingsCb) showRingsCb.checked = showRings;
if(ringSpacingSel) ringSpacingSel.value = ringSpacing;

if(themeSelect){ themeSelect.value = theme; themeSelect.onchange = () => { theme = themeSelect.value; applyTheme(); }; }
if(grayBgInput){ const gb = localStorage.getItem('grayBg') || '#cfcfcf'; grayBgInput.value = gb; }
if(qnhInput) qnhInput.value = isFinite(qnh)? Math.round(qnh).toString() : '1013';
if(resetUiBtn){ resetUiBtn.onclick = ()=>{ localStorage.clear(); location.reload(); }; }

function savePrefs(){
  localStorage.setItem('rangeNm', rangeNm);
  localStorage.setItem('showCallsign', showCallsign ? '1' : '0');
  localStorage.setItem('showAlt', showAlt ? '1' : '0');
  localStorage.setItem('showHdg', showHdg ? '1' : '0');
  localStorage.setItem('showTrail', showTrail ? '1' : '0');
  localStorage.setItem('trailLenSec', String(trailLenSec));
  localStorage.setItem('showSpd', showSpd ? '1' : '0');
  localStorage.setItem('showSquawk', showSquawk ? '1' : '0');
  localStorage.setItem('showVector', showVector ? '1' : '0');
  localStorage.setItem('preventOverlap', preventOverlap ? '1' : '0');
  localStorage.setItem('vectorMins', String(vectorMins));
  localStorage.setItem('showAirports', showAirports ? '1' : '0');
  localStorage.setItem('showNavaids', showNavaids ? '1' : '0');
  localStorage.setItem('showFixes', showFixes ? '1' : '0');
  localStorage.setItem('labelMode', labelMode);
  localStorage.setItem('navRangeNm', String(navRangeNm));
  localStorage.setItem('staleTimeoutMin', String(staleTimeoutMin));
  localStorage.setItem('posLossTimeoutSec', String(posLossTimeoutSec));
  localStorage.setItem('trafficSort', trafficSort);
  localStorage.setItem('qnh', String(qnh));
  localStorage.setItem('showRings', showRings ? '1':'0');
  localStorage.setItem('ringSpacing', ringSpacing);
}

// Handlers
if(zoomInBtn) zoomInBtn.onclick = () => { rangeNm = Math.max(10, rangeNm - 10); if(rangeInput) rangeInput.value = rangeNm; savePrefs(); try{requestOverlayFetch()}catch(_e){}; };
if(zoomOutBtn) zoomOutBtn.onclick = () => { rangeNm = Math.min(400, rangeNm + 10); if(rangeInput) rangeInput.value = rangeNm; savePrefs(); try{requestOverlayFetch()}catch(_e){}; };
if(btnZoomIn) btnZoomIn.onclick = () => zoomInBtn && zoomInBtn.onclick();
if(btnZoomOut) btnZoomOut.onclick = () => zoomOutBtn && zoomOutBtn.onclick();
if(rangeInput) rangeInput.onchange = () => { rangeNm = Math.max(5, Math.min(400, parseFloat(rangeInput.value) || 20)); rangeInput.value = rangeNm; savePrefs(); try{requestOverlayFetch()}catch(e){} };
if(showCallsignCb) showCallsignCb.onchange = () => { showCallsign = showCallsignCb.checked; savePrefs(); };
if(showAltCb) showAltCb.onchange = () => { showAlt = showAltCb.checked; savePrefs(); };
if(showHdgCb) showHdgCb.onchange = () => { showHdg = showHdgCb.checked; savePrefs(); };
if(showTrailCb) showTrailCb.onchange = () => { showTrail = showTrailCb.checked; if(!showTrail){ trails.clear(); trailLastSample.clear(); } savePrefs(); };
if(trailLenSel) trailLenSel.onchange = () => { trailLenSec = parseFloat(trailLenSel.value)||60; savePrefs(); };
if(showSpdCb) showSpdCb.onchange = () => { showSpd = showSpdCb.checked; savePrefs(); };
if(showSquawkCb) showSquawkCb.onchange = () => { showSquawk = showSquawkCb.checked; savePrefs(); };
if(showVectorCb) showVectorCb.onchange = () => { showVector = showVectorCb.checked; savePrefs(); };
if(preventOverlapCb) preventOverlapCb.onchange = () => { preventOverlap = preventOverlapCb.checked; savePrefs(); };
if(vectorMinsSel) vectorMinsSel.onchange = () => { vectorMins = parseFloat(vectorMinsSel.value)||0.5; savePrefs(); };
if(applyFilterBtn) applyFilterBtn.onclick = () => { localStorage.setItem('icaoRanges', icaoFilterTA.value.trim()); icaoRanges = parseRanges(icaoFilterTA.value.trim()); };
if(labelModeSel) labelModeSel.onchange = () => { labelMode = labelModeSel.value; savePrefs(); };
if(labelStyleSel) labelStyleSel.onchange = () => {
  labelStyle = labelStyleSel.value === 'topsky' ? 'topsky' : 'classic';
  localStorage.setItem('labelStyle', labelStyle);
  if(labelStyle !== 'topsky' && tsUi) tsUi.clear();
};

// --- TopSky labels (topsky.js) ---
let tsPos = {};            // hex -> chosen label position (0-15), keeps labels from jumping
let tsRects = {};          // hex -> label box of the last frame
let tsTargetsLast = [];    // [[hex, x, y]] of the symbols drawn in the last frame
// level in hundreds of feet, 3 digits: QNH altitude below 5000 ft (as the classic A-level), else FL
function tsLvl3(alt){
  const adj = correctedAltFt(Number(alt));
  return String(Math.max(0, Math.round((adj < 5000 ? adj : Number(alt)) / 100))).padStart(3,'0');
}
// --- Pointing at an aircraft from outside (EFHK traffic window): a blinking ring for 6 s,
// and with TopSky labels the aircraft is selected (its extended label stays open) ---
let flashHex = null, flashUntil = 0;
window.radarHasAircraft = hex => {
  const a = aircraft.get(String(hex || '').toUpperCase());
  return !!a && Number.isFinite(a.lat) && Number.isFinite(a.lon);
};
window.radarSelect = hex => {
  hex = String(hex || '').toUpperCase();
  flashHex = hex; flashUntil = Date.now() + 6000;
  if(labelStyle === 'topsky' && tsUi) tsUi.select(hex);
};
// --- Move the map by dragging it with the mouse (a click without moving still selects) ---
let mapDrag = null;          // {x, y, lat, lon, moved} while the mouse button is down on the scope
let mapJustDragged = false;  // swallow the click that ends a drag
function scopeRadiusPx(){ const w = canvas.width / DPR, h = canvas.height / DPR; return Math.min(w, h) / 2 - 24; }
canvas.addEventListener('mousedown', e => {
  if(e.button !== 0) return;
  mapJustDragged = false;     // a drag that ended outside the scope left no click to swallow
  mapDrag = {x: e.clientX, y: e.clientY, lat: center.lat, lon: center.lon, moved: false};
});
document.addEventListener('mousemove', e => {
  if(!mapDrag) return;
  const dx = e.clientX - mapDrag.x, dy = e.clientY - mapDrag.y;
  if(!mapDrag.moved && Math.hypot(dx, dy) < 4) return;          // a small wobble is still a click
  mapDrag.moved = true;
  canvas.style.cursor = 'grabbing';
  const nmPerPx = rangeNm / Math.max(10, scopeRadiusPx());
  const la = mapDrag.lat + (dy * nmPerPx) / 60;
  const lo = mapDrag.lon - (dx * nmPerPx) / (60 * Math.cos(la * Math.PI / 180));
  setCenter(la, lo, false);
});
document.addEventListener('mouseup', () => {
  if(!mapDrag) return;
  if(mapDrag.moved){ mapJustDragged = true; canvas.style.cursor = ''; setCenter(center.lat, center.lon, true); }
  mapDrag = null;
});
canvas.addEventListener('click', e => {           // capture: before the TopSky click handling
  if(mapJustDragged){ mapJustDragged = false; e.stopImmediatePropagation(); }
}, true);
// the home button (⌂) under the zoom buttons: back to the default centre (EFHK)
const btnHome = document.getElementById('btnHome');
if(btnHome) btnHome.onclick = () => setCenter(window.RADAR_CENTER.lat, window.RADAR_CENTER.lon, true);

const tsUi = (typeof Topsky !== 'undefined') ? Topsky.interaction(canvas, {
  active: () => labelStyle === 'topsky',
  busy: () => !!(mapDrag && mapDrag.moved),
  targets: () => tsTargetsLast,
  rects: () => tsRects,
}) : null;
if(showAirportsCb) showAirportsCb.onchange = () => { showAirports = showAirportsCb.checked; savePrefs(); };
if(showNavaidsCb) showNavaidsCb.onchange = () => { showNavaids = showNavaidsCb.checked; savePrefs(); };
if(showFixesCb) showFixesCb.onchange = () => { showFixes = showFixesCb.checked; savePrefs(); };
const navFetch = ()=>{ fetchNavaids(); fetchNavMeta(); loadOverlayMeta(); };
if(navRangeSel) navRangeSel.onchange = () => { navRangeNm = parseFloat(navRangeSel.value)||100; savePrefs(); navFetch(); };
if(reloadNavBtn) reloadNavBtn.onclick = navFetch;
if(staleTimeoutSel) staleTimeoutSel.onchange = () => { const v = parseFloat(staleTimeoutSel.value); staleTimeoutMin = Number.isFinite(v) ? v : 2; savePrefs(); };
if(posTimeoutSel) posTimeoutSel.onchange = () => { const v = parseFloat(posTimeoutSel.value); posLossTimeoutSec = Number.isFinite(v) ? v : 30; savePrefs(); };
if(trafficSortSel) trafficSortSel.onchange = () => { trafficSort = trafficSortSel.value; savePrefs(); };
// --- Auto QNH from the latest METAR (server: /api/qnh, refreshed every 10 min) ---
// On by default; the user's choice is remembered.
let qnhAuto = (localStorage.getItem('qnhAuto') ?? '1') === '1';
const qnhAutoCb = document.getElementById('qnhAuto');
const qnhInfoEl = document.getElementById('qnhInfo');
function applyQnhAutoUi(){
  if(qnhAutoCb) qnhAutoCb.checked = qnhAuto;
  for(const el of [qnhInput, qnhUpBtn, qnhDownBtn]){ if(el) el.disabled = qnhAuto; }
  if(qnhInfoEl && !qnhAuto){ qnhInfoEl.textContent = ''; qnhInfoEl.title = ''; }
}
async function fetchQnh(){
  if(!qnhAuto) return;
  try{
    const r = await fetch('/api/qnh', {cache:'no-store'});
    const j = await r.json();
    if(!qnhAuto) return;
    if(Number.isFinite(j.qnh)){
      qnh = j.qnh;
      if(qnhInput) qnhInput.value = String(Math.round(qnh));
      savePrefs();
      const old = (j.error && Number.isFinite(j.age_sec)) ? ` (last good ${Math.round(j.age_sec/60)} min ago)` : '';
      if(qnhInfoEl){ qnhInfoEl.textContent = `METAR ${j.station} ${j.obs_time || ''}: Q${Math.round(qnh)}${old}`; qnhInfoEl.title = j.metar || ''; }
    } else if(qnhInfoEl){
      qnhInfoEl.textContent = `METAR ${j.station || ''} not available – using QNH ${Math.round(qnh)}`;
      qnhInfoEl.title = j.error || '';
    }
  }catch(e){
    if(qnhInfoEl){ qnhInfoEl.textContent = `METAR not available – using QNH ${Math.round(qnh)}`; qnhInfoEl.title = ''; }
  }
}
if(qnhAutoCb) qnhAutoCb.onchange = () => {
  qnhAuto = qnhAutoCb.checked;
  localStorage.setItem('qnhAuto', qnhAuto ? '1' : '0');
  applyQnhAutoUi();
  fetchQnh();
};
applyQnhAutoUi(); fetchQnh();
setInterval(fetchQnh, 5*60*1000);

if(qnhInput) qnhInput.onchange = () => { const v = parseFloat(qnhInput.value); qnh = Number.isFinite(v)? v : 1013; qnhInput.value = String(Math.round(qnh)); savePrefs(); };
if(qnhUpBtn) qnhUpBtn.onclick = () => { let v = parseFloat(qnhInput.value||'1013'); if(!Number.isFinite(v)) v = 1013; v = Math.min(1050, v+1); qnh = v; qnhInput.value = String(Math.round(v)); savePrefs(); };
if(qnhDownBtn) qnhDownBtn.onclick = () => { let v = parseFloat(qnhInput.value||'1013'); if(!Number.isFinite(v)) v = 1013; v = Math.max(950, v-1); qnh = v; qnhInput.value = String(Math.round(v)); savePrefs(); };
if(showRingsCb) showRingsCb.onchange = () => { showRings = showRingsCb.checked; savePrefs(); };
if(ringSpacingSel) ringSpacingSel.onchange = () => { ringSpacing = ringSpacingSel.value; savePrefs(); };

function applyGrayBgValue(v){
  if(!/^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/.test(v)) return false;
  localStorage.setItem('grayBg', v);
  document.documentElement.style.setProperty('--gray-bg', v);
  return true;
}
if(applyGrayBgBtn) applyGrayBgBtn.onclick = () => { const v = (grayBgInput.value||'').trim(); if(applyGrayBgValue(v)) applyTheme(); };

if(applyCenterBtn){
  applyCenterBtn.onclick = () => {
    const la = parseFloat(centerLatInput.value);
    const lo = parseFloat(centerLonInput.value);
    if(Number.isFinite(la) && Number.isFinite(lo)) setCenter(la, lo, true);
  };
}
// Centre of the scope: Manual Center, dragging the map, the home (⌂) button.
// reload = fetch the navaids and map lines for the new centre (after a drag: once, at the end).
function setCenter(la, lo, reload){
  la = Math.max(-85, Math.min(85, la)); lo = ((lo + 540) % 360) - 180;
  center.lat = la; center.lon = lo;
  localStorage.setItem('centerLat', String(la));
  localStorage.setItem('centerLon', String(lo));
  if(centerReadoutEl) centerReadoutEl.textContent = `${la.toFixed(4)}, ${lo.toFixed(4)}`;
  if(centerLatInput) centerLatInput.value = la.toFixed(4);
  if(centerLonInput) centerLonInput.value = lo.toFixed(4);
  if(reload){ fetchNavaids(); fetchNavMeta(); requestOverlayFetch(); }
}

// --- Own position: a small marker at the user's position (decimal degrees), kept in this browser ---
const ownPos = {
  on: localStorage.getItem('ownPosOn') === '1',
  lat: parseFloat(localStorage.getItem('ownLat') ?? 'NaN'),
  lon: parseFloat(localStorage.getItem('ownLon') ?? 'NaN'),
};
(function(){
  const cb = document.getElementById('ownPosOn');
  const la = document.getElementById('ownLatInput');
  const lo = document.getElementById('ownLonInput');
  const btn = document.getElementById('applyOwnPos');
  if(!cb || !la || !lo) return;
  if(Number.isFinite(ownPos.lat)) la.value = String(ownPos.lat);
  if(Number.isFinite(ownPos.lon)) lo.value = String(ownPos.lon);
  cb.checked = ownPos.on;
  // returns true when both fields hold a valid coordinate (and stores it)
  function take(){
    const v1 = parseFloat(String(la.value).replace(',', '.')), v2 = parseFloat(String(lo.value).replace(',', '.'));
    const ok1 = Number.isFinite(v1) && v1 >= -90 && v1 <= 90, ok2 = Number.isFinite(v2) && v2 >= -180 && v2 <= 180;
    la.classList.toggle('invalid', !ok1); lo.classList.toggle('invalid', !ok2);
    if(!(ok1 && ok2)) return false;
    ownPos.lat = v1; ownPos.lon = v2;
    localStorage.setItem('ownLat', String(v1)); localStorage.setItem('ownLon', String(v2));
    return true;
  }
  function setOn(on){ ownPos.on = on; cb.checked = on; localStorage.setItem('ownPosOn', on ? '1' : '0'); }
  if(btn) btn.onclick = () => { if(take()) setOn(true); };
  for(const el of [la, lo]) el.addEventListener('keydown', e => { if(e.key === 'Enter' && take()) setOn(true); });
  cb.onchange = () => { setOn(cb.checked && (Number.isFinite(ownPos.lat) && Number.isFinite(ownPos.lon) ? true : take())); };
})();
function drawOwnPosition(cx, cy, R, obst){
  if(!ownPos.on || !Number.isFinite(ownPos.lat) || !Number.isFinite(ownPos.lon)) return;
  const pr = projectNm(ownPos.lat, ownPos.lon);
  const x = cx + (pr.x / rangeNm) * R, y = cy - (pr.y / rangeNm) * R;
  ctx.save();
  setStroke(colors.own || colors.symbol); ctx.lineWidth = 1.2; ctx.lineJoin = 'miter';
  ctx.beginPath(); ctx.moveTo(x, y-4); ctx.lineTo(x+3.5, y+2.5); ctx.lineTo(x-3.5, y+2.5); ctx.closePath(); ctx.stroke();   // small triangle
  ctx.restore();
  if(obst) obst.push({x: x-6, y: y-6, w: 12, h: 10});
}

// Utils
function parseRanges(str){
  if(!str) return [];
  const parts = str.split(/[,;\s]+/).filter(Boolean);
  const out = [];
  for(const p of parts){
    if(p.includes('-')){
      const [a,b] = p.split('-').map(x => x.trim());
      const lo = parseInt(a, 16), hi = parseInt(b, 16);
      if(Number.isFinite(lo) && Number.isFinite(hi)) out.push([Math.min(lo,hi), Math.max(lo,hi)]);
    } else {
      const v = parseInt(p,16);
      if(Number.isFinite(v)) out.push([v,v]);
    }
  }
  return out;
}
icaoRanges = parseRanges(localStorage.getItem('icaoRanges') || '');
function inRanges(hex, ranges){
  if(ranges.length === 0) return true;
  const v = parseInt(hex, 16);
  if(!Number.isFinite(v)) return false;
  return ranges.some(([lo,hi]) => v >= lo && v <= hi);
}
function deg2rad(d){ return d*Math.PI/180; }
function projectNm(lat, lon){
  const dLat = deg2rad(lat - center.lat);
  const dLon = deg2rad(lon - center.lon);
  const x = (dLon * 180/Math.PI) * 60 * Math.cos(deg2rad(center.lat));
  const y = (dLat * 180/Math.PI) * 60;
  return {x,y};
}
function distanceNm(lat1, lon1, lat2, lon2){
  const dLat = (lat2 - lat1) * 60;
  const dLon = (lon2 - lon1) * 60 * Math.cos((lat1*Math.PI/180));
  return Math.hypot(dLat, dLon);
}

// altitude formatters
function correctedAltFt(alt){
  if(!Number.isFinite(alt)) return alt;
  if(alt < 5000 && Number.isFinite(qnh)){
    const delta = (qnh - 1013.25) * 27;
    return alt + delta;
  }
  return alt;
}
function formatAltCode(alt){
  if(!Number.isFinite(alt)) return '---';
  const adj = correctedAltFt(Number(alt));
  if(Number.isFinite(adj) && adj < 5000){
    const ah = Math.round(adj/100);
    return `A${String(ah).padStart(3,'0')}`;
  }
  const fl = Math.round(Number(alt)/100);
  return `F${String(fl).padStart(3,'0')}`;
}
function formatAltWithTrend(alt, vr){
  const NBSP = NBSP_GLOBAL;
  const base = formatAltCode(alt);
  const th = 50;
  if(!Number.isFinite(vr)) return base + NBSP;
  if(vr > th)  return base + '+';
  if(vr < -th) return base + '-';
  return base + NBSP;
}
function normalizeNbsp(s){ if(s==null) return s; try{ return String(s).replace(/\\u00A0/g, NBSP_GLOBAL); }catch(_){ return s; } }
function nbspize(s){ const ch = NBSP_GLOBAL; return String(s).split(ch).join('&nbsp;'); }

function escapeHTML(s){
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}
function altToHTML(s){
  if(s==null) return '';
  const real = normalizeNbsp(String(s));
  const escaped = real.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
  return escaped.replace(/\u00A0/g,'&nbsp;').replace(/\\u00A0/g,'&nbsp;');
}
let _trafficLastHTML = '';
let _trafficLastTs = 0;
let _trafficPointerDown = false;  // see traffic list click handling near the end

// Canvas
function resizeCanvas(){
  let rect = null;
  try{ rect = canvas.getBoundingClientRect ? canvas.getBoundingClientRect() : null; }catch(e){ rect = null; }
  let w = rect && rect.width ? rect.width : (window.innerWidth - 340);
  let h = rect && rect.height ? rect.height : (window.innerHeight);
  if(!Number.isFinite(w) || w < 100) w = Math.max(300, window.innerWidth - 340);
  if(!Number.isFinite(h) || h < 100) h = Math.max(300, window.innerHeight);
  canvas.width = Math.floor(w * DPR);
  canvas.height = Math.floor(h * DPR);
  ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
}
window.addEventListener('resize', resizeCanvas);
document.addEventListener('DOMContentLoaded', resizeCanvas);
resizeCanvas();

// Data
let lastDataOkMs = Date.now();     // last successful /api/aircraft response
const SERVER_LOST_SEC = 30;        // clear targets if the server itself is unreachable this long
function setStatus(text, warn){
  if(!statusEl) return;
  statusEl.textContent = text;
  statusEl.classList.toggle('warn', !!warn);
}
async function fetchData(){
  try{
    const res = await fetch('/api/aircraft', {cache:'no-store'});
    if(!res.ok) throw new Error('HTTP ' + res.status);
    const j = await res.json();
    lastDataOkMs = Date.now();
    const arr = Array.isArray(j.aircraft) ? j.aircraft : [];
    let count = 0;
    const next = new Map();
    const now = Date.now();
    for(const raw of arr){
      const ac = normalizeAircraft(raw);
      if(!ac.hex) continue;
      next.set(ac.hex, ac);
      count++;
      const s = acState.get(ac.hex) || {};
      const MOVE_THRESH_NM = 0.02; // ~37 m to ignore jitter
      if(Number.isFinite(ac.lat) && Number.isFinite(ac.lon)){
        if(!Number.isFinite(s.lastPosLat) || !Number.isFinite(s.lastPosLon)){
          s.lastPosLat = ac.lat; s.lastPosLon = ac.lon;
          s.lastPosTime = now;
          s.lastMoveTime = now;
          s.stationarySince = now;
        } else {
          const dnm = distanceNm(s.lastPosLat, s.lastPosLon, ac.lat, ac.lon);
          s.lastPosTime = now;
          s.lastPosLat = ac.lat; s.lastPosLon = ac.lon;
          if(dnm >= MOVE_THRESH_NM){
            s.lastMoveTime = now;
            s.stationarySince = null;
          } else {
            s.stationarySince = s.stationarySince || now;
          }
        }
      }
      acState.set(ac.hex, s);
    }
    for(const hex of Array.from(acState.keys())){ if(!next.has(hex)) acState.delete(hex); }
    // forget trails of aircraft that are no longer in the feed
    for(const hex of Array.from(trails.keys())){ if(!next.has(hex)){ trails.delete(hex); trailLastSample.delete(hex); } }
    aircraft = next;
    if(tsUi) tsUi.forget(new Set(next.keys()));
    const upd = new Date().toISOString().slice(11,19) + 'Z';
    if(j.feed_lost){
      const age = Number.isFinite(j.feed_age) ? `no data for ${Math.round(j.feed_age)} s` : 'no data yet';
      setStatus(`FEED LOST – ${age}${j.error ? ' (' + j.error + ')' : ''} | Checked: ${upd}`, true);
    } else if(j.error){
      setStatus(`Targets: ${count} | Updated: ${upd} | Feed problem: ${j.error}`, true);
    } else {
      setStatus(`Targets: ${count} | Updated: ${upd}`, false);
    }
  }catch(e){
    const down = Math.round((Date.now() - lastDataOkMs)/1000);
    if(down > SERVER_LOST_SEC && aircraft.size){ aircraft = new Map(); acState.clear(); trails.clear(); trailLastSample.clear(); }
    setStatus(`Radar server not reachable (${down} s)`, true);
  }
}
setInterval(fetchData, 5000); fetchData();

// Navaids: server returns only the points within navRangeNm of the current center
async function fetchNavaids(){
  try{
    const q = `clat=${center.lat.toFixed(5)}&clon=${center.lon.toFixed(5)}&nmr=${navRangeNm}`;
    const res = await fetch(`/api/navaids?${q}`, {cache:'no-store'});
    const raw = await res.json();
    function within(lat, lon, nmr){
      if(!Number.isFinite(lat) || !Number.isFinite(lon)) return false;
      const d = distanceNm(center.lat, center.lon, lat, lon);
      return d <= nmr;
    }
    const out = {airports:[], navaids:[], fixes:[]};
    for(const key of ['airports','navaids','fixes']){
      const src = Array.isArray(raw[key]) ? raw[key] : [];
      for(const it of src){
        const la = Number(it.lat), lo = Number(it.lon);
        if(!Number.isFinite(la) || !Number.isFinite(lo)) continue;
        if(within(la,lo, navRangeNm)) out[key].push(it);
      }
    }
    window.navaidsData = out;
  }catch(e){}
}
async function fetchNavMeta(){
  try{
    const r = await fetch('/api/navaids_meta', {cache:'no-store'});
    const j = await r.json();
    const c = j.counts || {};
    const el = document.getElementById('navMeta');
    if(el){ window.navMetaBase = `Navaids: airports ${c.airports||0}, navaids ${c.navaids||0}, fixes ${c.fixes||0}`; el.textContent = window.navMetaBase; }
  }catch(e){}
}
fetchNavaids(); fetchNavMeta(); loadOverlayMeta();

function normalizeAircraft(a){
  const hex = (a.hex || a.icao24 || '').toString().toUpperCase();
  const callsign = (a.flight || a.callsign || a.ident || '').trim();
  const lat = Number(a.lat ?? a.latitude ?? NaN);
  const lon = Number(a.lon ?? a.longitude ?? NaN);
  const alt = a.alt_baro ?? a.baro_altitude ?? a.altitude ?? a.alt_geom ?? null;
  const hdg = a.track ?? a.heading ?? a.true_heading ?? null;
  const gs  = a.gs ?? a.speed ?? a.ground_speed ?? null;
  const vr  = a.baro_rate ?? a.vert_rate ?? a.vertical_rate ?? null;
  const squawk = a.squawk ?? a.sqk ?? a.mode_a ?? a.squawk_code ?? null;
  const reg = a.reg ?? a.registration ?? null;
  const type = a.type ?? a.icao_type ?? a.icaoType ?? a.icao_type_code ?? a.IcaoTypeCode ?? null;
  const sel_alt_ft = (a.sel_alt_ft!==undefined && a.sel_alt_ft!==null && !Number.isNaN(Number(a.sel_alt_ft))) ? Number(a.sel_alt_ft) : null;
  const sel_alt_hundreds = (a.sel_alt_hundreds!==undefined && a.sel_alt_hundreds!==null && !Number.isNaN(Number(a.sel_alt_hundreds))) ? Number(a.sel_alt_hundreds) : null;
  return {hex, callsign, lat, lon, alt, hdg, gs, vr, squawk, reg, type, sel_alt_ft, sel_alt_hundreds};
}

// Drawing helpers
function setFill(c){ ctx.fillStyle = c; }
function setStroke(c){ ctx.strokeStyle = c; }


function drawNavaidsLayer(cx, cy, R, obst){   // obst: TopSky label obstacles (symbol + name boxes)
  let inView = {airports:0, navaids:0, fixes:0};
  const lineW = (typeof theme!=='undefined' && theme==='gray') ? 1.6 : 1.2;
  const data = window.navaidsData || {};
  const datasets = [
    {flag: showAirports, key: 'airports', color: colors.airport, type:'apt'},
    {flag: showNavaids,  key: 'navaids',  color: colors.navaid,  type:'nav'},
    {flag: showFixes,    key: 'fixes',    color: colors.fix,     type:'fix'},
  ];
  ctx.save();
  ctx.globalAlpha = 1.0;
  ctx.lineWidth = lineW;
  ctx.font = '10px ui-monospace, monospace';
  ctx.textAlign = 'left'; ctx.textBaseline = 'middle';
  for(const ds of datasets){
    if(!ds.flag) continue;
    const arr = data[ds.key] || [];
    for(const it of arr){
      const lat = Number(it.lat), lon = Number(it.lon);
      if(!Number.isFinite(lat) || !Number.isFinite(lon)) continue;
      const proj = projectNm(lat, lon);
      const rnm = Math.hypot(proj.x, proj.y);
      if(rnm > rangeNm) continue; else { inView[ds.key] = (inView[ds.key]||0)+1; }
      const px = cx + (proj.x / rangeNm) * R;
      const py = cy - (proj.y / rangeNm) * R;
      let col = ds.color || '#00ff66';
      if(!col || col === colors.bg) col = (theme==='green'||theme==='full-el')? '#00ff66' : '#222222';
      setStroke(col); setFill(col);
      if(ds.type==='apt'){ ctx.beginPath(); ctx.moveTo(px, py-4); ctx.lineTo(px+4, py); ctx.lineTo(px, py+4); ctx.lineTo(px-4, py); ctx.closePath(); ctx.stroke(); ctx.fillRect(px-1, py-1, 2, 2); }
      else if(ds.type==='nav'){ ctx.beginPath(); ctx.arc(px, py, 3.5, 0, Math.PI*2); ctx.stroke(); ctx.beginPath(); ctx.arc(px, py, 2.2, 0, Math.PI*2); ctx.fill(); }
      else { ctx.strokeRect(px-3, py-3, 6, 6); ctx.fillRect(px-3, py-3, 6, 6); }
      const ident = (it.ident || it.name || '').toString().trim();
      if(ident){ ctx.fillText(ident, px+6, py); }
      if(obst) obst.push({x: px-5, y: py-6, w: 11 + (ident ? ctx.measureText(ident).width + 2 : 0), h: 12});
    }
  }
  ctx.restore();
  try{
    const el = document.getElementById('navMeta');
    if(el){
      const base = el.dataset.base || window.navMetaBase || 'Navaids:';
      const txt = `${base} (in view: APT ${inView.airports||0}, NAV ${inView.navaids||0}, FIX ${inView.fixes||0})`;
      const nowTs = Date.now();
      if(!window._navInViewTxt || window._navInViewTxt !== txt || !window._navInViewTs || (nowTs - window._navInViewTs) > 500){
        el.textContent = txt; // hard reset; never append
        window._navInViewTxt = txt;
        window._navInViewTs = nowTs;
      }
    }
  }catch(_){ }
}

function measureBlock(ctx, lines, lineH){ let w=0; for(const ln of lines){ w=Math.max(w, ctx.measureText(ln).width); } return {w, h: lines.length*lineH}; }
function boxesOverlap(a,b,pad=0){ return !(a.x2+pad < b.x1-pad || a.x1-pad > b.x2+pad || a.y2+pad < b.y1-pad || a.y1-pad > b.y2+pad); }
function hdgQuadrant(h){
  h = ((h%360)+360)%360;
  if(h>=45 && h<135) return 'SE';
  if(h>=135 && h<225) return 'SW';
  if(h>=225 && h<315) return 'NW';
  return 'NE';
}
function oppositeQuad(q){
  return q==='NE'?'SW': q==='NW'?'SE': q==='SE'?'NW':'NE';
}
function perpendicularQuads(q){
  switch(q){
    case 'NE': return ['NW','SE'];
    case 'NW': return ['NE','SW'];
    case 'SE': return ['NE','SW'];
    case 'SW': return ['NW','SE'];
  }
  return ['NE','SW'];
}
function preferredQuads(hdgDeg, vectorQuad, vectorOn){
  const base = (hdgDeg!=null && isFinite(hdgDeg)) ? hdgQuadrant(Number(hdgDeg)) : null;
  let list = [];
  if(vectorOn && vectorQuad){
    const opp = oppositeQuad(vectorQuad);
    list.push(opp, ...perpendicularQuads(vectorQuad), vectorQuad);
  } else if(base){
    const opp = oppositeQuad(base);
    list.push(opp, ...perpendicularQuads(base), base);
  } else {
    list = ['NE','NW','SE','SW'];
  }
  const seen = new Set(); const out = [];
  for(const q of list){ if(!seen.has(q)){ out.push(q); seen.add(q);} }
  return out;
}
function spiralFallback(px, py, m){
  const steps = [12,18,24,30,36,42,48];
  const quads = ['NE','NW','SE','SW'];
  function mkBox(tx, ty){ return {tx, ty, x1:tx, y1:ty-m.h, x2:tx+m.w, y2:ty}; }
  for(const r of steps){
    for(const q of quads){
      let tx, ty;
      if(q==='NE'){ tx = px + 10 + r; ty = py - 8 - r; }
      if(q==='NW'){ tx = px - 10 - m.w - r; ty = py - 8 - r; }
      if(q==='SE'){ tx = px + 10 + r; ty = py + 8 + m.h + r; }
      if(q==='SW'){ tx = px - 10 - m.w - r; ty = py + 8 + m.h + r; }
      const bb = mkBox(tx, ty);
      let clash = false;
      for(const other of (window.labelBoxes||[])){
        if(boxesOverlap(bb, other, 8)){ clash = true; break; }
      }
      if(!clash) return bb;
    }
  }
  return null;
}
function candidateOrder(hdgDeg, vectorQuad){
  return preferredQuads(hdgDeg, vectorQuad, showVector);
}


// === Overlays (lines) ===
let overlayLayers = {};
let overlaySegments = {};
let overlayDecimate = parseInt(localStorage.getItem('overlayDecimate') || '2', 10);

function overlayCategory(name){
  const n=(name||'').toLowerCase();
  if(n.includes('coast')||n.includes('shore')) return 'Coastlines';
  if(n.includes('ils')) return 'ILS';
  if(n.includes('apt')||n.includes('airport')) return 'Airports';
  if(n.includes('fir')) return 'FIR';
  if(n.includes('border')) return 'Borders';
  if(n.includes('ats')) return 'ATS';
  if(n.includes('nav')) return 'Navaids';
  if(n.includes('aqua')||n.includes('water')) return 'Hydro';
  return 'Other';
}
async function loadOverlayMeta(){
  const listEl=document.getElementById('overlayList'); if(!listEl) return;
  try{
    const r=await fetch('/api/overlays_meta',{cache:'no-store'});
    const j=await r.json(); if(!j.ok) throw new Error(j.error||'meta');
    const layers=j.layers||{}; const cats={};
    Object.entries(layers).forEach(([nm,count])=>{
      const checked=(localStorage.getItem('ov_'+nm)||'0')==='1';
      const cat=overlayCategory(nm);
      overlayLayers[nm]={checked,count,cat};
      (cats[cat]||(cats[cat]=[])).push(nm);
    });
    if(Object.keys(layers).length===0){ listEl.textContent='No .geojson files in /data/overlays'; return; }
    listEl.innerHTML = Object.entries(cats).map(([cat,names])=>{
      const anyChecked = names.some(nm=>overlayLayers[nm].checked);
      const items = names.map(nm=>{
        const o=overlayLayers[nm];
        return `<label><input type="checkbox" data-ov="${nm}" ${o.checked?'checked':''}> ${nm} <span class="muted">(${o.count})</span></label>`;
      }).join('<br>');
      return `<div class="ov-group"><div class="ov-head"><label><input type="checkbox" data-ovcat="${cat}" ${anyChecked?'checked':''}> ${cat}</label></div><div class="ov-items">${items}</div></div>`;
    }).join('');
    listEl.querySelectorAll('input[type=checkbox][data-ov]').forEach(cb=>{
      cb.onchange=()=>{ const nm=cb.dataset.ov; overlayLayers[nm].checked=cb.checked; localStorage.setItem('ov_'+nm, cb.checked?'1':'0'); requestOverlayFetch(); };
    });
    listEl.querySelectorAll('input[type=checkbox][data-ovcat]').forEach(cb=>{
      cb.onchange=()=>{
        const cat=cb.dataset.ovcat; const on=cb.checked;
        Object.entries(overlayLayers).forEach(([nm,o])=>{
          if(o.cat===cat){ o.checked=on; localStorage.setItem('ov_'+nm,on?'1':'0'); const el=listEl.querySelector(`input[data-ov="${nm}"]`); if(el) el.checked=on; }
        });
        requestOverlayFetch();
      };
    });
    const od=document.getElementById('overlayDecimate');
    if(od){ od.value=String(overlayDecimate); od.onchange=()=>{ overlayDecimate=parseInt(od.value,10)||2; localStorage.setItem('overlayDecimate', String(overlayDecimate)); requestOverlayFetch(); }; }
  }catch(e){ listEl.textContent='Overlay meta load failed'; }
}
function requestOverlayFetch(){ clearTimeout(window._ovTimer); window._ovTimer=setTimeout(fetchOverlays,250); }

// Ensure overlays fetch once on initial load (covers saved zoom/center with preselected layers)
if(!window._ovInitKick){
  window._ovInitKick = true;
  try{
    window.addEventListener('load', ()=> setTimeout(()=>{ try{ requestOverlayFetch(); }catch(_e){} }, 300));
    document.addEventListener('DOMContentLoaded', ()=> setTimeout(()=>{ try{ requestOverlayFetch(); }catch(_e){} }, 500));
  }catch(_e){}
}
async function fetchOverlays(){
  try{
    const names=Object.entries(overlayLayers).filter(([,o])=>o.checked).map(([nm])=>nm);
    if(!names.length){ overlaySegments={}; return; }
    const centerStr = `${center.lat.toFixed(6)},${center.lon.toFixed(6)}`;
    const url=`/api/overlays_fetch?names=${encodeURIComponent(names.join(','))}&center=${centerStr}&range_nm=${rangeNm}&decimate=${overlayDecimate}`;
    const r=await fetch(url,{cache:'no-store'});
    const j=await r.json(); if(!j.ok) throw new Error(j.error||'fetch');
    overlaySegments=j.layers||{};
  }catch(e){}
}
function drawOverlays(cx,cy,R){
  const names=Object.keys(overlaySegments||{}); if(!names.length) return;
  const col = colors.navaid || colors.text || '#666';
  ctx.save(); ctx.lineWidth=1; ctx.strokeStyle=col;
  for(const nm of names){
    const list=overlaySegments[nm]||[]; const lower=nm.toLowerCase();
    if(lower.includes('ils')){ ctx.setLineDash([6,4]); ctx.lineWidth=1; }
    else if(lower.includes('coast')||lower.includes('shore')){ ctx.setLineDash([]); ctx.lineWidth=1.2; }
    else if(lower.includes('border')||lower.includes('fir')){ ctx.setLineDash([3,3]); ctx.lineWidth=1; }
    else { ctx.setLineDash([]); ctx.lineWidth=1; }
    for(const seg of list){
      ctx.beginPath(); let first=true;
      for(const p of seg){
        const pr=projectNm(p[0],p[1]);
        const x=cx+(pr.x/rangeNm)*R, y=cy-(pr.y/rangeNm)*R;
        if(first){ ctx.moveTo(x,y); first=false; } else { ctx.lineTo(x,y); }
      }
      ctx.stroke();
    }
  }
  ctx.restore();
}

// Stale = position has not changed for the stale timeout -> removed from scope and traffic list.
// (Position-loss timeout, which is shorter, first moves the target to the no-position list.)
function isStale(s, now){
  return staleTimeoutMin > 0 && !!s && !!s.stationarySince && (now - s.stationarySince) > staleTimeoutMin*60*1000;
}
function drawScope(){
  const w = canvas.width / DPR;
  const h = canvas.height / DPR;
  ctx.clearRect(0,0,w,h);
  setFill(colors.bg); ctx.fillRect(0,0,w,h);

  const margin = 24;
  const R = Math.min(w, h)/2 - margin;
  const cx = w/2, cy = h/2;
  if(!(R>10)) return;

  // Rings
  if(showRings){
    setStroke(colors.ring); ctx.lineWidth=1;
    if(ringSpacing==='auto'){
      for(const frac of [0.25,0.5,0.75,1]){ ctx.beginPath(); ctx.arc(cx, cy, R*frac, 0, Math.PI*2); ctx.stroke(); }
    } else {
      let sp = parseFloat(ringSpacing);
      if(!Number.isFinite(sp) || sp <= 0) sp = 10;
      const maxRings = Math.min(40, Math.floor(rangeNm / sp));
      for(let k=1; k<=maxRings; k++){
        const frac = (k * sp) / rangeNm;
        if(frac <= 1.0 + 1e-6){
          ctx.beginPath(); ctx.arc(cx, cy, R*frac, 0, Math.PI*2); ctx.stroke();
        }
      }
    }
  }

  drawOverlays(cx,cy,R);
  // Center cross
  setStroke(colors.center); /* center cross removed */// Header
  setFill(colors.text); ctx.font='12px ui-monospace, monospace'; ctx.textAlign='left'; ctx.textBaseline='top';
  ctx.fillText(`Range: 0 – ${rangeNm} NM`, 10, 8);

  window.labelBoxes = [];
  const ts = labelStyle === 'topsky' && typeof Topsky !== 'undefined' && tsUi;
  const tsItems = [], tsObst = [], tsTargets = [];
  if(ts){
    tsObst.push({x: 4, y: 24, w: 44, h: 116});          // the zoom and home buttons in the top-left corner
    for(const id of ['wxWindow', 'trWindow']){           // the METAR & TAF and EFHK traffic windows
      const el = document.getElementById(id);
      if(el && !el.hidden){
        const c = canvas.getBoundingClientRect(), r = el.getBoundingClientRect();
        tsObst.push({x: r.left - c.left - 4, y: r.top - c.top - 4, w: r.width + 8, h: r.height + 8});
      }
    }
  }
  const ranges = icaoRanges;
  const posList = [];
  const now = Date.now();

  // Draw aircraft with position
  for(const ac of aircraft.values()){
    const s = acState.get(ac.hex) || {};
    if(isStale(s, now)) continue;
    const hasPos = Number.isFinite(ac.lat) && Number.isFinite(ac.lon);
    let posFrozen = false;
    if(posLossTimeoutSec > 0){
      if(!hasPos) posFrozen = true;
      else if(s && s.stationarySince && (now - s.stationarySince) > posLossTimeoutSec*1000) posFrozen = true;
    }
    if(!hasPos || posFrozen) continue; // treat as MODE-S below

    if(!inRanges(ac.hex, ranges)) continue;

    const xy = projectNm(ac.lat, ac.lon);
    const rnm = Math.hypot(xy.x, xy.y);

    // Allow aircraft beyond the selected range to be visible:
    // draw them at scaled position even if they are beyond the ring
    const px = cx + (xy.x / rangeNm) * R;
    const py = cy - (xy.y / rangeNm) * R;

    // Trails (3x3 squares behind target; skip last sample so trail starts behind symbol)
    // Stored as lat/lon so they stay correct after zoom, center change or window resize.
    if(showTrail){
      const nowMs = Date.now();
      const last = trailLastSample.get(ac.hex) || 0;
      if(nowMs - last >= 5000){
        const arr = trails.get(ac.hex) || [];
        arr.push({lat:ac.lat, lon:ac.lon, ts: nowMs});
        trails.set(ac.hex, arr);
        trailLastSample.set(ac.hex, nowMs);
      }
      const arr2 = trails.get(ac.hex) || [];
      const cutoff = nowMs - (trailLenSec*1000);
      while(arr2.length && arr2[0].ts < cutoff) arr2.shift();
      trails.set(ac.hex, arr2);
      setFill(colors.trail);
      for(let i=0;i<arr2.length-1;i++){
        const tp = projectNm(arr2[i].lat, arr2[i].lon);
        const tx = cx + (tp.x / rangeNm) * R, ty = cy - (tp.y / rangeNm) * R;
        ctx.fillRect(Math.round(tx)-1, Math.round(ty)-1, 3, 3);
        if(ts) tsObst.push({x: tx-2, y: ty-2, w: 4, h: 4});
      }
    }

    // Symbol (unfilled square)
    ctx.save(); ctx.translate(px, py); setStroke(colors.symbol); ctx.lineWidth=1.5; ctx.strokeRect(-5,-5,10,10); ctx.restore();
    if(ac.hex === flashHex && now < flashUntil && Math.floor(now / 400) % 2 === 0){
      setStroke(colors.symbol); ctx.lineWidth = 1.5; ctx.beginPath(); ctx.arc(px, py, 13, 0, Math.PI*2); ctx.stroke();
    }

    // Vector
    let vectorBB = null; let vectorQuad = null;
    if(showVector && Number.isFinite(ac.hdg) && Number.isFinite(ac.gs)){
      const a = ac.hdg * Math.PI/180;
      const dnm = (ac.gs * vectorMins) / 60.0;
      const dx = Math.sin(a) * dnm;
      const dy = Math.cos(a) * dnm;
      const vx = px + (dx / rangeNm) * R;
      const vy = py - (dy / rangeNm) * R;
      setStroke(colors.symbol); ctx.lineWidth=1; ctx.beginPath(); ctx.moveTo(px,py); ctx.lineTo(vx,vy); ctx.stroke();
      if(ts) Topsky.lineObstacles(px, py, vx, vy, tsObst);
      const thick = 24;
      vectorBB = {x1: Math.min(px, vx)-thick, y1: Math.min(py, vy)-thick, x2: Math.max(px, vx)+thick, y2: Math.max(py, vy)+thick};
      if(dx >= 0 && dy >= 0) vectorQuad = 'NE'; else if(dx < 0 && dy >= 0) vectorQuad = 'NW'; else if(dx >= 0 && dy < 0) vectorQuad = 'SE'; else vectorQuad = 'SW';
    }

    // Label
    let label = (labelMode === 'icao') ? ac.hex : (labelMode === 'callsign' ? (ac.callsign || ac.hex) : ((localStorage.getItem('showCallsign')!=='0' && ac.callsign) ? ac.callsign : ac.hex));

    if(ts){
      // TopSky label: collected here, placed and drawn after all symbols (topsky.js)
      const isSel = tsUi.selected() === ac.hex, ext = isSel || tsUi.hover() === ac.hex;
      const lines = ext
        ? Topsky.extLines(ac, tsUi.data(ac.hex), {cs: label, lvl3: tsLvl3, center: [center.lat, center.lon]})
        : Topsky.labelLines(ac, label, tsLvl3);
      const sq = ac.squawk ? String(ac.squawk).trim() : '';
      tsItems.push({key: ac.hex, p: {x: px, y: py}, lines, sel: isSel, ext,
                    alt: Number.isFinite(ac.alt) ? ac.alt : 99999, emg: (!ext && Topsky.EMG.has(sq)) ? sq : ''});
      tsTargets.push([ac.hex, px, py]);
      if(isSel){ setStroke(colors.symbol); ctx.lineWidth = 1; ctx.strokeRect(px-9, py-9, 18, 18); }
      posList.push({d:rnm, label, alt: ac.alt ?? NaN, hex: ac.hex, squawk: ac.squawk, vr: ac.vr, reg: ac.reg, type: ac.type, sel_alt_ft: ac.sel_alt_ft, sel_alt_hundreds: ac.sel_alt_hundreds});
      continue;
    }

    const squawkStr = (showSquawk && ac.squawk) ? String(ac.squawk).trim() : '';
    const firstLine = label + (squawkStr? (' ' + squawkStr) : '');

    let lines = [firstLine];
    const altLine = (showAlt && Number.isFinite(ac.alt)) ? (()=>{
      let t = formatAltWithTrend(ac.alt, ac.vr);
      try{ var _h=_selHundreds(ac); var _cur=(Number.isFinite(ac.alt)? Math.round(ac.alt/100): null); t = _joinAlt(t, _cur, _h); }catch(_e){}
      if(showSpd && Number.isFinite(ac.gs)) t = `${t} ${Math.round(ac.gs)}`;
      return t;
    })() : (showSpd && Number.isFinite(ac.gs)) ? `${Math.round(ac.gs)}` : null;
    if(altLine) lines.push(altLine);
    const infoParts = [];
    if(showHdg && Number.isFinite(ac.hdg)) infoParts.push(`H${String(Math.round(ac.hdg)).padStart(3,'0')}`);
    if(isRegOn() && ac.reg){ const last = infoParts.length ? infoParts[infoParts.length-1] : ''; if(!last.includes(ac.reg)){ if(infoParts.length){ infoParts[infoParts.length-1] = last + ' ' + ac.reg; } else { infoParts.push(ac.reg); } } }
    
if(isTypeOn() && ac.type){ infoParts.push(ac.type); } /*TYPE_AFTER_REG*/
    if(infoParts.length) lines.push(infoParts.join(' '));
    lines = lines.map(normalizeNbsp);

    ctx.font='12px ui-monospace, monospace'; setFill(colors.text);
    ctx.textAlign='left'; ctx.textBaseline='bottom';
    const lineH = 13;
    const m = measureBlock(ctx, lines, lineH);
    const symBox = {x1:px-6, y1:py-6, x2:px+6, y2:py+6};

    const order = Number.isFinite(ac.hdg) ? candidateOrder(Number(ac.hdg), vectorQuad) : ['NE','NW','SE','SW'];
    let placed = null;
    const padSym = 10, padVec = 18;
    function labelBoxFor(q){
      if(q==='NE'){ const tx = px+10, ty = py-8; return {tx,ty,x1:tx,y1:ty-m.h,x2:tx+m.w,y2:ty}; }
      if(q==='NW'){ const tx = px-10-m.w, ty = py-8; return {tx,ty,x1:tx,y1:ty-m.h,x2:tx+m.w,y2:ty}; }
      if(q==='SE'){ const ty = py+8 + m.h; const tx = px+10; return {tx,ty,x1:tx,y1:ty-m.h,x2:tx+m.w,y2:ty}; }
      if(q==='SW'){ const ty = py+8 + m.h; const tx = px-10-m.w; return {tx,ty,x1:tx,y1:ty-m.h,x2:tx+m.w,y2:ty}; }
      return null;
    }
    for(const q of order){
      const bb = labelBoxFor(q);
      if(!bb) continue;
      if(boxesOverlap(bb, symBox, padSym)) continue;
      if(vectorBB && boxesOverlap(bb, vectorBB, padVec)) continue;
      if(preventOverlap){
        let ok = true;
        for(const other of window.labelBoxes){ if(boxesOverlap(bb, other, 8)){ ok=false; break; } }
        if(!ok) continue;
      }
      placed = bb; break;
    }
    if(!placed){
      for(const q of order){
        const bb = labelBoxFor(q);
        if(!bb) continue;
        if(boxesOverlap(bb, symBox, padSym)) continue;
        if(vectorBB && boxesOverlap(bb, vectorBB, padVec)) continue;
        placed = bb; break;
      }
    }
    if(!placed){ placed = spiralFallback(px, py, m) || labelBoxFor('NE'); }

    for(let i=0;i<lines.length;i++){
      const y = placed.ty - (lines.length-1-i)*lineH;
      if(i===0 && squawkStr){
        const emergency = (squawkStr==='7500' || squawkStr==='7600' || squawkStr==='7700');
        const prefix = label + ' ';
        ctx.fillText(prefix, placed.tx, y);
        const off = ctx.measureText(prefix).width;
        const was = ctx.fillStyle;
        const isFullEL = document.body.classList.contains('theme-full-el');
        if(emergency && !isFullEL){ ctx.fillStyle = '#ff2d2d'; }
        ctx.fillText(squawkStr, placed.tx + off, y);
        ctx.fillStyle = was;
      } else {
        ctx.fillText(lines[i], placed.tx, y);
      }
    }
    window.labelBoxes.push({x1:placed.x1, y1:placed.y1, x2:placed.x2, y2:placed.y2});

    posList.push({d:rnm, label, alt: ac.alt ?? NaN, hex: ac.hex, squawk: ac.squawk, vr: ac.vr, reg: ac.reg, type: ac.type, sel_alt_ft: ac.sel_alt_ft, sel_alt_hundreds: ac.sel_alt_hundreds});
  }

  // Draw navaids last (on top)
  drawNavaidsLayer(cx, cy, R, ts ? tsObst : null);
  drawOwnPosition(cx, cy, R, ts ? tsObst : null);

  // TopSky labels over everything (topsky.js)
  if(ts){
    const mono = document.body.classList.contains('theme-full-el') || document.body.classList.contains('theme-full-el-yellow');
    tsRects = Topsky.drawLabels(ctx, tsItems, w, h, tsObst, tsPos, {
      text: colors.text, leader: colors.ring, extBg: colors.bg, emg: mono ? null : '#ff2d2d',
      font: '12px ui-monospace, monospace'});
    tsTargetsLast = tsTargets;
  } else { tsRects = {}; tsTargetsLast = []; }

  // MODE-S / no-pos list
  const drawnHex = new Set(posList.map(x => x.hex));
  const noPos = [];
  for(const ac of aircraft.values()){
    if(!ac.hex || drawnHex.has(ac.hex)) continue;
    if(!inRanges(ac.hex, ranges)) continue;
    if(isStale(acState.get(ac.hex), now)) continue;
    let label = (labelMode==='callsign') ? (ac.callsign || ac.hex) : (labelMode==='icao'? ac.hex : ((showCallsign && ac.callsign)? ac.callsign : ac.hex));
    
    label = label + '*';
    const altStr = formatAltWithTrend(ac.alt, ac.vr);
    const altNum = Number.isFinite(ac.alt) ? Number(ac.alt) : NaN;
    noPos.push({label, altStr, altNum, squawk: ac.squawk, reg: ac.reg, type: ac.type, sel_alt_ft: ac.sel_alt_ft, sel_alt_hundreds: ac.sel_alt_hundreds});
  }

  // Sort & render list
  let rows = posList.map(item => ({...item, _rowType:'pos'})).concat(noPos.map(p=>({...p, _rowType:'nopos', d:Infinity})));
  function altVal(x){ const n = Number(x.alt ?? x.altNum ?? NaN); return Number.isFinite(n)? n : NaN; }
  function labelVal(x){ return String(x.label||''); }
  switch(trafficSort){
    case 'rangeDesc': rows.sort((a,b)=> (a._rowType==='pos'&&b._rowType==='pos')? (b.d-a.d) : (a._rowType==='pos'? -1 : (b._rowType==='pos'? 1 : labelVal(a).localeCompare(labelVal(b)))) ); break;
    case 'altDesc': rows.sort((a,b)=> { const av=altVal(a), bv=altVal(b); if(Number.isFinite(av)&&Number.isFinite(bv)) return bv-av; if(Number.isFinite(av)) return -1; if(Number.isFinite(bv)) return 1; return labelVal(a).localeCompare(labelVal(b)); }); break;
    case 'altAsc': rows.sort((a,b)=> { const av=altVal(a), bv=altVal(b); if(Number.isFinite(av)&&Number.isFinite(bv)) return av-bv; if(Number.isFinite(av)) return -1; if(Number.isFinite(bv)) return 1; return labelVal(a).localeCompare(labelVal(b)); }); break;
    case 'labelAsc': rows.sort((a,b)=> labelVal(a).localeCompare(labelVal(b))); break;
    case 'rangeAsc':
    default: rows.sort((a,b)=> (a._rowType==='pos'&&b._rowType==='pos')? (a.d-b.d) : (a._rowType==='pos'? -1 : (b._rowType==='pos'? 1 : labelVal(a).localeCompare(labelVal(b)))) ); break;
  }


  
function _selHundreds(obj){
  try{
    if(obj && Number.isFinite(obj.sel_alt_hundreds)) return Math.round(Number(obj.sel_alt_hundreds));
    if(obj && Number.isFinite(obj.sel_alt_ft)){
      var v = Number(obj.sel_alt_ft);
      if(v >= 1000) return Math.round(v/100);
      if(v >= 0 && v <= 600) return Math.round(v);
    }
  }catch(e){}
  return null;
}

function _joinAlt(currentStr, curHundreds, selHundreds){
  try{
    if(!(selHundreds===0 || Number.isFinite(selHundreds))) return currentStr;
    var s = String(currentStr);
    while(s.length && /\s/.test(s.charAt(s.length-1))) s = s.slice(0,-1);
    var last = s.slice(-1);
    var sign = (last==='+'||last==='-'||last.charCodeAt(0)===8722) ? last : '';
    var base = sign ? s.slice(0,-1) : s;
    var code = String(Math.round(selHundreds)).padStart(3,'0');
    if(!sign && (curHundreds===0 || Number.isFinite(curHundreds)) && Math.round(curHundreds)===Math.round(selHundreds)){
      return base + '=' + code;
    }
    if(sign) return s + code;
    return base + '-' + code;
  }catch(e){ return currentStr; }
}
const lis = rows.slice(0, 80).map(function(item){
  var raw = String(item.label || '');
  var pure = raw.replace(/\*+$/, '');
  var star = raw.endsWith('*') ? '*' : '';
  var isHex = /^[0-9A-F]{6}$/.test(pure);
  var isCs  = /^[0-9A-Z]{3,8}$/.test(pure) && !isHex;
  var link  = isCs
    ? '<a href="https://www.flightradar24.com/callsign/' + encodeURIComponent(pure) + '" target="_blank" rel="noopener noreferrer">' + escapeHTML(pure) + '</a>'
    : isHex
    ? '<a href="https://globe.adsbexchange.com/?icao=' + encodeURIComponent(pure) + '" target="_blank" rel="noopener noreferrer">' + escapeHTML(pure) + '</a>'
    : escapeHTML(pure);

  var sq = (item.squawk && String(item.squawk).trim()) || '----';
  var emg = (sq==='7500'||sq==='7600'||sq==='7700');
  var cls = emg ? 'emg' : '';

  var regTxt  = (typeof isRegOn==='function' && isRegOn() && item.reg) ? (' ' + escapeHTML(item.reg)) : '';
  var typeTxt = (typeof isTypeOn==='function' && isTypeOn() && item.type) ? (' ' + escapeHTML(item.type)) : '';

  if (item && item._rowType==='pos') {
    var nm = escapeHTML(item.d.toFixed(1).padStart(5,' '));
    var _altStr = formatAltWithTrend(item.alt, item.vr);
    try{ var _h=_selHundreds(item); var _cur=(Number.isFinite(item.alt)? Math.round(item.alt/100): null); _altStr = _joinAlt(_altStr, _cur, _h); }catch(_e){}
    var altHtml = altToHTML(_altStr);
    var sqSafe = escapeHTML(sq);
    return '<li><span>' + link + star + regTxt + typeTxt + ' · ' + nm + ' · ' + altHtml + ' <span class="sq ' + cls + '">' + sqSafe + '</span></span></li>';
  } else {
    var _altStr2 = item.altStr;
    try{ var _h=_selHundreds(item); var _cur=(Number.isFinite(item.altNum)? Math.round(item.altNum/100): null); _altStr2 = _joinAlt(_altStr2, _cur, _h); }catch(_e){}
    var altHtml2 = altToHTML(_altStr2);
    var sqSafe2 = escapeHTML(sq);
    return '<li><span>' + link + star + regTxt + typeTxt + ' · ' + altHtml2 + ' <span class="sq ' + cls + '">' + sqSafe2 + '</span></span></li>';
  }
});
  const html = lis.join('');
  const nowTs = Date.now();
  if(trafficListEl && !_trafficPointerDown && (html !== _trafficLastHTML) && (nowTs - _trafficLastTs > 250)){
    trafficListEl.innerHTML = html;
    _trafficLastHTML = html;
    _trafficLastTs = nowTs;
  }
}

// Clock + loop
function fmtClock(){
  const d=new Date(); const hh=String(d.getUTCHours()).padStart(2,'0'); const mm=String(d.getUTCMinutes()).padStart(2,'0'); const ss=String(d.getUTCSeconds()).padStart(2,'0');
  if(utcClockEl) utcClockEl.textContent = `${hh}:${mm}:${ss}`;
}
setInterval(fmtClock, 250); fmtClock();

function animate(){ try{ drawScope(); } catch(e){ try{ const el=document.getElementById('status'); if(el) el.textContent = 'Render error: ' + (e.message||e); }catch(_){} } requestAnimationFrame(animate); }
animate();


// --- Traffic list: links open in a new tab via target="_blank".
// The list is rebuilt when data changes; pause rebuilding while a mouse button / touch is down
// on it, so a click is never lost because its link was replaced between press and release.
(function(){
  const tl = document.getElementById('trafficList');
  if (!tl) return;
  tl.addEventListener('pointerdown', () => { _trafficPointerDown = true; });
  const release = () => { if(_trafficPointerDown) setTimeout(() => { _trafficPointerDown = false; }, 300); };
  window.addEventListener('pointerup', release);
  window.addEventListener('pointercancel', release);
})();

// --- Traffic Copy: robust copy with fallback (works on HTTP + Firefox)
(function(){
  const btn = document.getElementById('copyTrafficBtn');
  if (!btn) return;
  function doCopy(){
    const ul = document.getElementById('trafficList');
    if (!ul) return;
    const lines = Array.from(ul.querySelectorAll('li')).map(li => li.textContent.replace(/\s+/g,' ').trim());
    const txt = lines.join('\n');
    const done = () => {
      const old = btn.textContent;
      btn.textContent = 'Copied!';
      setTimeout(()=>{ btn.textContent = old; }, 1200);
    };
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(txt).then(done).catch(()=>fallback(txt, done));
    } else {
      fallback(txt, done);
    }
  }
  function fallback(txt, cb){
    const ta = document.createElement('textarea');
    ta.value = txt; ta.style.position='fixed'; ta.style.opacity='0'; ta.style.left='-9999px';
    document.body.appendChild(ta); ta.focus(); ta.select();
    try { document.execCommand('copy'); } catch(_) {}
    document.body.removeChild(ta); cb && cb();
  }
  btn.addEventListener('click', (e)=>{ e.preventDefault(); doCopy(); });
})();



function ensureRegControl(){
  if(document.getElementById('showReg')) return;
  // try to find the labels options container by anchoring to another known checkbox
  const anchor = document.getElementById('showHdg') || document.getElementById('showAlt') || document.querySelector('input[id^="show"]');
  if(!anchor) return;
  const lbl = document.createElement('label');
  const cb  = document.createElement('input');
  cb.type = 'checkbox'; cb.id = 'showReg';
  cb.checked = showReg;
  lbl.appendChild(cb);
  lbl.appendChild(document.createTextNode(' REG'));
  // insert after anchor's label
  const anchorLabel = anchor.closest('label') || anchor.parentElement;
  if(anchorLabel && anchorLabel.parentElement){
    anchorLabel.parentElement.appendChild(lbl);
  } else {
    document.body.appendChild(lbl);
  }
  cb.addEventListener('change', e=>{
    showReg = !!e.target.checked;
    localStorage.setItem('showReg', showReg? '1':'0');
  });
}

// Reflects Reg checkbox state reliably
function isRegOn(){
  try{
    const cb = document.getElementById('showReg');
    if(cb) return !!cb.checked;
  }catch(_e){}
  try{ return (localStorage.getItem('showReg') ?? '1') === '1'; }catch(_e){}
  return true;
}
function isTypeOn(){
  try{
    const cb = document.getElementById('showType');
    if(cb) return !!cb.checked;
  }catch(_e){}
  try{ return (localStorage.getItem('showType') ?? '0') === '1'; }catch(_e){}
  return false;
}


document.addEventListener('DOMContentLoaded', ensureRegControl);


window.addEventListener('error', (e)=>{ console.error('radar.js error', e.message); });

// --- Persist 'Type' toggle like the other label options ---
document.addEventListener('DOMContentLoaded', () => {
  try {
    const cb = document.getElementById('showType');
    if (!cb) return;
    const saved = localStorage.getItem('showType');
    if (saved !== null) cb.checked = (saved === '1');
    cb.addEventListener('change', (e) => {
      try { localStorage.setItem('showType', e.target.checked ? '1' : '0'); } catch(_) {}
    });
  } catch(_) {}
});

