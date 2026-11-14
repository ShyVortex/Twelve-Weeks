/**
 * @file GEAR UP view: HTML builders for the list/edit pages, preview and details.
 *
 * Loaded after loadout-model.js and before loadout.js (classic scripts, src/index.html order).
 * Exposes the global `LoadoutView`; every function is pure (returns HTML strings / small data
 * objects) and never reads or writes controller state directly.
 */
'use strict';

const LoadoutView = (() => {
  const M = LoadoutModel;
  const esc = (s) =>
    String(s).replace(
      /[&<>"]/g,
      (m) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[m],
    );
  const icon = (n) => `<img src="../assets/icons/${n || 'none'}.png" alt="">`;
  // 'synced' | 'pending' | 'waiting' | 'nogame' | 'error' (main.js loadout:sync / loadout:save)
  const SYNC = {
    synced: ['Synced with game', ''],
    pending: ['Will apply when the game loadout menu closes', 'pending'],
    waiting: ['Start the game once to sync', 'pending'],
    error: ['Could not write the game file', 'bad'],
  };
  const syncHtml = (syncState) => {
    const s = SYNC[syncState];
    return `<span class="lo-sync ${s ? s[1] : ''}" id="lo-sync">${s ? esc(T(s[0])) : ''}</span>`;
  };

  // ---------------------------------------------------------------- list page
  function preview(lo, h) {
    const w = (slot, sel, none) =>
      sel
        ? `<div class="pv"><span class="pvi">${icon(M.wicon(slot, sel))}</span><b>${esc(M.wname(slot, sel))}</b></div>`
        : `<div class="pv dim"><span class="pvi">${icon()}</span><b>${none}</b></div>`;
    const sk = lo.skills
      .filter(Boolean)
      .map(
        (s) =>
          `<div class="pv"><span class="pvi">${icon('skill-' + M.skill(s).icon)}</span><b>${esc(M.skill(s).name)} ${M.ROMAN[s.lv]}</b></div>`,
      )
      .join('');
    const c = h.kind === 'class' ? M.G.classes[h.i] : null;
    return `<h3>${esc(M.label(h))}</h3>${c ? `<p class="cdesc">${esc(c.desc)}</p>` : ''}${w('small', lo.small, 'No Small Firearm')}${w('large', lo.large, 'No Large Firearm')}<hr>${w('purch', lo.purch, 'No Purchasable')}<hr>${sk || `<div class="pv dim"><span class="pvi">${icon()}</span><b>Nothing</b></div>`}
      <div class="lp">${M.total(lo)}/${M.LP_MAX} LP</div>`;
  }
  function listHtml({ st, hi, syncState }) {
    const rowHtml = (h, lo) =>
      `<button class="lrow ${hi.kind === h.kind && hi.i === h.i ? 'sel' : ''} ${M.isActive(st, h) ? 'act' : ''}" data-kind="${h.kind}" data-i="${h.i}" data-snd="click"><span class="li">${icon(lo.large ? M.wicon('large', lo.large) : lo.small ? M.wicon('small', lo.small) : lo.purch ? M.wicon('purch', lo.purch) : null)}</span><b>${esc(M.label(h))}</b>${M.isActive(st, h) ? '<em>EQUIPPED</em>' : `<em>${M.total(lo)} LP</em>`}</button>`;
    const customs = st.custom.map((lo, i) => rowHtml({ kind: 'custom', i }, lo)).join('');
    const classes = M.G.classes
      .map((c, i) => rowHtml({ kind: 'class', i }, M.fromClass(c)))
      .join('');
    const lo = M.current(st, hi);
    const html = `<div class="lo-head"><h2>GEAR UP</h2><span class="lo-sub">MULTIPLAYER</span>${syncHtml(syncState)}</div>
      <div class="lo-cols"><div class="lo-listcol">${customs}<div class="lo-sep">CLASSES</div>${classes}</div>
      <div class="lo-prev">${preview(lo, hi)}</div></div>
      <div class="lo-foot"><button class="btn" id="lo-select" data-snd="confirm">${M.isActive(st, hi) ? 'EQUIPPED' : 'SELECT'}</button>${hi.kind === 'custom' ? '<button class="btn" id="lo-edit" data-snd="click">EDIT</button>' : ''}
      <span class="note-s">${hi.kind === 'class' ? 'Pre-made classes are view only.' : ''}</span></div>`;
    return { html, selectDisabled: M.isActive(st, hi) };
  }

  // ---------------------------------------------------------------- edit page
  function editHtml({ st, hi, row, hiItem, syncState }) {
    const lo = st.custom[hi.i],
      r = M.ROWS[row],
      used = M.total(lo),
      opts = M.options(lo, r);
    const left = M.ROWS.map((x, i) => {
      const inf = M.rowInfo(lo, x);
      return `<button class="erow ${i === row ? 'sel' : ''}" data-row="${i}" data-snd="click"><span class="li">${icon(inf.ic)}</span><b class="${inf.empty ? 'dim' : ''}">${esc(inf.name)}</b><em>${inf.cost}</em></button>${i === 1 ? '<div class="lo-line"></div>' : ''}`;
    }).join('');
    const base = used - M.rowInfo(lo, r).cost;
    const mid = opts
      .map((o) => {
        if (o.skill) {
          const lv = o.skill.cost
            .map((c, k) => {
              const ok = base + c <= M.LP_MAX;
              return `<span class="lv ${o.cur && lo.skills[+r.k[5]].lv === k + 1 ? 'on' : ''} ${ok ? '' : 'no'}" data-skill="${o.id}" data-lv="${k + 1}">${M.ROMAN[k + 1]}<small>${c}</small></span>`;
            })
            .join('');
          return `<div class="orow ${o.cur ? 'cur' : ''} ${hiItem === o.key ? 'hi' : ''}" data-key="${o.key}" tabindex="0" role="button"><span class="li">${icon(o.ic)}</span><b>${esc(o.name)}</b><span class="lvs">${lv}</span></div>`;
        }
        if (o.w) {
          const w = o.w;
          const pills = w.supIcon
            ? `<span class="lvs">${[0, 1]
                .map((q) => {
                  const c = w.lp + (q ? w.supp : 0),
                    ok = base + c <= M.LP_MAX;
                  return `<span class="lv ${o.cur && o.q === q ? 'on' : ''} ${ok ? '' : 'no'}" data-w="${w.id}" data-q="${q}">${q ? 'QUIET' : 'LOUD'}<small>${c ? c : 'FREE'}</small></span>`;
                })
                .join('')}</span>`
            : `<em>${w.lp ? w.lp : 'FREE'}</em>`;
          return `<div class="orow wrow ${o.cur ? 'cur' : ''} ${o.ok ? '' : 'no'} ${hiItem === o.key ? 'hi' : ''}" data-key="${o.key}" tabindex="0" role="button"><span class="li">${icon(o.ic)}</span><b>${esc(w.name)}</b>${pills}</div>`;
        }
        return `<button class="orow ${o.cur || (o.key === 'none' && M.rowInfo(lo, r).empty) ? 'cur' : ''} ${hiItem === o.key ? 'hi' : ''}" data-key="${o.key}"><span class="li">${icon(null)}</span><b>${esc(o.name)}</b><em></em></button>`;
      })
      .join('');
    return `<div class="lo-head"><h2>CUSTOM LOADOUT ${hi.i + 1}</h2><span class="lo-lp ${used > M.LP_MAX ? 'bad' : ''}">${used}/${M.LP_MAX} Loadout Points</span>${syncHtml(syncState)}</div>
      <div class="lo-cols edit"><div class="lo-listcol">${left}</div><div class="lo-pick"><h4>${r.t}</h4>${mid}</div><div class="lo-det">${details(lo, r, opts, hiItem)}</div></div>
      <div class="lo-foot"><button class="btn" id="lo-back" data-snd="back">BACK</button><button class="btn" id="lo-reset" data-snd="click">RESET LOADOUT</button></div>`;
  }
  function details(lo, r, opts, hiItem) {
    const o = opts.find((x) => x.key === hiItem) || opts.find((x) => x.cur);
    if (!o || o.key === 'none')
      return `<h3>${esc((r.none || 'Nothing').toUpperCase())}</h3><div class="dicon">${icon(null)}</div><p class="cdesc">Nothing equipped in this slot.</p>`;
    if (o.skill) {
      const s = o.skill,
        cur = lo.skills[+r.k[5]];
      const lines = s.desc
        .map(
          (d, k) =>
            `<p class="cdesc ${cur && cur.id === o.id && cur.lv === k + 1 ? 'curlv' : ''}"><b>${M.ROMAN[k + 1]}</b> ${esc(d)} <i>${s.cost[k] ? s.cost[k] + ' LP' : 'FREE'}</i></p>`,
        )
        .join('');
      return `<h3>${esc(s.name)}</h3><div class="dicon">${icon('skill-' + s.icon)}</div>${lines}`;
    }
    const w = o.w,
      quiet = o.cur && o.q;
    const st = w.stats
      ? ['RATE OF FIRE:', 'RELOAD SPEED:', 'DAMAGE:', 'ACCURACY:']
          .map(
            (n, k) =>
              `<div class="stat"><label>${n}</label><div class="segs">${Array.from({ length: 10 }, (_, s) => `<i class="${s < w.stats[k] ? 'f' : ''}"></i>`).join('')}</div></div>`,
          )
          .join('')
      : '';
    const eff = w.supIcon
      ? `<p class="cdesc eff"><b>${quiet ? 'QUIET' : 'LOUD'}</b> ${quiet ? `Suppressed: fewer enemies hear the shots, and firing does not show you on the enemy radar. +${w.supp} LP.` : `Standard. QUIET adds a suppressor for +${w.supp} LP.`}</p>`
      : '';
    return `<h3>${esc((quiet ? 'SUPPRESSED ' : '') + w.name)}</h3><div class="dcost">${o.cost ? o.cost + ' LP' : 'FREE'}</div><div class="dicon wide">${icon(o.ic)}</div><p class="cdesc">${esc(w.desc)}</p>${eff}${st}${o.ok ? '' : '<p class="cdesc bad">NOT ENOUGH POINTS<br>Spend your loadout points elsewhere.</p>'}`;
  }

  return { esc, icon, SYNC, syncHtml, preview, listHtml, editHtml, details };
})();
