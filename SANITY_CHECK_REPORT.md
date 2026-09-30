# Sanity Check Report — Calcio Italiano Dash

Audit in sola lettura eseguito il 2026-09-30. Nessun file di progetto è stato modificato: questo report è l'unico file scritto durante l'audit.

---

## 1. Executive Summary

- **L'app si avvia correttamente.** `app.py` importa senza errori, il router mappa tutte le rotte a layout esistenti, `server = app.server` è presente (riga 140), il cache warm-up completa con successo per tutte e 5 le stagioni (2021/22 → 2025/26). L'unico problema di avvio è un **conflitto di porta 8050** dovuto a un processo `app.py` preesistente (avviato da un altro ambiente conda, non da questo audit) — non un bug dell'app.
- **I test NON passano tutti in modo pulito.** 112 test passano istantaneamente (`test_xg.py`, `test_ppda.py`, `test_data_loader.py`, `test_high_regains.py`, e 60/63 di `test_chance_creation.py`). Ma **3 test in `TestPossessionValueModelBuild` (in `test_chance_creation.py`) si bloccano/impiegano tempo eccessivo** (>9 minuti CPU, poi terminati manualmente) — causa probabile: `PossessionValueModel.build()` con DataFrame sintetici pre-caricati non attiva il percorso di fallback e finisce per scandire l'intero corpus reale di CSV Opta (`RAW_DATA_DIR`) invece di usare solo i dati sintetici del test.
- **I dati sono presenti.** 123 file parquet trovati; 122 sono tracciati in git. Le stagioni 2021/22–2025/26 sono coperte per la maggior parte delle tabelle (alcune mancano l'ultima stagione per design, es. `gk_events`, `ft_entries`).
- **Rischio di deploy latente su Render:** `.gitignore` contiene una regola generica `data/` in fondo al file. I parquet attualmente tracciati sono "grandfathered" (aggiunti prima che la regola esistesse), ma **qualsiasi nuovo file generato da un futuro run di precompute in `data/` verrà ignorato silenziosamente da git** a meno di `git add -f`.
- **Ambiente Python duplicato e disallineato:** esistono DUE virtualenv (`.venv/` in root e `dash_app/.venv/`), entrambi **privi di `scikit-learn`** nonostante il requirements.txt avverta esplicitamente che questo causa un degrado silenzioso del modulo Possession Value (tutti i valori PV mostrano 0.00). Le versioni installate divergono anche dai pin di `requirements.txt` (dash 4.0.0 installato vs 4.1.0 richiesto, pandas 3.0.1 vs 2.3.3, pyarrow 23.0.1 vs 22.0.0).
- **Le decisioni analitiche "locked" sono in gran parte confermate corrette**, con un'eccezione importante: coesistono due valori diversi per il bordo dell'area di rigore (83.33 corretto vs 83.5 residuo) nello stesso file `defensive_structure.py`, usato per classificazione analitica reale, non solo per il disegno del campo.
- Il bug noto in `_is_set_piece_event()` (filtro squadra mancante) **risulta già corretto** nel codice attuale — coerente con le modifiche non ancora committate.

---

## 2. Tabella dei problemi

| # | Area | File:riga | Descrizione | Severità |
|---|------|-----------|--------------|----------|
| 1 | Test suite | `dash_app/tests/test_chance_creation.py::TestPossessionValueModelBuild` (righe 795-855) + `dash_app/src/analytics/possession_value.py:594` | `PossessionValueModel.build()` con DataFrame sintetici pre-caricati (`pre_loaded`) non salta la scoperta CSV reale (`_discover_match_csvs(raw_dir)` con `raw_dir=None` → `RAW_DATA_DIR`); il test finisce per processare l'intero corpus Opta reale invece dei soli dati sintetici. Osservato: processo pytest a >9 min CPU time, terminato manualmente senza completare. | **CRITICA** |
| 2 | Ambiente / dipendenze | `dash_app/.venv/` e `.venv/` (root) | Entrambi i venv NON hanno `scikit-learn` installato. Il modulo Possession Value degrada silenziosamente a 0.00 ovunque (comportamento documentato in `requirements.txt` righe 11-20 ma non rispettato nell'ambiente corrente). Log conferma: `ERROR | dashboard.pv_model_util | Failed to load PV model ... No module named 'sklearn'`. | **ALTA** |
| 3 | Ambiente / dipendenze | `dash_app/.venv/`, `.venv/` vs `dash_app/requirements.txt` | Versioni installate disallineate dai pin: dash 4.0.0 (richiesto 4.1.0), pandas 3.0.1 (richiesto 2.3.3), pyarrow 23.0.1 (richiesto 22.0.0), plotly 6.5.2/6.6.0 (richiesto 6.5.0). `pip check` non segnala conflitti, ma i pin dichiarati "for reproducibility" non sono rispettati nell'ambiente locale. | **MEDIA** |
| 4 | Analitica — soglia area di rigore | `dash_app/src/analytics/defensive_structure.py:104` | `OPP_BOX_X_MIN: float = 83.5` usato per classificazione reale (N2 outcome / "Inside box"), mentre lo stesso file definisce `BOX_X: float = 83.33` (riga 142) e `Z14_X_MAX: float = 83.33` (riga 53). Il commento in `src/styling/pitch_utils.py:55` conferma esplicitamente che 83.5 è un "valore precedente" da correggere. Drift tra due soglie nello stesso modulo. | **ALTA** |
| 5 | Analitica — soglia area di rigore (visiva) | 9 file in `dash_app/src/components/*.py` e `dash_app/src/styling/pitch_utils.py:130` | Uso di `x0=83.5` per disegnare il rettangolo dell'area di rigore nei grafici Plotly (solo visivo, non analitico). Inconsistente con la costante canonica 83.33 usata altrove, ma non altera i calcoli. | **BASSA** |
| 6 | Deploy / dati | `.gitignore:36` (regola `data/`) | Qualsiasi nuovo file sotto `data/` (inclusi parquet rigenerati da un futuro run di precompute) verrà ignorato silenziosamente da git (confermato con `git check-ignore`). I 122 parquet attuali sono tracciati solo perché aggiunti prima che questa regola esistesse. Rischio concreto: un futuro refresh dati non verrà deployato su Render senza `git add -f` esplicito. | **ALTA** |
| 7 | Deploy / dati | `data/ready/player_season_*_k_table.json` (5 file) | Gitignorati dalla regola `data/` + `*.json`. Non causano malfunzionamenti (sono un sidecar write-only per documentazione metodologica, mai riletti dal codice), ma sono assenti da un deploy git-based. | **BASSA** |
| 8 | Dipendenze mancanti in requirements.txt | `dash_app/src/analytics/possession_value.py:762`, `dash_app/src/utils/pv_model.py:116-117` | `lightgbm` importato in modo lazy (dentro funzione) nel percorso attivo `src/`; non presente in `requirements.txt`. Import lazy quindi non blocca l'avvio, ma il modello di training LightGBM non è disponibile senza installazione manuale. | **BASSA** |
| 9 | Dipendenze mancanti in requirements.txt | `dash_app/src/models/train_pv_model.py:34`, `dash_app/src/models/generate_pv_heatmap.py:25` | `matplotlib` richiesto da due script offline (non importati dall'app runtime — falliscono solo se eseguiti direttamente). Import verificato con `python -c "import ..."`: `ModuleNotFoundError: No module named 'matplotlib'`. | **BASSA** |
| 10 | Codice morto isolato | `dash_app/_unused/**` (17 file: analytics, callbacks, registry, reporting, scripts, tabs) | Cluster confermato completamente isolato: nessun riferimento a `_unused`, `ArtifactRegistry`, `manifest_schema`, o `filters_callbacks` nel codice attivo al di fuori di `_unused/` stesso. Sicuro da rimuovere. | **BASSA** (info) |
| 11 | Documentazione | `docs/methodology/_archive/POSSESSION_VALUE_DESIGN.md`, `docs/methodology/_archive/MEAN_AGE_KPI_IMPLEMENTATION.md` | Riferimenti a file rimossi (`src/analytics/pv_model.py`, `src/callbacks/tabs_callbacks.py`) — entrambi nella cartella `_archive/`, quindi attesi come storici. | **BASSA** |
| 12 | Manutenibilità | 13 file >1000 righe (`set_piece_cards.py` 1969, `opponent_offensive_phase.py` 1945, `precompute_serie_a.py` 1736, `analysis_callbacks.py` 1689, `chance_creation.py` 1544, `team_detail_callbacks.py` 1512, `possession_value.py` 1406, `final_third.py` 1351, `chance_creation_cards.py` 1218, `opp_season_chances_conceded_cards.py` 1170, `defensive_structure.py` 1104, `final_third_cards.py` 1071, `opp_season_pressing_cards.py` 1051) | Candidati a refactoring/splitting per leggibilità e manutenibilità futura. Nessun impatto funzionale accertato. | **BASSA** |
| 13 | Data loader — fallback CSV | `dash_app/src/analytics/data_loader.py:559` | `_load_avg_age_csv()` legge un CSV esterno (`data/external/avg_age_serie_a.csv`, età media da Transfermarkt) direttamente, con `@lru_cache`. Non è un accesso a CSV grezzo Opta né avviene dentro un callback — è un'eccezione dichiarata e cachata, non una violazione dell'architettura precompute. | **BASSA** (nessuna azione richiesta) |

---

## 3. Stato delle decisioni analitiche "locked"

| Decisione | Stato | Note |
|---|---|---|
| `PENALTY_XG = 0.79` | ✅ | Confermato in `dash_app/src/analytics/xg.py:88`, usato correttamente in `compute_xg_for_shot()` (single-row, riga 606) e `compute_batch_xg()` (riga 650). |
| Coordinata area di rigore = 83.33 | ❌ (parziale) | Valore corretto (83.33) è il canonico e maggioritario nel codice, ma **83.5 sopravvive come soglia analitica reale** in `defensive_structure.py:104` (`OPP_BOX_X_MIN`) e come costante di disegno in 9 file di componenti UI. Vedi problema #4/#5. |
| Own goal → xG = 0.0 | ✅ | Confermato in `xg.py` (righe 608-609 single-row, righe 653-654 batch) e verificato indipendentemente dal test `test_own_goal_xg_is_zero` (PASSED). |
| "Own Goal" come attack origin in Chance Creation | ✅ | Implementato in modo maturo in `chance_creation.py` (righe ~1128-1273): righe di autogol identificate sul lato avversario (`"own goal"=="Si"`), coordinate ribaltate, credit alla squadra giusta, esplicitamente bypassando `classify_attack_origin()` (commento riga 1252). Confermato da 3 test dedicati tutti PASSED (`test_own_goal_credited_to_analysed_team`, `test_own_goal_not_present_gives_zero_own_goals`, `test_own_goal_not_in_regular_origin_matrix`). Questo risolve il "known open fix" segnalato nel brief. |
| PPDA — due definizioni distinte e non confuse | ✅ | **Team Overview** (`dash_app/src/analytics/ppda.py::compute_ppda()`, riga 171): denominatore = `ball_recoveries`. **Match/Opponent Analysis** (`dash_app/src/analytics/defensive_pressing.py::compute_ppda()`, riga 209): denominatore = `PPDA_ACTION_IDS = {4,7,8,45}` (tackle, intercettazione, fallo, challenge — commento esplicito "industry-standard 4-type set: StatsBomb/Wyscout/Opta"). Le due implementazioni sono correttamente separate, nessuna confusione riscontrata. |
| Aggregati stagionali = somma di numeratori/denominatori grezzi (non media di rate per partita) | ✅ | Verificato in `ppda.py::compute_ppda()` (somma eventi su tutta la stagione via `groupby().size()`, poi un'unica divisione finale) e in `season_player_analysis.py::aggregate_team_season()` (accumulatori incrementati per-match: `minutes[name] += m`, `counts`/`pva_sum` come dict accumulatori). |
| Bug `_is_set_piece_event()` — filtro squadra mancante | ✅ **RISOLTO** | La funzione (righe 311-349) ora accetta un parametro `attacking_team` esplicitamente documentato come fix per un forensic finding reale (GW13 min 68, GW17 min 64, GW19 min 97, Inter 2025/26). Entrambi i call site (`_check_set_piece`, righe 429-430 e 488) passano correttamente `attacking_team` derivato da `shot_row["team_name"]`. Il filtro sulla possessione precedente (`prev_is_attacker`, righe 462-467) è indipendentemente corretto. Coerente con le modifiche non committate presenti in git status — sembra il lavoro in corso interrotto dall'utente. |

---

## 4. Codice morto e file orfani

- **Cluster `dash_app/_unused/`** (17 file: `analytics/multi_season_standings_v1.py`, `callbacks/filters_callbacks.py`, `callbacks/tabs_callbacks.py`, `components/tables.py`, `registry/{__init__,loaders,manifest_schema,registry}.py`, `reporting/__init__.py`, `scripts/{_debug_cols,_debug_fk}.py`, `tabs/{__init__,home,match_report,player_analysis,settings,team_season}.py`) — confermato **totalmente isolato**. Zero riferimenti da codice attivo a `_unused`, `ArtifactRegistry`, `manifest_schema`, o `filters_callbacks`. Sicuro da eliminare in un secondo momento.
- **Nessun file orfano rilevato in `dash_app/src/`** — ogni modulo attivo è referenziato da almeno un altro file (verifica grep per basename su tutto `src/` + `app.py`).
- **Due script offline non collegati al runtime dell'app**: `dash_app/src/models/train_pv_model.py` e `dash_app/src/models/generate_pv_heatmap.py` — fallirebbero all'esecuzione diretta per `matplotlib` mancante, ma non sono importati da `app.py` o da alcun modulo attivo.
- **`dash_app/scripts/`** (`generate_demo_artifacts.py`, `scrape_avg_age.py`, `validate_general_buildup.py`) — script di utilità/precompute standalone, non parte del percorso di avvio dell'app; non verificati per obsolescenza in questo audit (fuori scope, nessun problema rilevato tramite grep).
- **`dash-improvements` branch**: confermato **completamente merged e stale** — 0 commit ahead di main, 12 commit behind. Il diff --stat mostra solo rinominazioni di path storiche (`_unused` → `src` reshuffle) già presenti su main. Nessuna azione richiesta; candidato sicuro per l'eliminazione del branch.

---

## 5. Piano d'azione prioritario (proposta — NESSUNA implementazione eseguita)

### Modifiche sicure / additive (non toccano funzioni o schemi esistenti)
1. Installare `scikit-learn==1.7.2` (pin da requirements.txt) in almeno UNO dei due venv per ripristinare il modulo Possession Value; decidere quale dei due venv (`.venv/` root o `dash_app/.venv/`) è quello "ufficiale" e considerare di rimuovere l'altro per evitare ambiguità futura.
2. Aggiungere `lightgbm` e `matplotlib` a `requirements.txt` (anche solo come dipendenze opzionali/commentate) per documentare la superficie reale di import, coerentemente con il pattern già usato per `scikit-learn`.
3. Rimuovere la cartella `dash_app/_unused/` (17 file, confermata isolata) — puramente additivo/sottrattivo, zero rischio funzionale.
4. Eliminare il branch `dash-improvements` (confermato fully-merged, stale).
5. Investigare la regola `data/` in `.gitignore` (riga 36): aggiungere un'eccezione esplicita `!data/ready/*.parquet` e `!data/processed/*.parquet` (o rimuovere la regola generica `data/` mantenendo solo `*.csv`/`*.db`/ecc.) per evitare che un futuro refresh dati venga silenziosamente escluso da git.
6. Isolare/velocizzare `TestPossessionValueModelBuild::test_build_completes` (e le 2 classi sorelle) in `test_chance_creation.py` passando esplicitamente un `raw_dir` inesistente o vuoto quando si usano DataFrame sintetici, così da forzare il fallback invece di scandire `RAW_DATA_DIR` reale. Questo è un fix di test, non tocca `possession_value.py` in produzione.

### Modifiche che toccano funzioni/schemi esistenti (richiedono revisione più attenta)
7. Allineare `OPP_BOX_X_MIN` in `defensive_structure.py:104` da 83.5 a 83.33 — impatta la classificazione N2 "Inside box" nella Defensive Structure analytics; **verificare prima l'impatto su eventuali dati/report già pubblicati con la soglia 83.5** prima di cambiare, poiché altera l'output analitico storico.
8. Allineare le 9 occorrenze di `x0=83.5` nei componenti UI (solo disegno rettangolo) a 83.33 per coerenza visiva col resto del sistema — impatto puramente cosmetico ma tocca molti file components/*.
9. Rivedere e chiudere le modifiche non committate già in corso su `chance_creation.py`, `chance_creation_cards.py`, `test_chance_creation.py` (il fix del filtro squadra in `_is_set_piece_event()` sembra completo e testato — valutare se è pronto per il commit).
10. Aggiornare i pin di `requirements.txt` o riallineare gli ambienti locali (dash 4.0.0→4.1.0, pandas 3.0.1→2.3.3, pyarrow 23.0.1→22.0.0) per garantire riproducibilità reale, non solo dichiarata.

---

## Fase 1 — Stato

Eseguita il 2026-09-30 a partire dal tag `pre-phase1-cleanup-2026-09-30`. Implementati solo i punti 1–6 della sezione "Modifiche sicure / additive"; punti 7–10 non toccati, come richiesto.

| # | Intervento | Stato | Note |
|---|------------|-------|------|
| — | Commit modifiche pre-esistenti (own-goal credit) | ✅ | Le modifiche non committate implementavano il credito dei gol nella propria porta all'avversario, non il fix del filtro squadra in `_is_set_piece_event()` (quel fix risultava già presente nel codice base). Committate con messaggio accurato dopo verifica dei 60 test non-PV: `feat(chance-creation): credit opponent own goals to analysed team`. |
| 1 | scikit-learn 1.7.2 + scelta venv | ✅ | Installato in `dash_app/.venv/` (scelto perché unico dei due con pytest/pytest-timeout già installati e funzionante; `.venv/` root rimosso). Diff di `pip freeze` conferma solo 5 nuovi package (scikit-learn, scipy, joblib, threadpoolctl, cloudpickle) — nessuna modifica a pandas/numpy/dash/pyarrow/plotly. `import sklearn` OK (1.7.2), `PossessionValueModel.get_instance().loaded == True`. |
| 2 | `lightgbm` + `matplotlib` in requirements.txt | ✅ | Aggiunti come dipendenze opzionali commentate (pattern coerente con scikit-learn), pin locali lightgbm==4.7.0 e matplotlib==3.11.2. Verificato: `train_pv_model.py` e `generate_pv_heatmap.py` ora si importano senza `ModuleNotFoundError`. |
| 3 | Rimozione `dash_app/_unused/` | ✅ | Grep di conferma su tutto il repo (`_unused`, `ArtifactRegistry`, `manifest_schema`, `filters_callbacks`) — zero riferimenti fuori dal cluster stesso. Rimossi 17 file + README. App verificata funzionante dopo la rimozione (import `app.py` OK, cache warm-up 5 stagioni OK). |
| 4 | Branch `dash-improvements` | ✅ | `git log main..dash-improvements` vuoto, nessun branch remoto omonimo. Eliminato con `git branch -d` (merge pulito, nessun rifiuto). |
| 5 | `.gitignore` — regola `data/` | ✅ | Sostituita `data/` con `data/*` + eccezioni esplicite `!data/ready/`, `!data/ready/*.parquet`, `!data/processed/`, `!data/processed/*.parquet`. Verificato con `git check-ignore`: nuovo parquet ipotetico in `ready/`/`processed/` → non ignorato; CSV raw Opta in `data/raw/` → ancora ignorato; JSON `player_season_*_k_table.json` → ancora ignorato (voluto, punto 7). `git status` non mostra nuovi file indesiderati. |
| 6 | Fix test PV lenti | ✅ | `TestPossessionValueModelBuild` (3 test) ora passa `raw_dir=tmp_path` a `build()`, forzando l'uso dei soli DataFrame sintetici invece della scansione di `RAW_DATA_DIR` reale. Nessuna modifica a `possession_value.py` (il parametro `raw_dir` era già presente e opzionale). Tempo: 0.80s per le 3 classi (era >9 min CPU, mai completato). |

**Verifica finale:** suite completa `pytest -q` → **118/118 passati in 1.19s**. App avviata su porta 8050 (libera), cache warm-up completato per tutte le 5 stagioni (2021/22–2025/26), nessun errore sklearn nei log; app arrestata correttamente al termine del test. `git diff --stat pre-phase1-cleanup-2026-09-30 -- dash_app/src/` → vuoto (nessun file di produzione toccato). Nessun push eseguito.

---

## Fase 2a — Dipendenze

Eseguita il 2026-09-30 a partire dal tag `pre-phase2a-deps-2026-09-30`, in risposta al punto 10 sopra (disallineamento pacchetti tra locale, test e Render).

### Situazione iniziale
- Locale (`dash_app/.venv/`, Python 3.13.5): dash 4.0.0, pandas 3.0.1, numpy 2.4.2, pyarrow 23.0.1, plotly 6.5.2.
- `dash_app/requirements.txt` (usato da Render): dash 4.1.0, pandas 2.3.3, numpy 2.3.5, pyarrow 22.0.0, plotly 6.5.0.
- Divergenza Python a 3 vie: `dash_app/.venv/` locale 3.13.5, `runtime.txt` (root) 3.11.9, `render.yaml` → `PYTHON_VERSION` 3.14.0, `dash_app/.python-version` 3.14. Nota di correzione dell'utente: la dicitura "validato su Render da tempo" nella prima stesura di questo report era inesatta — il deploy Render non aveva mai mostrato dati correttamente; la scelta della direzione dei pin non si basa quindi sullo storico di produzione ma sull'evidenza raccolta in Fase 0–1 (test, warning, confronto numerico).

### Fase 0–1 — Evidenza raccolta
- Nessun pattern di codice a rischio rilevante in `src/`: 1 `inplace=True` innocuo (rename su DataFrame locale), 1 controllo `dtype == object` in uno script offline mai importato a runtime; nessun vero chained-assignment, nessuna API deprecata (`fillna(method=...)`, `applymap`, frequenze `"H"`/`"T"`).
- Parquet: stesso numero di righe su tutte le 5 stagioni leggendo con pyarrow 22/pandas 2.3.3 e con pyarrow 23/pandas 3.0.1; unica differenza il dtype colonne stringa (`object` vs `str`, atteso).
- Test: 118/118 passati in entrambe le direzioni. Con pandas 2.3.3 compaiono 2 `FutureWarning` su `pd.concat` con entry NA in `test_chance_creation.py` (righe 1146, 1200) — assenti con pandas 3.0.1 perché lì il comportamento è già quello futuro di default. **Non corretti in questa fase — segnati come follow-up per un futuro passaggio a pandas 3.**
- Smoke test app: avvio pulito e cache 5 stagioni scaldata in entrambe le direzioni. Con pandas 3.0.1 compaiono inoltre 2 `PerformanceWarning: DataFrame is highly fragmented` (`defensive_structure.py:1033`, `final_third.py:1273`) — solo rumore di performance, nessun impatto sui risultati.
- Confronto numerico (Bologna–Roma, giornata 34, 2025/26 — ultima con CSV raw reale disponibile): output di Chance Creation (N tiri, xG totale, matrice origini), PPDA e Defensive Structure **identici byte-per-byte** tra le due direzioni.

### Decisione
**Opzione A — riportare il locale ai pin di `requirements.txt`** (confermata dall'utente). Motivazione: test, warning e output numerici sono equivalenti tra le due opzioni, quindi la scelta non è guidata dalla correttezza; riallineare il locale ai pin esistenti richiede meno superficie di cambiamento rispetto a validare per la prima volta pandas 3.0.1/pyarrow 23 in produzione.

### Allineamento Python
- `dash_app/.venv/` (versione su cui erano stati validati i 118 test): **Python 3.13.5**.
- Verificato che tutti i pin di `requirements.txt` (inclusi gli opzionali `lightgbm==4.7.0` e `matplotlib==3.11.2`) hanno wheel disponibili sia per Python 3.13 sia per 3.14 (nessun blocco tecnico in nessuna delle due direzioni).
- Scelta: allineare Render a 3.13.5 (non il locale a 3.14), poiché i 118 test hanno evidenza reale già raccolta proprio su 3.13.5.
- Modifiche: `render.yaml` → `PYTHON_VERSION: 3.13.5`; `dash_app/.python-version` → `3.13.5` (versione completa, per evitare ambiguità di patch); `runtime.txt` (root, stale, non letto da Render in questo setup) rimosso.
- Altri riferimenti cercati nel repo (README, Dockerfile, CI/workflow, script): nessun Dockerfile né workflow CI trovati; `README.md:57,136` dichiara solo "Python 3.10+" (requisito minimo generico, resta valido, nessuna modifica necessaria); aggiornato il commento stale in `dash_app/requirements.txt:28` ("validated working under both Python 3.11 and 3.14" → "validated working under Python 3.13").

### Implementazione
- `dash_app/.venv/` riallineato con `pip install -r dash_app/requirements.txt`. Diff `pip freeze` prima/dopo: `dash` 4.0.0→4.1.0, `numpy` 2.4.2→2.3.5, `pandas` 3.0.1→2.3.3, `plotly` 6.5.2→6.5.0, `pyarrow` 23.0.1→22.0.0, più `gunicorn` 23.0.0 (pinnato ma non ancora installato in locale) e le dipendenze transitive `pytz`/`tzdata` di pandas 2.3.3. Nessun altro pacchetto toccato.
- `pytest -q` nel venv riallineato (Python 3.13.5 + pin Opzione A): **118/118 passati**, stessi 2 `FutureWarning` già noti.
- Smoke test app nello stesso venv: avvio pulito su porta 8050, cache warm-up completo per le 5 stagioni, nessun errore né warning nuovo nei log; app arrestata correttamente.
- Venv temporanei di prova (`/tmp/venv-pins`, `/tmp/venv-latest`, `/tmp/venv-pyarrow22`, `/tmp/venv-pyarrow23`, `/tmp/venv-py313-check`, `/tmp/venv-py314-check`) cancellati al termine.

### Verifica finale
- `pip freeze` di `dash_app/.venv/` coincide con i pin di `requirements.txt` per tutti i pacchetti dichiarati (verificato via diff mirato).
- `pytest -q` → 118/118 verdi nel venv riallineato.
- App avviata e arrestata, nessun errore sklearn né warning pandas nuovi.
- `git diff --stat pre-phase2a-deps-2026-09-30 -- dash_app/src/` → vuoto.
- Nessun push eseguito.

### Follow-up aperti
- I 2 `FutureWarning` su `pd.concat` con entry NA in `test_chance_creation.py` (righe 1146, 1200) restano da correggere in un futuro passaggio a pandas 3.
- I 2 `PerformanceWarning: DataFrame is highly fragmented` osservati sotto pandas 3.0.1 (`defensive_structure.py:1033`, `final_third.py:1273`) sono solo rilevanti se/quando si deciderà di migrare a pandas 3.

---

## Fase 2b — Bordo area (visivo)

Eseguita il 2026-09-30 a partire dal tag `pre-phase2b-box-visual-2026-09-30`, in risposta al punto 8 sopra (bordo area disegnato a 83.5 invece del valore canonico Opta-normalizzato 83.33 usato dallo strato analitico).

### Inventario e classificazione
- `grep -rn "83\.5" dash_app/src/`: 8 occorrenze DISEGNO (`fig.add_shape(type="rect", ...)` in 7 file `components/` + `pitch_utils.py:130`), 1 ALTRO (commento in `pitch_utils.py:55`, già descrive la correzione), 1 ANALITICA fuori scope (`defensive_structure.py:104`, `OPP_BOX_X_MIN`, non toccata).
- Area speculare: ogni punto con `x0=83.5` aveva anche il rettangolo sinistro a `x0=0, x1=16.5` nello stesso file — sostituito con `16.67` per coerenza (100 − 83.33), come da conferma.
- Durante l'implementazione sono emerse 2 occorrenze aggiuntive di `16.5` non catturate dal grep iniziale (limitato a `83.5`): `final_third_cards.py:347` (`pa_w = 16.5`, larghezza box su un pitch con `PW=100.0`, stesso sistema di coordinate) e `chance_conceded_cards.py:505` (dentro `_draw_defensive_half()`, box sinistro con `y0=21.1/y1=78.9` già canonici ma `x1=16.5` non allineato). Entrambe corrette per coerenza; il lato destro di `final_third_cards.py` usa la formula `PW-pa_w`, quindi si è auto-corretto.
- Costante canonica: `pitch_utils.py` definisce già `_PENALTY_BOX_X0=83.33`/`_OWN_BOX_X1=16.67` (righe 59-64), ma sono private al modulo e usate solo da `draw_pitch()`; nessun componente le importava. Scelta implementativa confermata: (a) sostituzione diretta del letterale, non (b) import della costante — evita di rendere pubblica un'API privata per un fix puramente visivo.

### File modificati (commit `cd3b775`, `style(pitch): align penalty box drawing to canonical 83.33`)
1. `dash_app/src/components/chance_conceded_cards.py` — commento coordinate + 2 shape (`_section_origin_grid`, `_draw_defensive_half`)
2. `dash_app/src/components/chance_creation_cards.py` — 2 shape (`_section_origin_grid`)
3. `dash_app/src/components/final_third_cards.py` — `pa_w` in `_possession_pitch_figure`
4. `dash_app/src/components/opp_season_chances_conceded_cards.py` — 2 shape (`_build_zone_pitch`)
5. `dash_app/src/components/opponent_offensive_phase.py` — 6 shape (`_build_gk_zone_pitch`, `_build_ft_zone_pitch`, `build_cc_section`)
6. `dash_app/src/components/pitch_zones.py` — 2 shape (`pitch_zone_figure`)
7. `dash_app/src/styling/pitch_utils.py` — 2 shape (`_draw_formation_markings`)

### Verifica
- `grep -rn "83\.5" dash_app/src/` → solo il commento `pitch_utils.py:55` e `defensive_structure.py:104` (ANALITICA, intatta), come atteso.
- `git diff --stat pre-phase2b-box-visual-2026-09-30 -- dash_app/src/analytics/` → vuoto.
- `pytest -q` → 118/118 verdi (stessi 2 `FutureWarning` già noti, nessun nuovo warning).
- Verifica figure reali: generate `chance_creation_card()` e `chance_conceded_card()` con l'output di `analyse_chance_creation()`/`analyse_chance_conceded()` su Bologna–Roma (giornata 34, 2025/26, ultima con CSV raw reale), più `pitch_zones.pitch_zone_figure()` e `pitch_utils.draw_pitch(style="formation")` invocate direttamente. In tutte le figure ispezionate, i rettangoli area risultano `x0=83.33`/`x1=16.67` (nessun `83.5`/`16.5` residuo); numero di shape e tracce coerente con l'atteso per ciascun grafico (nessuna shape aggiunta/rimossa dalla modifica).
- Smoke test app: avvio pulito su porta 8050, cache 5 stagioni scaldata, nessun errore/warning nuovo; arrestata correttamente.
- Nessun push eseguito.

---

## Fase 2c — Soglia area analitica

Eseguita il 2026-09-30 a partire dal tag `pre-phase2c-box-threshold-2026-09-30`, in risposta al punto 7 sopra (`OPP_BOX_X_MIN = 83.5` in `defensive_structure.py:104`, presunta soglia analitica per la classificazione N2 "Inside box").

### Falso positivo: la soglia 83.5 era codice morto
L'analisi d'impatto in Fase 0 ha rivelato che `OPP_BOX_X_MIN` **non è mai stata letta da nessuna logica di classificazione** — è comparsa solo nella propria definizione e in un commento a blocco che la descriveva come se fosse usata. La classificazione reale N2/N3 "Inside box" (righe 552-557, 583-591) usa da sempre `BOX_X = 83.33` (già canonico, definito alla riga 142) insieme a `OPP_BOX_Y_MIN`/`OPP_BOX_Y_MAX`.

Verifica empirica: ricaricando il modulo con `OPP_BOX_X_MIN=83.5` vs `83.33` e ricalcolando `analyse_defensive_structure()` su tutte le 38 partite di Bologna 2025/26 disponibili, la `outcome_distribution` (N1/N2/N3) è risultata **identica in ogni singola partita** — zero eventi riclassificati, coerentemente con l'assenza di uso della costante. **Il punto 7 del sanity check era quindi un falso positivo: la soglia 83.5 non ha mai influenzato alcun output analitico della dashboard.**

### Modifica applicata (non l'opzione (a) inizialmente proposta)
Anziché riassegnare `OPP_BOX_X_MIN = BOX_X` (opzione (a) proposta al checkpoint), su indicazione esplicita è stata **rimossa la definizione della costante orfana**:
- `OPP_BOX_X_MIN: float = 83.5` (riga 104) eliminata.
- Commento a blocco (riga 98) aggiornato per descrivere la regola realmente applicata: `"Inside box : Team B raw x ≥ BOX_X AND y ∈ [OPP_BOX_Y_MIN, OPP_BOX_Y_MAX]"`.
- `OPP_CENTRAL_X_MIN` (66.67) e `OPP_DEEP_ATT_X_MIN` (75.0) **non toccate** — sono anch'esse costanti orfane (documentate nello stesso blocco di commento ma mai referenziate nella logica), segnalate qui come follow-up eventuale ma fuori scope per questa fase.

### File toccati (commit `d7a4219`)
- `dash_app/src/analytics/defensive_structure.py` — unica modifica di produzione (rimozione costante + aggiornamento commento).
- `dash_app/tests/test_defensive_structure_box_threshold.py` — nuovo file di test (nessun test esistente modificato).

### Nuovo test
Costruito un fixture minimale a due eventi (Dispossessed della squadra analizzata come trigger, seguito da un cross avversario nella finestra di transizione) che esercita realmente `compute_defensive_transitions()` — non un mock — per verificare il confine `BOX_X = 83.33`:
- `TestBoxThresholdConstant`: `BOX_X == 83.33`; `OPP_BOX_X_MIN` non più definita nel modulo.
- `TestInsideBoxClassificationBoundary`: cross con `Pass End X = 83.4` → outcome `N2` (Inside box); cross con `Pass End X = 83.3` → outcome ≠ `N2`.

### Verifica
- `grep -rn "83\.5" dash_app/src/` → nessuna occorrenza analitica residua (solo il commento storico in `pitch_utils.py:55`, invariato dalla Fase 2b).
- `git diff --stat pre-phase2c-box-threshold-2026-09-30 -- dash_app/src/` → solo `defensive_structure.py` (4 righe modificate).
- `pytest -q` → **122/122 verdi** (118 esistenti + 4 nuovi), stessi 2 `FutureWarning` già noti.
- Ricalcolo Bologna–Roma (giornata 34, 2025/26) dopo la modifica: `outcome_distribution = {'N1': 14, 'N2': 0, 'N3': 1}` — identico al valore misurato in Fase 0, confermando l'assenza di impatto.
- Nessun parquet rigenerato (non necessario: l'impatto misurato è strutturalmente zero).
- Smoke test app: avvio pulito su porta 8050, cache 5 stagioni scaldata, nessun errore/warning nuovo; arrestata correttamente.
- Nessun push eseguito.

### Follow-up aperto
- `OPP_CENTRAL_X_MIN` e `OPP_DEEP_ATT_X_MIN` in `defensive_structure.py` restano costanti orfane (documentate ma mai lette) — da valutare in un futuro giro di pulizia se si vuole rimuovere anche queste o effettivamente cablarle nella logica.
