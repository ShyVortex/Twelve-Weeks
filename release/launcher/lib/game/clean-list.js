/**
 * @file Clean game install reference for the Play-time file check (game build 1.6.10721).
 *
 * ARCHIVES: every .psarc the mod's winmm.dll accepts in build/pc/main, keyed by the FNV-1a 64 hash of the lowercase path
 * relative to build/pc/main (the same key and sizes as the winmm manifest). Any other .psarc there, or a listed one of
 * another size, makes winmm treat the install as modified; the server then refuses every search.
 * ROOT_DLLS: the .dll files a clean Steam install has next to tlou-ii.exe.
 */
'use strict';

const ARCHIVES = new Map([
  ['90ad66a5fb67b1a7', 77695732], // bin.psarc
  ['cf260d4a9a7b01e5', 4987403574], // common.psarc
  ['2aca1b3ceb21d307', 2786519027], // core.psarc
  ['dc61ba4c01349694', 6721710], // shaders.psarc
  ['75c22206a2e51f01', 21342874463], // sp-common.psarc
  ['d606690c51ca111e', 2460595312], // speech1/brazilian.psarc
  ['d408e897fe413af8', 3790312704], // speech1/english.psarc
  ['a4bd06fdf9956ea2', 2367411232], // speech1/french.psarc
  ['c14d11f63f4040ec', 2413266876], // speech1/german.psarc
  ['3dc5b05a3e22a6d8', 2484971912], // speech1/greek.psarc
  ['932c2eb40ca19eb8', 2517885416], // speech1/italian.psarc
  ['0ce42c6b162b37bf', 2460731308], // speech1/polish.psarc
  ['48d214eaaae9ebf7', 2490865480], // speech1/portuguese.psarc
  ['a65fa2138f1175cd', 2430411768], // speech1/russian.psarc
  ['c76788a4b48dfcea', 2522244616], // speech1/sam-spanish.psarc
  ['8a892b5b69ed89a8', 2487551336], // speech1/spanish.psarc
  ['c9e9a878ee549300', 2435754924], // speech1/turkish.psarc
  ['7d25c15391fde4a6', 475], // steam.psarc
  ['c15c6a3c42ba491e', 65833726], // tts1/brazilian-gameplay.psarc
  ['a34b7ded669f3171', 181889427], // tts1/brazilian-menu.psarc
  ['e00d90c46c816525', 57154649], // tts1/chinese-gameplay.psarc
  ['669a9ca3f123935a', 161528677], // tts1/chinese-menu.psarc
  ['1cae51f9ab97696f', 33718929], // tts1/croatian-gameplay.psarc
  ['22373ad020ceedbc', 166847028], // tts1/croatian-menu.psarc
  ['49fa8639ed069031', 57360965], // tts1/czech-gameplay.psarc
  ['f8a126f19040bee6', 166267359], // tts1/czech-menu.psarc
  ['3c30174884e950c7', 61984440], // tts1/danish-gameplay.psarc
  ['fb6933ef87f3d8a4', 169451007], // tts1/danish-menu.psarc
  ['f5bd4e0366639c76', 54646020], // tts1/dutch-gameplay.psarc
  ['ceb7a2893804f759', 157311717], // tts1/dutch-menu.psarc
  ['02d5925171d3f4d8', 49482916], // tts1/english-gameplay.psarc
  ['fa6dbb95646f5af3', 145838046], // tts1/english-menu.psarc
  ['b77f80edceac0eb1', 63984580], // tts1/finnish-gameplay.psarc
  ['7555b5e6e4079566', 180118202], // tts1/finnish-menu.psarc
  ['1ca2878fe5ee8468', 51287190], // tts1/french-gameplay.psarc
  ['93f881e5578efb23', 146736018], // tts1/french-menu.psarc
  ['a4250fd90548fb5e', 62652617], // tts1/german-gameplay.psarc
  ['a638bbb123feefb1', 184034166], // tts1/german-menu.psarc
  ['7a0b0c3fc3c89704', 59994719], // tts1/greek-gameplay.psarc
  ['d89378722a98801f', 177119459], // tts1/greek-menu.psarc
  ['ac46ef04f5276c73', 35443723], // tts1/hungarian-gameplay.psarc
  ['1818bd717f833c30', 173063292], // tts1/hungarian-menu.psarc
  ['7455613be1ad1810', 66143962], // tts1/italian-gameplay.psarc
  ['a211aee42c7174db', 187359328], // tts1/italian-menu.psarc
  ['b7d2ff785738a69c', 59676646], // tts1/korean-gameplay.psarc
  ['21deeb2a6681c687', 159051460], // tts1/korean-menu.psarc
  ['e61e4f4db509ff44', 54302900], // tts1/norwegian-gameplay.psarc
  ['0f0c80848d42125f', 149960414], // tts1/norwegian-menu.psarc
  ['67031e328994def7', 65937268], // tts1/polish-gameplay.psarc
  ['c4de124c2d1fb4b4', 179956071], // tts1/polish-menu.psarc
  ['1ac3f0a004ffa193', 62092830], // tts1/portuguese-gameplay.psarc
  ['dc69be75e6d8ddd0', 180648050], // tts1/portuguese-menu.psarc
  ['82801f569fb2c30b', 58605953], // tts1/russian-gameplay.psarc
  ['3a7b302953f48a98', 170786880], // tts1/russian-menu.psarc
  ['281f5cf18b6e597a', 60762541], // tts1/sam-spanish-gameplay.psarc
  ['0dd46c2cb2377cbd', 176759335], // tts1/sam-spanish-menu.psarc
  ['863ad187bf158ae3', 58964880], // tts1/simpl-chinese-gameplay.psarc
  ['1385375e4d09ef80', 163353126], // tts1/simpl-chinese-menu.psarc
  ['adb9c84b41238920', 56130711], // tts1/spanish-gameplay.psarc
  ['33f307ec8731940b', 162123262], // tts1/spanish-menu.psarc
  ['fdfc178be0d8b95f', 58190610], // tts1/swedish-gameplay.psarc
  ['90c4212259ba43cc', 163519357], // tts1/swedish-menu.psarc
  ['e649d2a95f0151b8', 61684552], // tts1/turkish-gameplay.psarc
  ['7ab43cbb79fc1053', 171637317], // tts1/turkish-menu.psarc
  ['c33d949573f0f120', 56161658], // tts1/ukenglish-gameplay.psarc
  ['8dc509f4a57c7c0b', 151495614], // tts1/ukenglish-menu.psarc
  ['8b463c3c3e357862', 861369113], // world-abby-ellie-fight.psarc
  ['335c0087844ff571', 1264558646], // world-abby-fights-militia.psarc
  ['2dc2c92f7e27df4d', 971464017], // world-abby-flashback-dad.psarc
  ['21475fec0aa0602f', 887093775], // world-amputation.psarc
  ['665891632abb2687', 677112769], // world-cutting-room.psarc
  ['223cd66ac948615b', 1150039690], // world-ellie-flashback-museum.psarc
  ['cce4a51798680919', 934955031], // world-ellie-flashback-patrol.psarc
  ['7177fc68d872fe15', 1005666313], // world-ellie-flashback-ultimatum.psarc
  ['73ea41d4bfc6b427', 491], // world-epilogue.psarc
  ['52047a82497ba6e7', 1517635308], // world-farm.psarc
  ['9787683eb90e4532', 778865036], // world-find-aquarium.psarc
  ['bf0b1f5cf66bf8b3', 2668215967], // world-find-nora.psarc
  ['5475a8f5214f92ed', 3890735720], // world-flashback-guitar.psarc
  ['7f878262f29e6734', 2326105176], // world-flooded-city.psarc
  ['55db6f5aba86c7c6', 5082077906], // world-forward-base.psarc
  ['485ca126051cee10', 18878906], // world-game-start.psarc
  ['7e841caefbc02b02', 218455783], // world-guitar-freeplay.psarc
  ['eb5945c852aa6a11', 1088886481], // world-jordan-escape.psarc
  ['e8aac8ff953cf58b', 2359945602], // world-medicine.psarc
  ['394237ac17203ee1', 387101591], // world-patrol-chalet.psarc
  ['4490d237146387d8', 1201834406], // world-patrol-departure.psarc
  ['636367133e3d1b1d', 1473416689], // world-patrol-jackson.psarc
  ['8ed764eed0308a99', 1201311405], // world-patrol.psarc
  ['a5a77b0d45c9886d', 2350780925], // world-rescue-jesse.psarc
  ['8818cf008e91e825', 4823389117], // world-rogue.psarc
  ['e3fa126de3d4300e', 1496886163], // world-santa-barbara.psarc
  ['1db24960050f6468', 2233116757], // world-save-lev.psarc
  ['00b635fc7c64eff7', 2877489848], // world-saving-kids.psarc
  ['5bac2be1dc4fb31f', 2367205516], // world-seattle-arrival.psarc
  ['345af553b24152d7', 447820109], // world-theater-ambush.psarc
  ['aec17b4c138cac16', 1093724587], // world-theater.psarc
  ['3d236ad4148452fd', 710281831], // world-tracking-horde.psarc
  ['b5f92e69f83f7b02', 1316519915], // world-tracking.psarc
  ['b593840320a3fa5f', 1571413510], // world-watchtower.psarc
  ['3cba53dbeb6bcd96', 94295010], // (name unknown)
]);

const ROOT_DLLS = [
  'cchromaeditorlibrary.dll',
  'cchromaeditorlibrary64.dll',
  'cuesdk.x64_2017.dll',
  'gfsdk_aftermath_lib.x64.dll',
  'microsoft.windowsappruntime.bootstrap.dll',
  'playstationsdk.dll',
  'webview2loader.dll',
  'amd_ags_x64.dll',
  'amd_fidelityfx_dx12.dll',
  'bink2w64.dll',
  'crs-client.dll',
  'dstorage.dll',
  'dstoragecore.dll',
  'dxcompiler.dll',
  'libxess.dll',
  'nvngx_dlss.dll',
  'nvngx_dlssg.dll',
  'sl.common.dll',
  'sl.dlss.dll',
  'sl.dlss_g.dll',
  'sl.interposer.dll',
  'sl.pcl.dll',
  'sl.reflex.dll',
  'steam_api64.dll',
];

module.exports = { ARCHIVES, ROOT_DLLS };
