# Pipeline dati settimanale

Automatizza l'aggiornamento della dash con le partite di Serie A appena giocate:

```
API PerformFeeds ──► JSON ──► CSV ──► data/raw/serie_a_<stagione>/events/ ──► precompute ──► pytest ──► commit + push ──► Render
```

La pipeline ristruttura gli script originali della cartella `selenium wire` senza modificarli.
La logica di parsing e conversione è la stessa: `convert.py` produce CSV identici byte per byte a quelli già presenti.

## Riepilogo operativo

- **App pubblicata:** https://fmp-dashboard.onrender.com
  - Render fa auto-deploy a ogni push su `main`. Le impostazioni valide sono nel pannello Render, perché `render.yaml` non viene letto.
  - Python 3.13.5 è fissato da `PYTHON_VERSION` e da `.python-version` nella root.
  - Sul piano Free il servizio va in stop dopo un periodo di inattività: la prima richiesta può impiegare circa 50 s.
- **Run automatici:** ogni **martedì alle 09:00** (LaunchAgent `com.ricki.calcioitaliano.weekly`).
  - Se il Mac era in stop, il run parte al risveglio.
  - Se era spento, parte al login, ma solo se il controllo della settimana non è ancora stato fatto (`--catch-up`).
  - Stato: `launchctl print gui/$(id -u)/com.ricki.calcioitaliano.weekly`.
- **Notifiche** (titolo "Calcio Italiano"):
  - ✅ partite caricate e pubblicate;
  - ℹ️ nessuna nuova partita;
  - ❌ errore;
  - con "⚠️ … ripiego browser" se l'API non era disponibile.
- **Stato stagione 2026/27 al 30/09/2026:** GW1–5 (50 partite) caricate.

### Cosa fare se arriva una notifica ❌

La notifica indica il passo e il motivo; il sottotitolo è il nome del log in `pipeline/logs/run_<data>_<ora>.log`. Tra i passi 7 e 9 la pipeline ha già ripristinato lo stato precedente. Al passo 10, invece, un commit fatto e poi fallito nel push resta in locale.

1. **Apri il log** e cerca la riga `❌ Errore al passo …` e, nel caso del precompute o di pytest, le righe `│` che la precedono.
2. **Diagnosi per passo:**

   | Passo | Causa tipica | Cosa fare |
   |---|---|---|
   | 0 | Branch diverso da `main`, file in staging, modifiche non committate in `data/ready`, `data/processed` o `xg_model.pkl` | Sistema lo stato di git (`git status`), poi rilancia |
   | 1, 4 | Rete assente o API PerformFeeds giù (e ripiego fallito) | Riprova più tardi; se persiste, prova l'API a mano (sezione "Aggiungere una stagione") |
   | 5, 6 | Formato Opta cambiato, squadra sconosciuta (neopromossa), colonne diverse | Leggi il dettaglio; per una squadra nuova aggiorna `team_mapping.py` (vedi sotto) |
   | 8 | Errore nel precompute, parquet non rigenerati | Guarda il traceback nel log; lancia a mano `cd dash_app && .venv/bin/python -m src.analytics.precompute_serie_a <stagione>` |
   | 9 | Test falliti | `cd dash_app && .venv/bin/python -m pytest -q` per vedere quali |
   | 10 | "commit non riuscito" | Controlla `git status` |
   | 10 | "push fallito, commit locale in sospeso" | Di solito sono credenziali GitHub scadute nel Portachiavi: fai un `git push` a mano da terminale. Altrimenti il run successivo ritenta da solo |

3. **Rilancia a mano** dalla root del repo: `dash_app/.venv/bin/python pipeline/run_weekly.py --dry-run`, poi senza opzioni.
4. **Controlla l'app** su https://fmp-dashboard.onrender.com una volta completato il deploy.

## Moduli

| File | Ruolo | Origine |
|---|---|---|
| `seasons.toml` | ID e cartelle per stagione; nessun ID è scritto nel codice | — |
| `config.py` | Legge `seasons.toml` e restituisce un oggetto `Season` con i percorsi | — |
| `opta_client.py` | Sessione HTTP verso `api.performfeeds.com`: header, JSONP, una richiesta alla volta, pausa casuale di 0,5–1,5 s, retry | script 4 |
| `fetch_matches.py` | Elenco partite con stato e giornata. **Principale:** API `soccerdata/match?tmcl=`. **Ripiego:** pagina risultati Scoresway con Selenium | script 2 |
| `download.py` | JSON `matchevent`. **Principale:** download diretto. **Ripiego:** Chrome con intercettazione CDP della risposta più pesante. Salva `<week>_<Home>_<Away>_<id>.json` (JSON pulito, indent=4) e salta le partite già scaricate | script 3 e 4 |
| `convert.py` | JSON → CSV; funzioni copiate **testualmente** dal notebook 1, cella 2 | script 1 |
| `opta_lookups/` | `opta_event_types.csv`, `opta_qualifier_types.csv` (copie identiche) | `try/transformers de opta/` |
| `quality.py` | Controlli prima della copia: CSV non vuoto, colonne uguali a un CSV esistente, `week` valorizzato, squadre risolte da `canonical_name()`, nessun `match_id` duplicato | — |
| `notify.py` | Notifica macOS (`osascript`) con titolo "Calcio Italiano" | — |
| `run_weekly.py` | Orchestratore | — |
| `launchd/` | Copia di riferimento del LaunchAgent | — |

File locali, gitignorati:
- `_work/<stagione>/`: `matches_<stagione>.csv`, `json/`, `csv/`, `.last_success`
- `logs/`: `run_<data>_<ora>.log`, uno per esecuzione, più gli output di launchd

JSON e CSV grezzi **non** vanno mai committati. La pipeline committa solo:
- i `*.parquet` in `data/ready/` e `data/processed/`;
- `data/ready/.csv_count_<stagione>`;
- il modello xG `data/cache/xg_model.pkl`.

## Installazione

La pipeline usa il venv della dash. Le sue dipendenze sono separate da quelle di Render:

```bash
dash_app/.venv/bin/python -m pip install -r pipeline/requirements.txt
```

Non usare `selenium-wire`: è incompatibile con `blinker>=1.8`, richiesto da Flask/Dash, e con setuptools ≥ 81. I ripieghi usano Selenium 4 e leggono le risposte dai log di rete di Chrome.

## Lancio manuale

Dalla root del repo:

```bash
dash_app/.venv/bin/python pipeline/run_weekly.py --dry-run          # fino ai controlli di qualità: niente copia né commit
dash_app/.venv/bin/python pipeline/run_weekly.py --no-push          # tutto, commit locale senza push
dash_app/.venv/bin/python pipeline/run_weekly.py                    # tutto, con push su origin main
dash_app/.venv/bin/python pipeline/run_weekly.py --season 2026/27   # stagione esplicita (default: current_season)
```

Opzioni pensate per launchd:
- `--wait-network`: attende la rete fino a 3 minuti.
- `--catch-up`: esegue solo se il controllo dell'ultimo martedì alle 09:00 non è ancora stato fatto.

### Passi di `run_weekly.py`

0. Verifiche preliminari (non in `--dry-run`): branch `main`, niente in staging, nessuna modifica non committata in `data/ready`, `data/processed`, `data/match_events` o `data/cache/xg_model.pkl`.
1. Elenco partite della stagione: sono "giocate" quelle con `matchStatus == Played`.
2. Confronto dei `match_id` con i CSV già in `data/raw/serie_a_<stagione>/events/`.
3. Se non manca nulla: notifica "nessuna nuova partita" e fine. Se ci sono commit della pipeline non pushati per un push fallito in precedenza, vengono pubblicati qui.
4. Download dei JSON mancanti.
5. Conversione in CSV.
6. Controlli di qualità (`--dry-run` si ferma qui).
7. Copia dei CSV nella cartella raw della dash.
8. Precompute della sola stagione:
   - prima rimuove `player_season_<stagione>.parquet` **della sola stagione corrente**, altrimenti il precompute lo salterebbe;
   - poi verifica che ogni famiglia di parquet sia stata rigenerata;
   - infine scrive `data/ready/.csv_count_<stagione>`, il riferimento usato dal controllo "stale data" dell'app;
   - se la stagione è in `match_analysis_seasons`, esporta i parquet di partita delle sole partite nuove in `data/match_events/<stagione>/` e verifica che ogni CSV raw abbia il suo (vedi [Match Analysis online](#match-analysis-online)).
9. `pytest -q`.
10. Commit (`data: add Serie A 2026/27 GW<n>`) dei parquet cambiati (compresi i nuovi `data/match_events/<stagione>/*.parquet`), di `.csv_count_<stagione>` e di `xg_model.pkl`, poi push su `origin main`, salvo `--no-push`.
11. Notifica con l'esito. Se durante il run è servito un ripiego browser, la notifica lo dice esplicitamente, per esempio "⚠️ API non disponibile, usato ripiego browser (download di 3 partite)".

La pipeline si ferma al primo errore. Se il problema avviene tra i passi 7 e 10, prima del commit, la pipeline ripristina lo stato precedente: rimuove i CSV copiati, riporta i parquet tracciati alla versione committata e cancella quelli nuovi. Così l'esecuzione successiva riparte pulita.
Se fallisce solo il push, il commit resta in locale e viene ritentato alla prossima esecuzione.

Un lock (`_work/.run.lock`) impedisce due esecuzioni contemporanee.

## Aggiungere una stagione

1. Trova l'ID della nuova stagione con l'API tournamentcalendar (non serve il browser):
   ```bash
   dash_app/.venv/bin/python -c "
   import sys; sys.path.insert(0, 'pipeline')
   from opta_client import OptaClient
   _, d = OptaClient('ft1tiv1inq7v1sk3y9tv12yh5').get_json('tournamentcalendar', comp='1r097lpxe0xn03ihb7wi98kao')
   [print(t['name'], t['id'], t['active']) for t in d['competition'][0]['tournamentCalendar'][:3]]"
   ```
2. Aggiungi un blocco in `seasons.toml`:
   ```toml
   [seasons.2027_2028]
   label = "2027/28"
   tournament_calendar_id = "<id>"
   results_url = "https://www.scoresway.com/en_GB/soccer/serie-a-2027-2028/<id>/results"
   raw_events_dir = "data/raw/serie_a_2027_2028/events"
   ```
3. Aggiorna `current_season` in `[defaults]`.
4. Le neopromosse devono essere risolte da `canonical_name()`. Se `quality.py` segnala una squadra sconosciuta:
   - aggiungi alias e logo in `dash_app/src/team_mapping.py` (`TEAM_LOGO_MAP` e `_CSV_ALIASES`);
   - metti il logo in `docs/logos/seriea/`.
5. Lancia `run_weekly.py --dry-run`, poi `--no-push`.

In locale la dash vede la stagione appena esiste `data/raw/serie_a_<stagione>/`. Su Render, dove `data/raw/` non c'è, la vede quando esiste `data/ready/standings_<stagione>.parquet` (`src/config.py:discover_seasons`).

Per la Match Analysis online vedi anche la sezione [Cambio di stagione](#cambio-di-stagione).

## Match Analysis online

Le sezioni della Match Analysis leggono i dati evento della singola partita. In locale li prendono da `data/raw/`; su Render, dove `data/raw/` non c'è, li prendono da parquet compatti versionati nel repo:

```
data/match_events/<stagione>/<stesso nome del CSV raw>.parquet
```

- **Quali stagioni:** solo quelle elencate in `match_analysis_seasons` (`seasons.toml`, sezione `[defaults]`). Su Render il selettore della Match Analysis mostra solo queste stagioni. Se si arriva a un'altra stagione, compare il messaggio "Match Analysis is not available online for the … season". In locale si vedono sempre tutte.
- **Contenuto:** le 108 colonne lette dalla Match Analysis (`MATCH_EVENT_COLUMNS` in `dash_app/src/utils/match_event_columns.py`), con ogni cella salvata come testo originale. Circa 96 KB per partita, circa 36 MB per stagione completa.
  - Quando si apre una partita, il CSV viene ricostruito in `/tmp/fmp_match_events/` (al massimo 30 file, i meno usati vengono rimossi). Le analisi lo leggono come un CSV raw, con gli stessi tipi e quindi gli stessi numeri.
- **Guardia:** `tests/test_match_events.py` fallisce se un modulo della Match Analysis inizia a usare una colonna non pubblicata. In quel caso:
  1. aggiungi la colonna a `MATCH_EVENT_COLUMNS`;
  2. riesporta con `--force` le stagioni pubblicate.
- **Pipeline:** il passo 8 aggiorna solo la stagione corrente, se è in `match_analysis_seasons`, ed esporta solo le partite nuove (circa 1 MB a giornata).

Comandi manuali (da `dash_app/`):

```bash
.venv/bin/python -m src.utils.match_events export --season 2026_2027 [--season ...] [--force]
.venv/bin/python -m src.utils.match_events prune --keep 2026_2027 2025_2026
```

### Cambio di stagione

Esempio: arriva il 2027/28 e si tengono online due stagioni.

1. Completa i passi di [Aggiungere una stagione](#aggiungere-una-stagione).
2. In `seasons.toml` aggiorna `match_analysis_seasons`: aggiungi la nuova stagione e togli la più vecchia, per esempio `["2027_2028", "2026_2027"]`.
3. Rimuovi dal repo le stagioni non più elencate:
   ```bash
   cd dash_app && .venv/bin/python -m src.utils.match_events prune --keep 2027_2028 2026_2027
   ```
4. Committa la rimozione (`git add -A data/match_events && git commit`). I parquet della nuova stagione li crea e committa la pipeline al primo run con partite nuove. Per anticiparli lancia `export --season 2027_2028`.

I file rimossi spariscono dal deploy ma **restano nella storia git**: il repo non si alleggerisce, e una stagione tolta si può ripubblicare rilanciando `export`. Per eliminarli davvero dalla storia serve una riscrittura (`git filter-repo`), da valutare a parte.

## Metodi di ripiego

| Metodo | Stato (verificato il 2026-09-30) |
|---|---|
| API `match?tmcl=` + download diretto `matchevent` (principali) | ✅ circa 1–2 s a partita |
| Ripiego Selenium 4 **headless** | ❌ **non operativo**: Scoresway risponde "Access Denied" (403) a Chrome headless |
| Ripiego Selenium 4 con **finestra visibile** (`browser_headless = false`, default) | ✅ pagina risultati: 50 partite; download: circa 12 s a partita, CSV identico al download diretto |

Il metodo **principale è sempre l'API**. I ripieghi entrano in gioco **solo** se l'API fallisce, e la notifica finale lo segnala. Con la finestra visibile, durante il run si apre Chrome, quindi serve una sessione utente attiva, che il LaunchAgent ha.

## Pianificazione settimanale (launchd)

Il LaunchAgent `launchd/com.ricki.calcioitaliano.weekly.plist` lancia la pipeline **ogni martedì alle 09:00** con `--wait-network --catch-up`.

- **Mac in stop alle 09:00:** launchd avvia il job al risveglio. Più scadenze perse vengono fuse in una.
- **Mac spento alle 09:00:** la scadenza va persa. Per questo il job ha anche `RunAtLoad`: al login la pipeline controlla se il run dell'ultimo martedì è già stato fatto.
  - Se sì, termina subito con la notifica "nessuna nuova partita".
  - Se no, recupera.

Attivazione:
```bash
cp pipeline/launchd/com.ricki.calcioitaliano.weekly.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.ricki.calcioitaliano.weekly.plist
launchctl print gui/$(id -u)/com.ricki.calcioitaliano.weekly | head -30   # verifica
```

Esecuzione immediata, per un test:
```bash
launchctl kickstart gui/$(id -u)/com.ricki.calcioitaliano.weekly
```

Disattivazione:
```bash
launchctl bootout gui/$(id -u)/com.ricki.calcioitaliano.weekly
rm ~/Library/LaunchAgents/com.ricki.calcioitaliano.weekly.plist
```

Se modifichi il plist, rifai `bootout` e poi `bootstrap`.

## Problemi aperti

- **Stagione 2025/26, fuori dallo scope della pipeline.** In `data/raw/serie_a_2025_2026/events/`:
  - manca `30_Atalanta_Verona_mj3bplbtymyn235up234w93o.csv`, presente in `Result_SerieA_25_26/`;
  - c'è `23_Bologna_Milan_ez4c76g0he7o1bvd8iaitxjiscopia.csv`, cioè il file di Bologna–Milan con il suffisso "copia" nel nome.

  Per questo la stagione ha 379 CSV invece di 380. Da sistemare a parte.
- **Modello xG non congelato:** da valutare.
  - `src/analytics/xg.py` riaddestra `data/cache/xg_model.pkl` ogni volta che cambia il numero totale di CSV raw, quindi a ogni aggiunta di partite.
  - Il precompute settimanale usa il modello appena riaddestrato, che la pipeline committa. Di conseguenza gli xG di **tutte** le stagioni calcolati al volo, e quelli della stagione ricalcolata, possono variare leggermente di settimana in settimana.
  - I parquet xG delle stagioni passate restano invece quelli del precompute con cui sono stati generati.
  - Possibile soluzione: congelare il modello su un set di stagioni fisso.
- **`formation_positions_<stagione>.parquet`:** nessun codice del repo lo genera più, quindi manca per il 2026/27. La pipeline lo esclude dal controllo del passo 8; va affrontato a parte.
- Una volta concluso il turno, Opta corregge a volte i dati degli eventi (per esempio `lastModified`). La pipeline scarica ogni partita una volta sola e non la riscarica.
