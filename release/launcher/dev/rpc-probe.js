// Dev probe: send one in-game card to the local Discord client and print what Discord stored (asset keys come back as
// mp:external/... when Discord accepted an https image). node dev/rpc-probe.js [state-file] [hold-seconds]
'use strict';
const fs = require('fs');
const { Client } = require('@xhayper/discord-rpc');
const ingame = require('../lib/rpc/ingame');
const I18N = require('../src/i18n-core');

(async () => {
  const txt = process.argv[2]
    ? fs.readFileSync(process.argv[2], 'utf8')
    : 'v=1\nst=match\nmap=p1-bookstore\nmapn=Bookstore (Part I)\nmode=sr\nmoden=Supply Raid\nlv=9\nelv=6\ndn=4\nx=1\nnp=8\nnpmax=8\nclan=WLF\nwk=3\nday=4\nsv=14\n';
  const a = ingame.build(ingame.parse(txt), I18N.T);
  const c = new Client({ clientId: '1569450156942819470' });
  await c.login();
  const r = await c.user.setActivity({
    name: 'Twelve Weeks - Launcher',
    type: 0,
    details: a.details,
    state: a.state,
    startTimestamp: (a.timestamps && a.timestamps.start) || Math.floor(Date.now() / 1000),
    partySize: a.partySize,
    partyMax: a.partyMax,
    largeImageKey: process.env.RPC_LARGE || a.assets.largeImage,
    largeImageText: a.assets.largeText,
    smallImageKey: a.assets.smallImage,
    smallImageText: a.assets.smallText,
    buttons: a.buttons,
  });
  console.log(JSON.stringify(r, null, 1));
  await new Promise((res) => setTimeout(res, (parseInt(process.argv[3], 10) || 3) * 1000));
  await c.user.clearActivity();
  await c.destroy();
})().catch((e) => {
  console.error('probe failed:', e.message);
  process.exit(1);
});
