/**
 * @file Background scene sets, rotation and cross-fades.
 */
'use strict';
// Background stills (assets/bg/*.jpg, 1920x1080, graded desaturated): two faction sets (WLF / Seraphites) and a small neutral set used before the
// clan faction is known. They rotate slowly with a cross-fade, or one can be picked (Settings > Display). Sources: README "Where the art and sound come from" (TLOU2's own art-gallery / chapter / encounter stills).
/**
 * Background scene sets, rotation and cross-fade controller.
 */
const Scenes = (() => {
  const SETS = {
    wlf: [
      ['wlf-hq', 'WLF HEADQUARTERS'],
      ['stadium-mess', 'THE MESS HALL'],
      ['stadium-window', 'THE STADIUM'],
      ['stadium-stands', 'THE BLEACHERS'],
      ['stadium-market', 'THE FORWARD BASE'],
      ['wlf-patrol', 'WLF PATROL'],
      ['stadium-concourse', 'THE CONCOURSE'],
      ['wlf-docks', 'THE DOCKS'],
    ],
    sera: [
      ['haven', 'HAVEN'],
      ['haven-village', 'THE VILLAGE'],
      ['haven-hut', 'THE HUTS'],
      ['haven-fields', 'THE CROPS'],
      ['haven-boardwalk', 'THE BOARDWALK'],
      ['island-burns', 'THE ISLAND'],
      ['island-smoke', 'SMOKE ON THE HORIZON'],
      ['island-fire', 'THE BURNING'],
      ['island-boat', 'THE PIERS'],
      ['island-embers', 'EMBERS'],
    ],
    neutral: [
      ['seattle-falls', 'THE FALLS'],
      ['seattle-city', 'SEATTLE'],
      ['seattle-overgrown', 'OVERGROWTH'],
      ['seattle-flooded', 'THE FLOODED STREET'],
      ['seattle-rain', 'RAIN'],
    ],
  };

  const url = (id) => `url('../assets/bg/${id}.jpg')`;
  const listeners = [];
  let set = 'neutral',
    mode = 'rotate',
    pick = null,
    cur = null,
    front = 0,
    timer = 0,
    order = [],
    oi = 0;
  const ids = () => SETS[set].map((x) => x[0]);
  function show(id) {
    if (id === cur) return;
    cur = id;
    const a = document.getElementById('bg-a'),
      b = document.getElementById('bg-b');
    const layers = [a, b],
      nxt = layers[1 - front],
      old = layers[front];
    nxt.style.backgroundImage = url(id);
    nxt.classList.add('on');
    old.classList.remove('on');
    front = 1 - front;
  }
  function reshuffle() {
    order = ids()
      .map((id) => [Math.random(), id])
      .sort((x, y) => x[0] - y[0])
      .map((x) => x[1]);
    oi = 0;
    if (order[0] === cur && order.length > 1) order.push(order.shift());
  }
  function tick() {
    clearTimeout(timer);
    if (mode === 'rotate') {
      if (!document.hidden) {
        if (oi >= order.length) reshuffle();
        show(order[oi++]);
      }
      timer = setTimeout(tick, 40000);
    }
  }
  function apply() {
    const valid = pick && ids().includes(pick) ? pick : null;
    if (mode === 'pick' && valid) {
      clearTimeout(timer);
      show(valid);
    } else {
      reshuffle();
      cur = null;
      tick();
    }
  }
  return {
    SETS,
    url,
    list: () => SETS[set],
    setName: () => set,
    onSet(cb) {
      listeners.push(cb);
    },
    setFaction(f) {
      const n = f === 'wlf' || f === 'sera' ? f : 'neutral';
      if (n === set && cur) return;
      const changed = n !== set;
      set = n;
      if (typeof Mus !== 'undefined') Mus.setTheme(n);
      apply();
      if (changed) listeners.forEach((cb) => cb());
    },
    setMode(m, p) {
      mode = m === 'pick' ? 'pick' : 'rotate';
      pick = p;
      apply();
    },
    current: () => cur,
  };
})();
