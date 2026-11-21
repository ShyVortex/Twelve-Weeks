/**
 * @file Renderer bug-report form, attachment list and send flow.
 */
'use strict';

// ---------------------------------------------------------------- report a bug
/**
 * Renderer bug-report form, attachments and send-flow controller.
 */
const Report = (() => {
  const MAPS = [
    'Capitol Hill',
    'Gas Station',
    'Train Station',
    'Shipyard',
    'School',
    'Hospital',
    'Forest',
    'Seraphite Camp',
    'Houses',
    'Overpass',
    'Resort',
    'Tilted / other',
    'Menu / lobby',
  ];
  const fillMaps = () => {
    const sel = $('rp-map');
    if (!sel) return;
    const cur = sel.value; // (the map field is gone - the logs say the map)
    sel.innerHTML =
      '<option value="">-</option>' +
      MAPS.map((m) => `<option value="${m}">${T(m)}</option>`).join('');
    sel.value = cur;
  };
  let inited = false,
    busyR = false;
  const size = (n) =>
    n >= 1048576 ? (n / 1048576).toFixed(1) + ' MB' : Math.max(1, Math.round(n / 1024)) + ' KB'; // (units stay)
  const date = (t) => (t ? new Date(t).toISOString().slice(0, 16).replace('T', ' ') : '');
  async function files() {
    const r = await f2.reportFiles($('rp-dumps').checked);
    const rows = (r.ok ? r.files : []).map((f) =>
      f.kind === 'missing'
        ? `<div class="rowbar st warn"><b>${esc(f.name)}</b><span>${esc(T(f.note))}</span></div>`
        : `<div class="rowbar st"><b>${esc(f.name)}</b><span>${size(f.size)}${f.mtime ? ' &middot; ' + date(f.mtime) : ''}${f.note ? ' &middot; ' + esc(T(f.note)) : ''}</span></div>`,
    );
    rows.push(
      `<div class="rowbar st"><b>system.txt</b><span>${esc(T('OS, CPU, GPU, versions, player name, Steam id'))}</span></div>`,
    );
    $('rp-files').innerHTML = rows.join('');
    L10N.tree($('rp-files'));
  }
  let busyA = false;
  const showAtt = (r) => {
    if (!r || !r.ok) {
      if (r && r.error) toast(r.error);
      return;
    }
    $('rp-att').innerHTML = r.items
      .map(
        (x) =>
          `<div class="att-item ${x.kind}" data-id="${esc(x.id)}">` +
          (x.kind === 'image'
            ? x.thumb
              ? `<img src="${x.thumb}" alt="">`
              : '<div class="att-ph">IMG</div>'
            : '<div class="att-ph">VIDEO</div>') +
          `<span class="att-n">${esc(x.name)}</span><span class="att-s">${size(x.size)}</span><button class="att-x" data-rm="${esc(x.id)}" title="${esc(T('Remove'))}" aria-label="${esc(T('Remove'))}">&times;</button></div>`,
      )
      .join('');
    for (const j of r.rejected || []) toast(`${j.name}: ${j.reason}`);
  };
  const guard = async (fn) => {
    if (busyA || busyR) return;
    busyA = true;
    try {
      showAtt(await fn());
    } finally {
      busyA = false;
    }
  };
  const fileOf = (e) =>
    [...((e.clipboardData && e.clipboardData.items) || [])]
      .filter((i) => i.kind === 'file' && /^image\//.test(i.type))
      .map((i) => i.getAsFile())
      .filter(Boolean);
  async function open() {
    if (!inited) {
      inited = true;
      f2.attList().then(showAtt);
      $('rp-attach').onclick = () => guard(() => f2.attPick());
      $('rp-att').onclick = (e) => {
        const b = e.target.closest('[data-rm]');
        if (b) guard(() => f2.attRemove(b.dataset.rm));
      };
      f2.onDropFiles((paths) => {
        if (curView === 'report') guard(() => f2.attAdd(paths));
      });
      const drop = $('v-report');
      drop.addEventListener('dragover', (e) => {
        e.preventDefault();
        drop.classList.add('dragging');
      });
      drop.addEventListener('dragleave', (e) => {
        if (e.target === drop) drop.classList.remove('dragging');
      });
      drop.addEventListener('drop', () => drop.classList.remove('dragging'), true);
      document.addEventListener('paste', async (e) => {
        if (curView !== 'report') return;
        const fl = fileOf(e);
        if (!fl.length) return; // plain text pastes go to the text box as usual
        e.preventDefault();
        for (const f of fl) {
          const buf = new Uint8Array(await f.arrayBuffer());
          await guard(() => f2.attPaste(Array.from(buf)));
        }
      });
      fillMaps();
      Report.fillMaps = fillMaps;
      for (const b of document.querySelectorAll('#rp-modes [data-rmode]'))
        b.onclick = () => mode(b.dataset.rmode);
      bindPlayer();
      $('rp-dumps').onchange = files;
      f2.onReportProgress((p) => {
        if (p.phase === 'collect') $('rp-state').textContent = T('Collecting files...');
        else if (p.phase === 'clip') {
          $('rp-bar').hidden = false;
          $('rp-fill').style.width = p.pct + '%';
          $('rp-state').textContent = T('Sending clip {n} of {of}... {pct}%', {
            n: p.n,
            of: p.of,
            pct: p.pct,
          });
        } else {
          $('rp-bar').hidden = false;
          $('rp-fill').style.width = p.pct + '%';
          $('rp-state').textContent = T('Sending {size}... {pct}%', {
            size: size(p.size || 0),
            pct: p.pct,
          });
        }
      });
      $('rp-send').onclick = async () => {
        if (busyR) return;
        const text = $('rp-text').value.trim();
        if (text.length < 10) {
          toast('Please describe what happened first.');
          $('rp-text').focus();
          return;
        }
        busyR = true;
        $('rp-send').disabled = true;
        $('rp-code').hidden = true;
        $('rp-state').textContent = T('Collecting files...');
        const r = await f2.sendReport({
          text,
          when: $('rp-when').value,
          whenText: $('rp-whent').value,
          mapMode: '',
          includeDumps: $('rp-dumps').checked,
        });
        busyR = false;
        $('rp-send').disabled = false;
        $('rp-bar').hidden = true;
        if (!r.ok) {
          $('rp-state').textContent = '';
          toast(r.error);
          return;
        }
        $('rp-state').textContent = T('Sent {size}. Your unique bug report code is {code}', { size: size(r.size), code: r.uniqueCode });
        $('rp-codev').textContent = r.code;
        $('rp-code').hidden = false;
        $('rp-text').value = '';
        toast('Report sent. Thank you!', true);
        f2.attList().then(showAtt);
        if (r.clipNotes && r.clipNotes.length)
          toast(
            T('The report is in, but a clip did not go through:') + ' ' + r.clipNotes.join(' '),
          );
      };
    }
    files();
    if (pmode) loadPlayers();
  }
  // ---- PLAYER REPORT: the players of my last 3 matches (from the game server), a reason and a text; the server opens a case + asks the match's clients for their demo
  let pmode = false,
    pPick = null,
    busyP = false;
  const ago = (s) =>
    s < 90
      ? T('just now')
      : s < 5400
        ? T('{n} min ago', { n: Math.round(s / 60) })
        : s < 129600
          ? T('{n} h ago', { n: Math.round(s / 3600) })
          : T('{n} d ago', { n: Math.round(s / 86400) });
  /**
   * Switch between the bug report and the player report form.
   * @param {string} m 'bug' or 'player'
   * @returns {void}
   */
  function mode(m) {
    pmode = m === 'player';
    for (const b of document.querySelectorAll('#rp-modes [data-rmode]'))
      b.classList.toggle('active', b.dataset.rmode === m);
    $('rep-body').hidden = pmode;
    $('rep-player').hidden = !pmode;
    if (pmode) loadPlayers();
  }
  /**
   * Load the players of the last matches into the picker.
   * @returns {Promise<void>}
   */
  async function loadPlayers() {
    pPick = null;
    $('pr-list').innerHTML = '';
    $('pr-none').hidden = true;
    $('pr-code').hidden = true;
    const r = await f2.reportPlayers();
    $('pr-state').textContent = '';
    if (!r.ok) {
      toast(r.error);
      $('pr-none').hidden = false;
      return;
    }
    $('pr-none').hidden = r.matches.some((m) => m.players.length);
    $('pr-list').innerHTML = r.matches
      .filter((m) => m.players.length)
      .map(
        (m, i) =>
          `<div class="pr-h">${esc(T('MATCH {n}', { n: i + 1 }))} &middot; ${esc(ago(m.age))}</div>` +
          m.players
            .map(
              (p) =>
                `<button class="pr-row" data-mid="${esc(m.mid)}" data-slot="${p.slot}"><b>${esc(p.name)}</b><span>${p.steamid && p.steamid !== '0' ? esc(p.steamid) : ''}</span></button>`,
            )
            .join(''),
      )
      .join('');
  }
  /**
   * Bind the player-report picker and send button.
   * @returns {void}
   */
  function bindPlayer() {
    $('pr-list').onclick = (e) => {
      const b = e.target.closest('.pr-row');
      if (!b) return;
      for (const x of document.querySelectorAll('#pr-list .pr-row'))
        x.classList.toggle('sel', x === b);
      pPick = { mid: b.dataset.mid, slot: +b.dataset.slot };
    };
    $('pr-send').onclick = async () => {
      if (busyP) return;
      if (!pPick) {
        toast('Pick the player you want to report first.');
        return;
      }
      let reasons = 0;
      for (const c of document.querySelectorAll('#rep-player [data-reason]'))
        if (c.checked) reasons |= +c.dataset.reason;
      if (!reasons) {
        toast('Pick at least one reason.');
        return;
      }
      busyP = true;
      $('pr-send').disabled = true;
      $('pr-state').textContent = T('Sending...');
      const r = await f2.reportPlayer({ ...pPick, reasons, text: $('pr-text').value.trim() });
      busyP = false;
      $('pr-send').disabled = false;
      $('pr-state').textContent = '';
      if (!r.ok) {
        toast(r.error);
        return;
      }
      $('pr-codev').textContent = r.code;
      $('pr-code').hidden = false;
      $('pr-text').value = '';
      for (const c of document.querySelectorAll('#rep-player [data-reason]')) c.checked = false;
      toast('Report sent. Thank you!', true);
    };
  }
  return { open };
})();
