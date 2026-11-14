/**
 * @file Hardware, CPU, RAM and GPU discovery for reports and diagnostics.
 */
'use strict';

const os = require('os');

/**
 * Collect CPU, RAM and OS information.
 * @returns {object}
 */
function hardware() {
  const cpus = os.cpus();
  return {
    cpu: cpus.length ? cpus[0].model.trim() : '?',
    cores: cpus.length,
    ram: Math.round(os.totalmem() / 2 ** 30),
    os: `${os.type()} ${os.release()}`,
    arch: os.arch(),
  };
}

/**
 * Detect the primary GPU name.
 * @param {{isLinux?: boolean, run?: Function}} [options]
 * @returns {string}
 */
async function gpuName({ isLinux, run }) {
  if (isLinux) {
    const l = await run('sh', [
      '-c',
      "lspci 2>/dev/null | grep -iE 'vga|3d|display' | cut -d: -f3- | tr '\\n' ';'",
    ]);
    return l.stdout.trim().slice(0, 280);
  }
  const r = await run('powershell.exe', [
    '-NoProfile',
    '-NonInteractive',
    '-Command',
    "(Get-CimInstance Win32_VideoController | ForEach-Object { $_.Name + ' ' + $_.DriverVersion }) -join '; '",
  ]);
  return r.stdout.trim().slice(0, 280);
}

module.exports = { hardware, gpuName };
