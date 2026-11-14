'use strict';
// node scripts/stamp-defaults.js <game host:port> <http://update host:port>  : rewrites OFFICIAL_SERVER / OFFICIAL_FILE_HOST in defaults.js (run before npm run dist)
const fs = require('fs'), path = require('path');
const [server, host] = process.argv.slice(2);
if (!/^[^:\s]+:\d+$/.test(server || '') || !/^https?:\/\/[^\s]+$/.test(host || '')) { console.error('usage: stamp-defaults.js <host:port> <http://host:port>'); process.exit(1); }
const f = path.join(__dirname, '..', 'defaults.js');
let s = fs.readFileSync(f, 'utf8');
s = s.replace(/const OFFICIAL_SERVER = '[^']*';/, `const OFFICIAL_SERVER = '${server}';`).replace(/const OFFICIAL_FILE_HOST = '[^']*';/, `const OFFICIAL_FILE_HOST = '${host.replace(/\/+$/, '')}';`);
fs.writeFileSync(f, s);
console.log('stamped', server, host);
