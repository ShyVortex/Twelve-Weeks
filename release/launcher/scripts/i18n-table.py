"""The launcher's English -> Polish table. Run: python scripts/i18n-table.py  -> writes src/i18n/pl.json and src/i18n/en.json (identity list of the source strings).
Game wording follows tools/loc/pl (the mod's Polish of TLOU2 / Factions terms: GEAR UP = WYPOSAŻENIE, QUIT = WYJDŹ, SERAPHITES = SERAFICI, BACK = WSTECZ, ...).
Placeholders: {name}; Polish plural  {n|plik|pliki|plików}; {name!} translates the captured text as well."""
import json, os
HERE = os.path.dirname(os.path.abspath(__file__))
PL = {
    # ---- window / menu
    "Twelve Weeks": "Twelve Weeks", "Minimize": "Minimalizuj", "Close": "Zamknij", "THE LAST OF US": "THE LAST OF US",
    "ONLINE": "W SIECI", "PLAY": "GRAJ", "UPDATE": "AKTUALIZUJ", "CLAN": "KLAN", "LOADOUT": "WYPOSAŻENIE", "NEWS": "AKTUALNOŚCI", "REPORT A BUG": "ZGŁOŚ BŁĄD",
    "SETTINGS": "USTAWIENIA", "QUIT": "WYJDŹ",
    # ---- status panel
    "STATUS": "STATUS", "SERVER": "SERWER", "CLIENT": "KLIENT", "PLAYING AS": "GRASZ JAKO", "GAME": "GRA", "LATEST NEWS": "OSTATNIE WIEŚCI",
    "5 SURVIVORS": "OCALALI: 5", "HEALTHY:": "ZDROWI:", "HUNGRY:": "GŁODNI:", "SICK:": "CHORZY:", "NEEDED PER DAY:": "POTRZEBNE DZIENNIE:",
    "LOADING": "WCZYTYWANIE", "Please wait.": "Proszę czekać.", "ENTER": "ENTER", "SELECT": "WYBIERZ", "ESC": "ESC", "BACK": "WSTECZ",
    "BUILD {v}": "WERSJA {v}", "NOT INSTALLED": "NIE ZAINSTALOWANO", "OFFLINE": "BRAK POŁĄCZENIA", "UPDATE AVAILABLE": "DOSTĘPNA AKTUALIZACJA", "UP TO DATE": "AKTUALNE",
    "NOT SET": "NIE USTAWIONO", "FOUND": "ZNALEZIONA", "NOT FOUND": "NIE ZNALEZIONA",
    "update server unreachable": "serwer aktualizacji niedostępny", ", build {v} installed": ", zainstalowana wersja {v}", "{size} to download, build {v}": "do pobrania: {size}, wersja {v}",
    "build {v}": "wersja {v}", "set it in Settings > Game": "ustaw ją w Ustawieniach > Gra", "{size} ({n} files)": "{size} ({n} {n|plik|pliki|plików})", "nothing": "nic",
    "Version {v} is available.": "Dostępna jest wersja {v}.", "Launcher is up to date.": "Launcher jest aktualny.", "{n} players, ": "graczy: {n}, ", "add a server in Settings": "dodaj serwer w Ustawieniach",
    "No update server configured": "Nie skonfigurowano serwera aktualizacji", "no feed source": "brak źródła wieści",
    # ---- play button states
    "STARTING": "URUCHAMIANIE", "PLEASE WAIT": "PROSZĘ CZEKAĆ", "IN GAME": "W GRZE", "SET GAME FOLDER": "USTAW FOLDER GRY", "SET SERVER": "USTAW SERWER", "RETRY": "PONÓW",
    "UPDATE & PLAY": "AKTUALIZUJ I GRAJ",
    # ---- progress
    "Checking for updates": "Sprawdzanie aktualizacji", "Verifying files": "Sprawdzanie plików", "Downloading": "Pobieranie", "Downloading launcher": "Pobieranie launchera", "Working": "Pracuję",
    "{t} left": "zostało {t}", "{pct}%  {a} of {b}": "{pct}%  {a} z {b}", "s": "s", "min": "min",
    # ---- alerts / toasts
    "DONE": "GOTOWE", "SOMETHING WENT WRONG": "COŚ POSZŁO NIE TAK", "NOT ENOUGH LOADOUT POINTS": "ZA MAŁO PUNKTÓW WYPOSAŻENIA",
    "Synced with game": "Zsynchronizowano z grą", "Will apply when the game is in the menu": "Zastosuje się, gdy gra będzie w menu", "Start the game once to sync": "Uruchom grę raz, aby zsynchronizować", "Could not write the game file": "Nie udało się zapisać pliku gry",
    "{name} costs {cost}. You have {left} left.": "{name!}: koszt {cost} PKT. Zostało ci {left} PKT.",
    "OVERRIDDEN BY FACTION'S CHOICE": "NADPISANE WYBOREM FRAKCJI", "Your clan's faction picks the backgrounds.": "Tła wybiera frakcja twojego klanu.",
    "Client updated to {v} ({n} files).": "Klient zaktualizowany do wersji {v} ({n} {n|plik|pliki|plików}).", "Client is up to date ({v}).": "Klient jest aktualny ({v}).",
    "Cannot reach the update server and no client is installed yet. Try again in a moment.": "Brak połączenia z serwerem aktualizacji, a klient nie jest jeszcze zainstalowany. Spróbuj ponownie za chwilę.",
    "Set the game folder first.": "Najpierw ustaw folder gry.", "Client files verified and mod files re-installed into the game folder.": "Pliki klienta sprawdzone, a pliki moda zainstalowane w folderze gry ponownie.",
    "Please describe what happened first.": "Najpierw opisz, co się stało.", "Report sent. Thank you!": "Zgłoszenie wysłane. Dziękujemy!", "Game folder set.": "Folder gry ustawiony.",
    "{n} install(s) found.": "Znalezione instalacje: {n}.", "Searching...": "Szukam...", "Select the folder for the client files": "Wybierz folder na pliki klienta",
    # ---- who is playing
    "In-game name": "Nazwa w grze", "Custom name (Settings)": "Własna nazwa (Ustawienia)", "Steam name": "Nazwa ze Steama", "Windows user": "Użytkownik Windows",
    # ---- clan tab
    "Loading clan...": "Wczytywanie klanu...", "WEEK {w}": "TYDZIEŃ {w}", "DAY {d}": "DZIEŃ {d}", "WEEK {w}: DAY {d}": "TYDZIEŃ {w}: DZIEŃ {d}", "CAMP TALK": "ROZMOWY W OBOZIE", "CAMP": "OBÓZ",
    "CAMP MORALE": "MORALE W OBOZIE", "HAPPENING IN CAMP": "CO SIĘ DZIEJE W OBOZIE", "hopeful": "NADZIEJA", "steady": "STABILNE", "strained": "NAPIĘTE", "grim": "PONURE", "HOPEFUL": "NADZIEJA", "STEADY": "STABILNE", "STRAINED": "NAPIĘTE", "GRIM": "PONURE",
    "Nothing in the journal yet. Play a match: your clan will start talking.": "Dziennik jest jeszcze pusty. Zagraj mecz, a twój klan zacznie opowiadać.",
    "Could not reach the clan service": "Brak połączenia z usługą klanu", "Your clan is stored on the game server; the host's update server must run with a database (API.md, /clan.json).": "Twój klan jest zapisany na serwerze gry; serwer aktualizacji hosta musi działać z bazą danych (API.md, /clan.json).",
    "Clan service error": "Błąd usługi klanu", "Your clan appears after your first match on this install.": "Twój klan pojawi się po pierwszym meczu na tej instalacji.",
    "On the very first launch of the game you choose your side (WLF or Seraphites) once for your clan. If you played before, finish one match with this install and it shows up here.": "Przy pierwszym uruchomieniu gry wybierasz stronę (WLF lub Serafici) raz, dla swojego klanu. Jeśli grałeś już wcześniej, zakończ jeden mecz na tej instalacji, a klan pojawi się tutaj.",
    "YOUR CLAN SURVIVED": "TWÓJ KLAN PRZETRWAŁ", "YOUR CLAN IS GONE": "TWÓJ KLAN PRZESTAŁ ISTNIEĆ", "CLANS WON": "WYGRANE KLANY", "CLANS LOST": "PRZEGRANE KLANY", "LARGEST CLAN": "NAJWIĘKSZY KLAN",
    "Choose your side again in the game's main menu to start a new clan.": "Wybierz stronę ponownie w głównym menu gry, aby założyć nowy klan.",
    "ACTIVE MISSION": "AKTYWNA MISJA", "EVENT TRAINING": "SZKOLENIE NA WYDARZENIE", "PRACTICE": "TRENING", "TIER {n}": "POZIOM {n}", "Day {d}/3": "Dzień {d}/3", "1 match left": "Został 1 mecz",
    "{n} matches left": "Pozostało meczów: {n}", "None picked": "Nie wybrano", "Pick one from CHOOSE MISSION in the game's main menu.": "Wybierz misję w WYBIERZ MISJĘ w głównym menu gry.",
    "EVENT": "WYDARZENIE", "ATTACK ON YOUR CAMP": "ATAK NA TWÓJ OBÓZ", "ATTACK": "ATAK", "FRIENDLY GROUP": "PRZYJAZNA GRUPA", "RESCUED HOSTAGES": "ODBICIE ZAKŁADNIKÓW", "RESCUE ALLIES": "RATUNEK DLA SOJUSZNIKÓW",
    "Match {a} of {b}.": "Mecz {a} z {b}.", "Casualties follow the mission tier you reach.": "Straty zależą od poziomu misji, który osiągniesz.", "New members follow the mission tier you reach.": "Nowi członkowie zależą od poziomu misji, który osiągniesz.",
    "NEXT MATCH": "NASTĘPNY MECZ", "An event starts with your next match.": "Wydarzenie zacznie się wraz z następnym meczem.", "LAST MATCH (DAY {d})": "OSTATNI MECZ (DZIEŃ {d})",
    "Parts earned": "Zdobyte części", "Supplies": "Zaopatrzenie", "Survivors gained": "Nowi ocalali", "Died": "Zmarli", "New hungry / sick": "Nowi głodni / chorzy", "Healed": "Wyleczeni",
    "tier {n}": "poziom {n}", "+{n} booster": "+{n} dopalacz", "Match left early: the day passed with no supplies.": "Mecz opuszczono wcześniej: dzień minął bez zaopatrzenia.",
    "{a} of {b} days survived": "Przetrwane dni: {a} z {b}", "week {a} of {b}": "tydzień {a} z {b}", "{n} SURVIVORS": "OCALALI: {n}", "HEALTHY": "ZDROWI", "HUNGRY": "GŁODNI", "SICK": "CHORZY",
    "NEEDED PER DAY": "POTRZEBNE DZIENNIE", "+{n} for the next one-use booster": "+{n} do następnego jednorazowego dopalacza", "ONE-USE BOOSTERS": "JEDNORAZOWE DOPALACZE",
    "Clans won {a}": "Wygrane klany: {a}", "lost {a}": "przegrane: {a}", "largest clan {a}": "największy klan: {a}", "Could not show the clan: {e}": "Nie można pokazać klanu: {e}",
    # ---- news / loading
    "Could not load news: {e}": "Nie można wczytać aktualności: {e}", "Nothing new.": "Nic nowego.", "{n} threads": "wątki: {n}",
    # ---- report a bug
    "WHAT HAPPENED": "CO SIĘ STAŁO", "REQUIRED": "WYMAGANE", "Describe the bug: what you did, what you expected, what happened instead.": "Opisz błąd: co robiłeś, czego oczekiwałeś i co stało się zamiast tego.",
    "WHEN": "KIEDY", "Just now": "Przed chwilą", "Last match": "Ostatni mecz", "Earlier today": "Wcześniej dzisiaj", "Another day": "Innego dnia", "MAP / MODE (OPTIONAL)": "MAPA / TRYB (OPCJONALNIE)",
    "TIME DETAILS (OPTIONAL)": "SZCZEGÓŁY CZASU (OPCJONALNIE)", "for example 21:40, in the second round": "na przykład 21:40, w drugiej rundzie",
    "Include older crash dumps too (the newest dump from the last 7 days is always sent)": "Dołącz także starsze zrzuty awarii (najnowszy zrzut z ostatnich 7 dni jest zawsze wysyłany)",
    "FILES THAT WILL BE SENT": "PLIKI, KTÓRE ZOSTANĄ WYSŁANE", "Your token and other secrets are never sent. Logs have token-like strings removed. The report goes to the Twelve Weeks update server.": "Twój token i inne sekrety nigdy nie są wysyłane. Z logów usuwane są ciągi podobne do tokenów. Zgłoszenie trafia na serwer aktualizacji Twelve Weeks.",
    "SEND REPORT": "WYŚLIJ ZGŁOSZENIE", "REPORT CODE": "KOD ZGŁOSZENIA", "Quote this code when you talk to the dev.": "Podaj ten kod, gdy rozmawiasz z twórcą.",
    "OS, CPU, GPU, versions, player name, Steam id": "system, procesor, karta graficzna, wersje, nazwa gracza, identyfikator Steam", "Collecting files...": "Zbieranie plików...", "Sending {size}... {pct}%": "Wysyłanie {size}... {pct}%",
    "Sent {size}.": "Wysłano {size}.", "newest crash dump": "najnowszy zrzut awarii", "older crash dump": "starszy zrzut awarii", "last 20 MB": "ostatnie 20 MB",
    "not found in {dir} - play a match first": "nie znaleziono w {dir} - najpierw zagraj mecz", "game folder not set - set it in Settings > Game": "folder gry nie ustawiony - ustaw go w Ustawieniach > Gra",
    "Capitol Hill": "Capitol Hill", "Gas Station": "Stacja benzynowa", "Train Station": "Dworzec", "Shipyard": "Stocznia", "School": "Szkoła", "Hospital": "Szpital", "Forest": "Las", "Seraphite Camp": "Obóz Serafitów",
    "Houses": "Domy", "Overpass": "Wiadukt", "Resort": "Ośrodek", "Tilted / other": "Tilted / inna", "Menu / lobby": "Menu / lobby",
    # ---- settings
    "DISPLAY": "WYŚWIETLANIE", "FILES": "PLIKI", "ABOUT": "INFORMACJE", "GAME FOLDER": "FOLDER GRY", "DETECT": "WYKRYJ", "BROWSE": "PRZEGLĄDAJ", "The folder that contains tlou-ii.exe.": "Folder, w którym leży tlou-ii.exe.",
    "PLAYER NAME": "NAZWA GRACZA", "empty = in-game name, then Steam name, then Windows user": "puste = nazwa w grze, potem nazwa ze Steama, potem użytkownik Windows",
    "Skip the server and version check before starting (emergencies only)": "Pomiń sprawdzanie serwera i wersji przed startem (tylko awaryjnie)", "LANGUAGE": "JĘZYK", "ENGLISH": "ENGLISH", "POLSKI": "POLSKI",
    "BACKGROUNDS": "TŁA", "ROTATE": "ZMIENIAJ", "PICK ONE": "WYBIERZ JEDNO", "WLF set (your clan)": "Zestaw WLF (twój klan)", "Seraphite set (your clan)": "Zestaw Serafitów (twój klan)", "Neutral set (no clan yet)": "Zestaw neutralny (jeszcze bez klanu)",
    "Background motion (very slow, subtle)": "Ruch tła (bardzo powolny, subtelny)", "Film grain": "Ziarno filmowe", "Menu sounds": "Dźwięki menu", "SOUND VOLUME": "GŁOŚNOŚĆ DŹWIĘKÓW", "Menu music": "Muzyka w menu", "MUSIC VOLUME": "GŁOŚNOŚĆ MUZYKI",
    "TO DOWNLOAD": "DO POBRANIA", "INSTALLED": "ZAINSTALOWANE", "LATEST": "NAJNOWSZE", "UPDATE CLIENT": "AKTUALIZUJ KLIENTA", "VERIFY FILES": "SPRAWDŹ PLIKI", "REPAIR INSTALL": "NAPRAW INSTALACJĘ", "CANCEL": "ANULUJ",
    "OPEN GAME FOLDER": "OTWÓRZ FOLDER GRY", "OPEN CLIENT FILES": "OTWÓRZ PLIKI KLIENTA", "OPEN LOGS": "OTWÓRZ LOGI", "CLIENT FILES FOLDER": "FOLDER PLIKÓW KLIENTA", "Where the downloaded mod files live. Empty = default.": "Tu leżą pobrane pliki moda. Puste = domyślny.",
    "LAUNCHER": "LAUNCHER", "BUILD DATE": "DATA KOMPILACJI", "ELECTRON": "ELECTRON", "SYSTEM": "SYSTEM", "CPU": "PROCESOR", "MEMORY": "PAMIĘĆ", "LAUNCHER DATA": "DANE LAUNCHERA", "UPDATE LAUNCHER": "AKTUALIZUJ LAUNCHER",
    "Twelve Weeks is a fan project, not affiliated with or endorsed by Sony Interactive Entertainment or Naughty Dog.": "Twelve Weeks to projekt fanowski, niezwiązany z Sony Interactive Entertainment ani Naughty Dog i przez nie niepopierany.",
    # ---- backgrounds
    "WLF HEADQUARTERS": "KWATERA WLF", "THE MESS HALL": "STOŁÓWKA", "THE STADIUM": "STADION", "THE BLEACHERS": "TRYBUNY", "THE FORWARD BASE": "BAZA WYPADOWA", "WLF PATROL": "PATROL WLF", "THE CONCOURSE": "HALA", "THE DOCKS": "PORT", "THE WALL": "MUR", "HAVEN": "HAVEN", "THE VILLAGE": "WIOSKA", "THE HUTS": "CHATY", "THE CROPS": "UPRAWY", "THE BOARDWALK": "POMOST", "THE ISLAND": "WYSPA", "SMOKE ON THE HORIZON": "DYM NA HORYZONCIE", "THE BURNING": "POŻAR", "THE PIERS": "MOLA", "EMBERS": "ŻAR", "THE FALLS": "WODOSPAD", "UNDER THE OVERPASS": "POD WIADUKTEM", "SEATTLE": "SEATTLE", "OVERGROWTH": "ZAROŚNIĘTE MIASTO", "THE FLOODED STREET": "ZALANA ULICA", "RAIN": "DESZCZ",
    # ---- GEAR UP
    "MULTIPLAYER": "TRYB WIELOOSOBOWY", "CLASSES": "KLASY", "EQUIPPED": "W UŻYCIU", "EDIT": "EDYTUJ", "Pre-made classes are view only.": "Gotowe klasy są tylko do podglądu.",
    "CUSTOM LOADOUT {n}": "WŁASNE WYPOSAŻENIE {n}", "{n} LP": "{n} PKT", "{a}/{b} LP": "{a}/{b} PKT", "{a}/{b} Loadout Points": "Punkty wyposażenia: {a}/{b}", "FREE": "ZA DARMO",
    "SMALL FIREARM": "BROŃ KRÓTKA", "LARGE FIREARM": "BROŃ DŁUGA", "SURVIVAL SKILL {n}": "UMIEJĘTNOŚĆ PRZETRWANIA {n}", "PURCHASABLE": "DO KUPIENIA", "No skills": "Brak umiejętności",
    "RESET LOADOUT": "ZRESETUJ WYPOSAŻENIE", "LOUD": "GŁOŚNO", "QUIET": "CICHO", "Nothing equipped in this slot.": "Nic nie ma w tym miejscu.",
    "Suppressed: fewer enemies hear the shots, and firing does not show you on the enemy radar. +{n} LP.": "Z tłumikiem: mniej wrogów słyszy strzały, a strzelanie nie pokazuje cię na radarze wroga. +{n} PKT.", "Standard. QUIET adds a suppressor for +{n} LP.": "Standard. CICHO dodaje tłumik za +{n} PKT.",
    "NO LARGE FIREARM": "BRAK BRONI DŁUGIEJ", "NO PURCHASABLE": "BRAK PRZEDMIOTU DO KUPIENIA",
    "SERVER RESTART": "RESTART SERWERA", "SERVER SHUTTING DOWN": "WYŁĄCZANIE SERWERA", "SERVER NOTICE": "KOMUNIKAT SERWERA", "New update available - restart after finishing the match.": "Dostępna nowa aktualizacja - uruchom grę ponownie po zakończeniu meczu.",
    "Server restarting in {n} min.": "Restart serwera za {n} min.", "Server restarting in {n} s.": "Restart serwera za {n} s.", "Server is shutting down.": "Serwer się wyłącza.",
    "Finish your match - your progress is saved.": "Dokończ mecz - twój postęp jest zapisany.",
    "SUPPRESSED {n}": "{n!} Z TŁUMIKIEM", "OF POPULATION": "POPULACJI",
    # ---- missions the game table does not translate
    "Special Executions": "Egzekucje specjalne", "Molotov Executions": "Egzekucje koktajlem Mołotowa", "Downs with Bombs": "Powalenia bombami", "Gift Crafting Items": "Podaruj materiały do wytwarzania",
    "Downs with Melee": "Powalenia bronią białą", "Shiv Executions": "Egzekucje nożem", "Downs from Long Range": "Powalenia z dużej odległości", "Downs with 9mm Pistol": "Powalenia pistoletem 9 mm",
    "Downs with Revolver": "Powalenia rewolwerem", "Downs with the Shorty": "Powalenia obrzynem", "Downs with Hunting Rifle": "Powalenia karabinem myśliwskim", "Downs with Semi Auto Rifle": "Powalenia karabinem samopowtarzalnym",
    "Downs with Burst Rifle": "Powalenia karabinem seryjnym", "Downs with Bow": "Powalenia łukiem", "Headshots": "Strzały w głowę", "Revives": "Ożywienia",
    # ---- main-process messages (errors shown to the player)
    "Please describe what happened (at least a sentence).": "Opisz, co się stało (przynajmniej jedno zdanie).", "No file host set (Settings > Files): reports go to the update server.": "Nie ustawiono hosta plików: zgłoszenia trafiają na serwer aktualizacji.",
    "The server refused the report: {e}": "Serwer odrzucił zgłoszenie: {e}", "The server answered HTTP {s}.": "Serwer odpowiedział: HTTP {s}.", "the game server did not answer": "serwer gry nie odpowiedział",
    "update server: {e}": "serwer aktualizacji: {e}", "Busy ({what}). Wait for it to finish.": "Zajęte ({what}). Poczekaj na zakończenie.", "No file host configured (Settings > Files).": "Nie skonfigurowano hosta plików.",
    "Play is disabled in test / screenshot mode.": "Granie jest wyłączone w trybie testowym.", "Game folder not set. Open Settings > Game.": "Nie ustawiono folderu gry. Otwórz Ustawienia > Gra.",
    "No server address. Set it in Settings > Game (or ship server.txt in the client files).": "Brak adresu serwera.", "The server lists no launcher build.": "Serwer nie podaje wersji launchera.",
    "Self-update only works from the packaged portable exe.": "Samoaktualizacja działa tylko ze spakowanego pliku exe.", "tlou-ii.exe is not in that folder.": "W tym folderze nie ma pliku tlou-ii.exe.",
    "Game folder not set.": "Nie ustawiono folderu gry.", "Close the game first.": "Najpierw zamknij grę.", "Unknown folder": "Nieznany folder",
    "The game folder is not set (tlou-ii.exe not found). Pick it in Settings > Game.": "Folder gry nie jest ustawiony (nie znaleziono tlou-ii.exe). Wskaż go w Ustawieniach > Gra.",
    "The game is already running. Close it and start it only from this launcher.": "Gra jest już uruchomiona. Zamknij ją i uruchamiaj tylko z tego launchera.",
    "Cannot reach the server at {server}. Is the host's server running? Is the address right (it changes if the host re-created the tunnel)?": "Brak połączenia z serwerem {server}. Czy serwer hosta działa? Czy adres jest poprawny (zmienia się, gdy host odtworzy tunel)?",
    "VERSION MISMATCH: your game build is '{a}' but the server runs '{b}'. Press UPDATE CLIENT, then play again.": "NIEZGODNA WERSJA: twoja wersja gry to '{a}', a serwer działa na '{b}'. Naciśnij AKTUALIZUJ KLIENTA i zagraj ponownie.",
    "winmm.dll is missing from the downloaded client files. Run Verify / Repair in Settings > Files.": "Brak winmm.dll w pobranych plikach klienta. Uruchom sprawdzanie / naprawę w Ustawieniach > Pliki.",
    "winmm.dll is not a T2R client build.": "winmm.dll nie pochodzi z klienta T2R.", "update server unreachable (cached)": "serwer aktualizacji niedostępny", "timeout": "przekroczono czas oczekiwania", "cancelled": "anulowano",
    "connection lost": "utracono połączenie", "HTTP {c}": "HTTP {c}", "Checksum mismatch for {f}": "Błędna suma kontrolna: {f}", "Bad manifest (no files list).": "Błędny manifest (brak listy plików).",
    "The server address '{s}' is wrong. It must look like name:port (for example abc-123.joinmc.link:12345).": "Adres serwera '{s}' jest nieprawidłowy. Musi wyglądać jak nazwa:port (na przykład abc-123.joinmc.link:12345).",
    "The server name '{h}' was not found. Check the address for typos and that your internet connection works.": "Nie znaleziono serwera '{h}'. Sprawdź adres i połączenie z internetem.",
}
PL.update({   # clan chronicle view (roster with portraits, match summaries with loot, styled journal captions)
    "SURVIVORS": "OCALALI", "CLOSE TO": "BLISKI", "MATCHES": "MECZE", "PARTS": "CZĘŚCI", "BROUGHT HOME": "PRZYNIESIONO DO OBOZU", "IN CAMP NOW": "W OBOZIE TERAZ",
    "Down on their side": "Po ich stronie", "Lost": "Straty", "Times downed": "Razy powalony", "SUPPLIES": "ZAPASY", "RATIONS": "RACJE", "NEXT RAID": "NASTĘPNY WYPAD",
    "LOST": "STRATA", "LAST WORDS": "OSTATNIE SŁOWA", "SICK BAY": "IZBA CHORYCH", "HUNGER": "GŁÓD", "NEWCOMER": "NOWY W OBOZIE", "STORES": "ZAPASY OBOZU", "MATCH": "MECZ",
           "RAID": "WYPAD", "KEEPSAKE": "PAMIĄTKA", "BIRTH": "NARODZINY", "LAST WISH": "OSTATNIE ŻYCZENIE", "BLAME": "WINA", "BETRAYAL": "ZDRADA", "STORY": "HISTORIA",
           "STEP {n}": "KROK {n}", "THE WHOLE STORY SO FAR": "CAŁA HISTORIA DOTĄD"})
PL.update({   # clan screen: supplies, raids, NEW markers, loot
    "NEW": "NOWE", "{n} / DAY": "{n} / DZIEŃ", "IN CAMP": "W OBOZIE", "SHORT {n}": "BRAK {n}", "THIS WEEK: BROUGHT VS NEEDED": "TEN TYDZIEŃ: PRZYNIESIONO I POTRZEBNE",
    "LAST RAID": "OSTATNI WYPAD", "BROUGHT": "PRZYNIESIONO", "NEEDED": "POTRZEBNE", "THE STOCK LASTS": "ZAPASY WYSTARCZĄ NA", "NOBODY GOES HUNGRY OR SICK": "NIKT NIE GŁODUJE ANI NIE CHORUJE",
    "MORALE +{n}": "MORALE +{n}", "SHORT BY {n}": "BRAKUJE {n}", "SUPPLIES BROUGHT HOME": "ZAPASY PRZYNIESIONE DO OBOZU", "RAIDS": "WYPADY", "1 DAY": "1 DZIEŃ", "{n} DAYS": "{n} DNI",
    "DAY": "DZIEŃ", "DAYS": "DNI", "ENOUGH, +{n} OVER": "WYSTARCZY, +{n} NADWYŻKI", "JUST ENOUGH": "DOKŁADNIE TYLE, ILE TRZEBA", "1 WENT HUNGRY": "1 OSOBA GŁODNA", "{n} WENT HUNGRY": "GŁODNYCH: {n}",
    "1 FELL SICK": "1 OSOBA ZACHOROWAŁA", "{n} FELL SICK": "ZACHOROWAŁO: {n}", "1 HEALED": "1 OSOBA WYLECZONA", "{n} HEALED": "WYLECZONO: {n}", "GOES HUNGRY": "GŁODUJE", "IS SICK": "JEST CHORY",
    "FOOD": "JEDZENIE", "WATER": "WODA", "MEDICINE": "LEKI", "AMMO": "AMUNICJA", "MATERIALS": "MATERIAŁY", "PINEAPPLE": "ANANAS", "BEANS": "FASOLA", "BANDAGES": "BANDAŻE", "ANTIBIOTICS": "ANTYBIOTYKI",
    "ALCOHOL": "SPIRYTUS", ".38 ROUNDS": "NABOJE .38", "9MM BOXES": "PUDEŁKA 9 MM", "WATER FILTERS": "FILTRY DO WODY", "BATTERIES": "BATERIE", "SCISSORS": "NOŻYCZKI", "RAGS": "SZMATY",
    "CHESSBOARD": "SZACHOWNICA", "GUITAR STRING": "STRUNA GITAROWA", "COMIC BOOK": "KOMIKS", "TEDDY BEAR": "PLUSZOWY MIŚ", "SEEDS": "NASIONA", "DECK OF CARDS": "TALIA KART", "HARMONICA": "HARMONIJKA", "MATCH WON": "MECZ WYGRANY", "MATCH LOST": "MECZ PRZEGRANY", "Executions": "Egzekucje", "HOW THIS WEEK WENT": "JAK MINĄŁ TYDZIEŃ", "NONE": "BRAK", "DEPRESSED": "DEPRESJA", "SHOCK": "SZOK", "IN SHOCK": "W SZOKU", "IS DEPRESSED": "MA DEPRESJĘ", "IS IN SHOCK": "JEST W SZOKU", "WHAT THEY FOUND": "CO ZNALEZLI", "SCRAPS": "ODPADKI", "POOR": "SKROMNE", "NORMAL": "ZWYKŁE", "GOOD": "DOBRE", "LUXURIOUS": "LUKSUSOWE", "MORE ABOUT THIS RAID": "WIĘCEJ O TYM WYPADZIE", "EARLIER ENTRIES": "WCZEŚNIEJSZE WPISY", "Click a raid to see what it brought home.": "Kliknij wypad, by zobaczyć, co przyniósł."})
# GEAR UP row titles shown with a number / and the EN names of the empty rows come from the game table (game-pl.json); these are the launcher's own
os.makedirs(os.path.join(HERE, "..", "src", "i18n"), exist_ok=True)
json.dump(PL, open(os.path.join(HERE, "..", "src", "i18n", "pl.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump({k: k for k in PL}, open(os.path.join(HERE, "..", "src", "i18n", "en.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(len(PL), "entries")
