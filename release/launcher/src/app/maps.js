/**
 * @file Settings > MAPS: the map lists (Part II, Part I DLC), the details panel, the Part I location and the tester import.
 */
'use strict';

let mapsSt = null,
  mapsSel = null,
  mapsDl = false;

/**
 * Draw one list of map tiles (the background picker's selection model: one active tile, an accent underline).
 * @param {string} id list element id
 * @param {object[]} list
 * @returns {void}
 */
function drawMapList(id, list) {
  $(id).innerHTML = list
    .map(
      (m) =>
        `<button class="mp" data-id="${m.id}" data-snd="click" title="${m.name}"><i style="background-image:url('../assets/maps/${m.id}.jpg')"></i><em>${m.name.toUpperCase()}</em></button>`,
    )
    .join('');
  $$('#' + id + ' .mp').forEach((b) =>
    b.addEventListener('click', () => {
      mapsSel = b.dataset.id;
      drawMapDetails();
    }),
  );
}
/**
 * Fill the details panel for the selected map (name + source, plus the DLC status of a Part I map).
 * @returns {void}
 */
function drawMapDetails() {
  const all = [...mapsSt.part2, ...mapsSt.part1];
  const m = all.find((x) => x.id === mapsSel);
  $$('#s-maps .mp').forEach((b) => b.classList.toggle('active', b.dataset.id === mapsSel));
  $('mp-dn').textContent = m ? m.name : '--';
  $('mp-ds').textContent = m
    ? mapsSt.part1.includes(m)
      ? T('The Last of Us Part I')
      : T('The Last of Us Part II')
    : '--';
  $('mp-dl').textContent = m ? T(m.place) : '--';
  $('mp-prev').style.backgroundImage = m ? `url('../assets/maps/${m.id}.jpg')` : '';
  let st = '--',
    cap = '';
  if (m) {
    if (!m.pack) st = T('Included');
    else if (m.installed) st = T('Installed');
    else if (mapsSt.tlou1.valid) st = T('Not installed');
    else st = T('Needs Part I');
    if (m.pack && !m.installed && !mapsSt.tlou1.valid)
      cap = T('Set the location of The Last of Us Part I, or import the map files.');
  }
  // import / download actions belong to Part I maps only
  $('mp-tools').hidden = !m || !mapsSt.part1.includes(m);
  $('mp-dst').textContent = st;
  $('mp-cap').textContent = cap;
}
/**
 * Redraw the whole tab from a state snapshot (also the grey-out of the Part I section).
 * @param {object} st state from main (lib/maps.js mapsState)
 * @returns {void}
 */
function drawMaps(st) {
  mapsSt = st;
  if (!mapsSel) mapsSel = st.part2[0].id;
  drawMapList('mp-list2', st.part2);
  drawMapList('mp-list1', st.part1);
  const unlocked = st.tlou1.valid || st.part1.some((m) => m.installed);
  $('mp-p1').classList.toggle('locked', !unlocked);
  $('mp-dir').value = st.tlou1.dir;
  $('mp-dir').placeholder = T('Not set');
  $('mp-clear').hidden = !st.tlou1.dir;
  $('mp-loc').hidden = !unlocked;
  $('mp-change').hidden = !unlocked;
  // TEMPORARY server download: offered while a Part I map is missing (the lock overlay has its own button)
  $('mp-get2').hidden = !unlocked || st.part1.every((m) => m.installed);
  $('mp-conv').hidden = !(st.converter && st.tlou1.valid) || st.part1.every((m) => m.installed);
  $('mp-get').hidden = st.part1.every((m) => m.installed);
  drawDownloadButtons();
  drawMapDetails();
}
/**
 * Enable / disable the download buttons and show CANCEL while the pack downloads.
 * @returns {void}
 */
function drawDownloadButtons() {
  const on = mapsDl || busy;
  $('mp-get').disabled = on;
  $('mp-get2').disabled = on;
  $('mp-conv').disabled = on;
  $('mp-cancel').hidden = !mapsDl;
}
/**
 * TEMPORARY playtester download of the prebuilt Part I map pack (the shared progress bar shows it).
 * @returns {Promise<void>}
 */
async function downloadP1() {
  if (mapsDl || busy) return;
  mapsDl = true;
  drawDownloadButtons();
  $('mp-msg').textContent = '';
  showProgress({ phase: 'check', done: 0, total: 1 });
  const r = await f2.mapsDownload();
  mapsDl = false;
  hideProgress();
  if (r.ok) drawMaps(r.state);
  else drawDownloadButtons();
  if (!r.ok) {
    if (/cancel/i.test(r.error || ''))
      return void ($('mp-msg').textContent = T('Download cancelled.'));
    if (/not available yet/i.test(r.error || ''))
      return toast(T('Server maps are not available yet.'), true, T('MAPS'));
    return denied(T('Download failed'), r.error);
  }
  $('mp-msg').textContent = r.downloaded
    ? T('Part I maps downloaded.')
    : T('Part I maps are up to date.');
  toast(r.downloaded ? T('Part I maps downloaded.') : T('Part I maps are up to date.'), true);
}
/**
 * Convert the player's own Part I install into the Part I maps (p1conv; the shared progress bar shows it).
 * @returns {Promise<void>}
 */
async function convertP1() {
  if (mapsDl || busy) return;
  mapsDl = true;
  drawDownloadButtons();
  $('mp-msg').textContent = '';
  showProgress({ phase: 'check', done: 0, total: 1 });
  const r = await f2.mapsConvert();
  mapsDl = false;
  hideProgress();
  if (r.ok) drawMaps(r.state);
  else drawDownloadButtons();
  if (!r.ok) {
    if (/cancel/i.test(r.error || ''))
      return void ($('mp-msg').textContent = T('Download cancelled.'));
    return denied(T('Conversion failed'), r.error);
  }
  toast(T('Part I maps installed.'), true);
}
/**
 * Reload the state from main and redraw.
 * @returns {Promise<void>}
 */
async function loadMaps() {
  const r = await f2.mapsState();
  if (r && r.ok) drawMaps(r.state);
}
/**
 * Wire the MAPS tab.
 * @returns {void}
 */
function bindMaps() {
  const pickP1 = async () => {
    const r = await f2.mapsPickP1();
    if (!r.ok) return denied(T('Not a Part I install'), r.error);
    if (!r.picked) return;
    drawMaps(r.state);
    toast(T('The Last of Us Part I found.'), true);
  };
  $('mp-set').onclick = pickP1;
  $('mp-change').onclick = pickP1;
  $('mp-clear').onclick = async () => {
    const r = await f2.mapsClearP1();
    if (r.ok) drawMaps(r.state);
  };
  $('mp-get').onclick = downloadP1;
  $('mp-get2').onclick = downloadP1;
  $('mp-conv').onclick = convertP1;
  $('mp-cancel').onclick = () => f2.cancel();
  f2.onBusy(drawDownloadButtons);
  $('mp-import').onclick = async () => {
    const r = await f2.mapsImport();
    if (!r.ok) return denied(T('Import failed'), r.error);
    if (!r.picked) return;
    drawMaps(r.state);
    $('mp-msg').textContent = T('{n} files imported.', { n: r.copied.length });
  };
  document.querySelector('[data-sub=maps]').addEventListener('click', loadMaps);
  loadMaps();
}
