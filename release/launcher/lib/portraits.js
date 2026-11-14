'use strict';
// Portrait cast for the launcher's expanded clan roster UI. The 18 rendered members (85 proposed)
// are stored in assets/portraits/<model>_<expr>.png. Expression states: neutral, happy, sad, hungry, sick, shock, dead, perk, depressed.
// This module maps (faction, gender, member index) -> portrait filename, with status-based expression selection.

const CAST = [
  // WLF cast (faction 1) - mix of military and stadium personnel
  { model: 'militia-male-05', g: 'm' }, // 0: adult male
  { model: 'stadium-male-06', g: 'm' }, // 1: adult male
  { model: 'militia-female-02', g: 'f' }, // 2: adult female
  { model: 'stadium-kid-05', g: 'f' }, // 3: child female
  { model: 'militia-male-03', g: 'm' }, // 4: adult male
  { model: 'stadium-kid-07', g: 'm' }, // 5: child male
  { model: 'stadium-gym-male-03', g: 'm' }, // 6: adult male
  { model: 'stadium-gym-female-07', g: 'f' }, // 7: adult female
  { model: 'militia-female-14', g: 'f' }, // 8: adult female
  { model: 'stadium-male-01', g: 'm' }, // 9: adult male
  { model: 'stadium-male-09', g: 'm' }, // 10: adult male
  { model: 'stadium-gym-female-04', g: 'f' }, // 11: adult female
  { model: 'stadium-kitchen-male-02', g: 'm' }, // 12: adult male
  { model: 'stadium-kitchen-female-02', g: 'f' }, // 13: adult female
  { model: 'militia-doctor-female-01', g: 'f' }, // 14: adult female
  { model: 'militia-female-05', g: 'f' }, // 15: adult female
  { model: 'stadium-teen-female-01', g: 'f' }, // 16: teen female
];

// Expression based on member status and mood
const EXPR_MAP = {
  healthy: {
    default: 'neutral',
    happy: 'happy',
    sad: 'sad',
    hopeful: 'happy',
    cheerful: 'happy',
    calm: 'neutral',
    worried: 'sad',
    afraid: 'shock',
    desperate: 'depressed',
    grieving: 'sad',
    grim: 'sad',
    despair: 'depressed',
  },
  hungry: { default: 'hungry', worried: 'hungry', desperate: 'hungry', grim: 'hungry' },
  sick: { default: 'sick', desperate: 'sick', grieving: 'sick' },
};

function hash(str) {
  let h = 0;
  for (let i = 0; i < str.length; i++) h = ((h << 5) - h + str.charCodeAt(i)) | 0;
  return Math.abs(h);
}

function portraitFor(name, gender, state, mood) {
  // Pick a consistent portrait for this member based on name hash
  const h = hash(name || 'Unknown');
  const gMatches = CAST.filter((c) => c.g === gender);
  const pool = gMatches.length ? gMatches : CAST;
  const cast = pool[h % pool.length];

  // Pick expression based on state and mood
  const stateMap = EXPR_MAP[state] || EXPR_MAP.healthy;
  const expr = stateMap[mood] || stateMap.default || 'neutral';

  return `${cast.model}_${expr}.png`;
}

function portraitUrl(name, gender, state, mood) {
  const file = portraitFor(name, gender, state, mood);
  // In Electron, resolve to the assets path
  return `assets/portraits/${file}`;
}

module.exports = { portraitFor, portraitUrl, CAST };
