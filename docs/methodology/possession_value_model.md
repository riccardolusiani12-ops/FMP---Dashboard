# Possession Value Model — Metodologia

> **Versione**: 2.0 ML (sostituisce xT grid v1.x)  
> **Data**: Aprile 2026  
> **File modello**: `dash_app/src/models/pv_model_serie_a.pkl`  
> **Utility**: `dash_app/src/utils/pv_model.py`  
> **Integrazione**: `dash_app/src/analytics/chance_creation.py`  
> **Training**: `dash_app/src/models/train_pv_model.py`

---

## Indice

1. [Scopo e Contesto](#1-scopo-e-contesto)
2. [Architettura del Modello](#2-architettura-del-modello)
3. [Dati di Training](#3-dati-di-training)
4. [Integrazione nel Dashboard](#4-integrazione-nel-dashboard)
5. [Interpretazione](#5-interpretazione)
6. [Limitazioni](#6-limitazioni)

---
## 1. Scopo e Contesto

### 1.1 Cos'è il Possession Value

Il **Possession Value** (PV) misura la probabilità che una possesso in corso si concluda con un gol, condizionatamente allo **stato attuale del gioco**:

$$PV(s_t) = P(\text{goal} \mid \text{stato del gioco al tempo } t)$$

dove "stato" include la posizione della palla, il tipo di azione, la geometria rispetto alla porta e il contesto della possesso (quante azioni sono già avvenute, quanto si è già penetrato verso la porta avversaria).

### 1.2 PV vs xT: la differenza fondamentale

| Caratteristica | xT (Expected Threat) | PV (Possession Value) |
|---|---|---|
| **Cosa misura** | Valore di una **zona** del campo | Valore di uno **stato** (zona + azione + contesto) |
| **Granularità** | Discreta (16×12 = 192 celle) | Continua (feature vector a 24 dimensioni) |
| **Input** | Solo (x, y) | (x, y, type_id, outcome, possesso context, ...) |
| **Inferenza** | Lookup in array numpy | Predict con modello ML |
| **Sensibilità** | No: due azioni nella stessa zona hanno identico xT | Sì: un passaggio e un dribbling nella stessa posizione producono PV diversi |

**Il vecchio modello** (`pv_model_serie_a.pkl` v1.x) era una griglia 16×12 di frequenze empiriche. Ogni cella conteneva P(goal | possesso in quella zona), calcolata su 8.6M eventi. Era efficace come baseline ma ignorava tipo di azione, direzione del gioco, profondità della possesso.

**Il nuovo modello** è un classificatore supervisionato che stima P(goal | game_state) con un vettore di 24 feature, addestrato con split temporale per stagione.

### 1.3 Possession Value Added (PVA)

Il **PVA** di un'azione è la variazione di P(goal) che produce:

$$\text{PVA}(t) = PV(s_t) - PV(s_{t-1})$$

- **PVA > 0**: l'azione ha aumentato la pericolosità (es. filtrante dentro l'area)
- **PVA < 0**: l'azione ha diminuito la pericolosità (es. retropassaggio sotto pressione)
- **PVA ≈ 0**: l'azione non ha modificato significativamente P(goal)

Questo è esattamente il framework usato da **Opta/Stats Perform** e **SciSports** nei loro prodotti proprietari di action valuation.

### 1.4 Perché PV è superiore all'approccio precedente

Il vecchio `chance_creation.py` usava `pv_model.get_xT(x, y)` — un lookup nella griglia 16×12. Era di fatto un **xGOT approssimato**: una stima della pericolosità della zona del tiro, non del valore della catena che lo ha prodotto.

Il nuovo PV:
1. **Valuta la catena**, non solo la posizione finale: usa il delta dall'entrata nel terzo offensivo al tiro
2. **Incorpora il tipo di azione**: cross vs passaggio filtrante vs tocco nella stessa zona → PV diversi
3. **Considera il contesto della possesso**: un'azione all'8° tocco di una possesso elaborata è diversa da un contropiede diretto
4. **È coerente con xG**: entrambi stimano probabilità di gol, permettendo confronti diretti nella Chain-to-Goal Matrix

---

## 2. Architettura del Modello

### 2.1 Approccio concettuale

Il modello è un **classificatore binario** che per ogni evento risponde alla domanda:

> *Data la posizione attuale della palla e il contesto del gioco, qual è la probabilità che questa possesso si concluda con un gol?*

**Perché `ends_in_goal` e non `ends_in_shot`?**

Con `ends_in_shot` il modello stimerebbe P(tiro), non P(gol). Usando `ends_in_goal`:
- Il modello è **coerente con xG**: entrambi stimano probabilità di gol
- Il PV sum è **direttamente comparabile con xG sum** nella Chain-to-Goal Matrix
- Un tiro da 50 metri e una palla a botta sicura hanno PV molto diversi, come devono

**Output**: P(goal) ∈ [0, 1] — una probabilità calibrata, non uno score relativo.

### 2.2 Feature Engineering

#### Features Spaziali

| Feature | Formula | Motivazione |
|---|---|---|
| `x` | Coordinata Opta (0→100) | Posizione longitudinale |
| `y` | Coordinata Opta (0→100) | Posizione laterale |
| `x²` | `x ** 2` | Non-linearità: pericolosità accelera nell'area di rigore |
| `y²` | `y ** 2` | Simmetria: ali meno pericolose del centro |
| `xy` | `x * y` | Interazione: posizione centrale avanzata = molto pericolosa |
| `dist_to_goal` | √((100−x)² + (50−y)²) | Distanza euclidea dalla porta avversaria |
| `angle_to_goal` | arctan(7.32·(100−x) / ((100−x)² + (y−50)² − 3.66²)) in gradi | Angolo subteso dai pali |
| `in_box` | 1 se x≥83.33 ∧ 21.1≤y≤78.9 | Flag: dentro l'area di rigore |
| `in_final_third` | 1 se x≥66.67 | Flag: terzo offensivo |
| `central_corridor` | 1 se 33.3≤y≤66.7 | Flag: corridoio centrale |
| `dist_to_center_y` | \|y − 50\| | Distanza dalla mezzeria laterale |

**Ruolo dei termini quadratici**: la pericolosità non cresce linearmente con x. Da centrocampo a 30m dalla porta la crescita è graduale; dentro l'area esplode. I termini x², y², xy permettono a Logistic Regression di catturare questa non-linearità senza trasformazioni aggiuntive.

#### Features Evento

| Feature | Fonte/Formula | Motivazione |
|---|---|---|
| `type_id` | Opta typeId numerico | Tipo dell'azione |
| `outcome` | 0=fallito, 1=riuscito | Un passaggio fallito ha PV diverso da uno riuscito |
| `is_pass` | type_id == 1 | Flag: passaggio |
| `is_carry_touch` | type_id == 44 | Flag: tocco/conduzione |
| `is_recovery` | type_id == 49 | Flag: recupero palla |
| `is_tackle` | type_id == 7 | Flag: tackle |
| `is_interception` | type_id == 8 | Flag: intercetto |
| `through_ball` | Qualifier Opta | Passaggio filtrante |
| `cross` | Qualifier Opta | Cross |
| `head` | Qualifier Opta | Colpo di testa |
| `aerial` | Qualifier Opta | Duello aereo |

#### Features Possesso

| Feature | Formula | Motivazione |
|---|---|---|
| `poss_event_index` | `df.groupby('poss_id').cumcount()` | Posizione nella possesso (0=primo evento). Un'azione al 1° tocco dopo recupero è molto diversa dalla stessa posizione al 12° tocco |
| `x_max_in_poss_so_far` | `groupby('poss_id')['x'].cummax()` | Massima profondità raggiunta nella possesso fino a questo punto — proxy della traiettoria dell'azione |

`poss_event_index` cattura la **maturità della possesso**: un recupero alto che porta direttamente al tiro (index=1) è molto più pericoloso della stessa zona raggiunta dopo 15 tocchi.

`x_max_in_poss_so_far` è un **proxy della profondità**: se la squadra è già entrata a x=90 e poi ha riportato la palla a x=75, il modello sa che siamo in una fase avanzata dell'attacco, più pericolosa di un'azione che parte da x=75.

### 2.3 Dataset di Training

| Parametro | Valore |
|---|---|
| Fonte | Dati evento Opta, Serie A |
| Stagioni | 2008-2009 → 2025-2026 |
| Righe nel training set | 8,652,634 eventi |
| Possessioni | 3,266,254 |
| Tiri esclusi | Sì |
| `ends_in_goal` positivi | ~0.52% |

**Split temporale** — mai random su dati temporali:

| Split | Stagioni | Motivazione |
|---|---|---|
| Train | 2008-2009 → 2021-2022 | 14 stagioni di storia |
| Validation | 2022-2023, 2023-2024 | Tuning e early stopping |
| Test | 2024-2025 | Valutazione out-of-sample finale |
| Escluso | 2025-2026 | Stagione in corso — no data leakage |

Uno split random miscelerebbe eventi di stagioni diverse nello stesso fold — il modello vedrebbe eventi "futuri" rispetto al validation set (data leakage temporale).

**Gestione sbilanciamento** (ends_in_goal = 0.52%):
- **XGBoost**: `scale_pos_weight = n_negativi / n_positivi ≈ 192`
- **Logistic Regression**: `class_weight='balanced'`

### 2.4 Modelli Addestrati

#### MODEL A — Logistic Regression

```python
scaler = StandardScaler()   # fit solo su train, transform su val/test
model  = LogisticRegression(C=1.0, max_iter=1000,
                             solver='lbfgs',
                             class_weight='balanced',
                             n_jobs=-1)
```

**Pregi**: interpretabile (i coefficienti mostrano il peso di ogni feature), velocissima a inferenza, ben calibrata out-of-the-box.
**Limiti**: cattura le non-linearità solo via i termini quadratici espliciti presenti nelle feature.

#### MODEL B — XGBoost

```python
model = xgb.XGBClassifier(
    n_estimators=500, max_depth=5,
    learning_rate=0.05, subsample=0.8,
    colsample_bytree=0.8,
    scale_pos_weight = n_neg / n_pos,
    eval_metric='aucpr',
    early_stopping_rounds=30,
    tree_method='hist',
)
```

**Pregi**: cattura automaticamente non-linearità e interazioni di ordine superiore; gestisce valori mancanti; robusto allo sbilanciamento.
**Limiti**: meno interpretabile; più lento a inferenza; rischio overfitting senza regolarizzazione adeguata.

#### Criteri di Selezione

Il modello vincente è scelto sul **ROC-AUC sul validation set**. Se la differenza è ≤ 0.002, si preferisce Logistic Regression (più leggera, più semplice, più veloce a deployare).

#### Metriche di Valutazione

| Metrica | Cosa misura | Perché usarla |
|---|---|---|
| **ROC-AUC** | Capacità discriminante complessiva | Standard; threshold-indipendente |
| **Average Precision (AP)** | Area sotto curva Precision-Recall | Più informativo su dataset sbilanciati: un modello che predice sempre 0 ha AP ≈ 0.005, molto peggio del naïve |
| **Brier Score** | Calibrazione probabilistica | Misura quanto le probabilità sono accurate. 0 = perfetto, 1 = peggio del caso |
| **F1 @ opt threshold** | Equilibrio precision/recall | Utile per interpretare il comportamento pratico |

**Perché ROC-AUC da solo non basta**: con 0.52% di positivi, un modello che dice sempre 0 ha ROC-AUC ≈ 0.5 ma AP ≈ 0.005. Un buon modello PV deve avere AP significativamente superiore al baseline naïve.

### 2.5 Calibrazione Probabilistica

La calibrazione è la corrispondenza tra probabilità predetta e frequenza osservata: se il modello assegna P=0.10 a 100 eventi, circa 10 dovrebbero effettivamente concludersi in gol.

Il **reliability diagram** ("calibration curve") mostra questo allineamento:
- Asse X: probabilità media predetta in ogni bin di percentile
- Asse Y: frazione di positivi osservati nello stesso bin
- Diagonale perfetta = calibrazione perfetta

Se la curva è sopra la diagonale il modello è sotto-fiducioso; se è sotto, è sovra-fiducioso.

**Isotonic calibration** (applicata se il Brier Score migliora >5%):

```python
from sklearn.calibration import CalibratedClassifierCV
calibrated = CalibratedClassifierCV(best_model, method='isotonic', cv='prefit')
calibrated.fit(X_val, y_val)
```

XGBoost con `scale_pos_weight` elevato tende ad essere leggermente sovra-fiducioso su dataset fortemente sbilanciati.

---

## 3. Dati di Training

### 3.1 Pipeline di Estrazione

```
JSON Opta (raw)  →  parse events + qualifiers  →  build_possessions()
    →  label possessioni (ends_in_shot, ends_in_goal)
    →  escludi tiri  →  feature engineering  →  parquet
```

File finale: `data/serie_a_pv_features.parquet` (8.6M righe, 24 feature + label)

### 3.2 Event Types Inclusi

| type_id | Evento |
|---|---|
| 1 | Pass |
| 2 | Offside Pass |
| 3 | Take On |
| 7 | Tackle |
| 8 | Interception |
| 12 | Clearance |
| 44 | Ball Touch / Carry |
| 49 | Ball Recovery |
| 61 | Aerial |
| 13, 14, 15, 16 | Tiri (esclusi dal training set) |

### 3.3 Qualifier Estratti

| qualifierId | Colonna | Tipo |
|---|---|---|
| 72 | `through_ball` | flag 0/1 |
| 2 | `cross` | flag 0/1 |
| 18 | `head` | flag 0/1 |
| 73 | `aerial` | flag 0/1 |
| 102 | `distance_to_goal` | float |
| 103 | `angle_to_goal` | float |
| 140 | `pass_end_x` | float |
| 141 | `pass_end_y` | float |

### 3.4 Definizione di Possesso

```python
# Cambio possesso quando si verifica almeno una delle seguenti condizioni:
team_change  = df['team_id'] != df['team_id'].shift(1)
time_gap     = df['_match_sec'].diff().abs() > 5.0   # secondi
match_change = df['match_id'] != df['match_id'].shift(1)

df['poss_id'] = (team_change | time_gap | match_change).cumsum()
```

### 3.5 Labelling

```python
# Per ogni poss_id:
# ends_in_shot = 1  se almeno un evento ha type_id in {13, 14, 15, 16}
# ends_in_goal = 1  se almeno un evento ha type_id == 16
#
# Il label viene assegnato a TUTTI gli eventi della possesso,
# non solo all'ultimo. Questo permette al modello di imparare
# che ogni azione della catena ha contribuito al goal.
```

**Perché escludere i tiri dal training set**: i tiri sono per definizione l'evento che genera la label `ends_in_shot=1`. Includerli introdurrebbe data leakage. Il modello PV deve valutare gli stati *prima* del tiro.

### 3.6 Dimensioni Finali

| Dato | Valore |
|---|---|
| Righe totali (no tiri) | 8,652,634 |
| Possessioni | 3,266,254 |
| `ends_in_goal` positivi | ~0.52% |
| Feature columns | 24 |
| Stagioni | 18 (2008-09 → 2025-26) |

---

## 4. Integrazione nel Dashboard

### 4.1 Classe `PossessionValueModel` (`dash_app/src/utils/pv_model.py`)

#### Pattern Singleton

```python
# Il modello è caricato in RAM una sola volta (primo import del modulo)
pv = PossessionValueModel.get_instance()

# Ogni chiamata successiva restituisce la stessa istanza
pv2 = PossessionValueModel.get_instance()
assert pv is pv2   # True — nessun reload del pkl
```

**Motivazione**: il modello ML (specialmente XGBoost) può occupare centinaia di MB in RAM. Caricarlo ad ogni request Dash sarebbe inaccettabile per le performance del dashboard.

#### Metodi Pubblici

```python
# P(goal) per una singola posizione + tipo azione
pv.score(x=85.0, y=50.0, type_id=1, outcome=1)
# -> float in [0, 1]

# PVA = P(goal | to) - P(goal | from)
pv.delta(x_from=70.0, y_from=50.0, x_to=85.0, y_to=50.0,
         type_id_from=1, type_id_to=16)
# -> float in [-1, 1]

# P(goal) per sequenza di eventi
events = [{"x": 70, "y": 50, "type_id": 1},
          {"x": 85, "y": 48, "type_id": 1}]
pv.score_sequence(events)
# -> [0.021, 0.043]

# PVA per ogni evento della sequenza
pv.pva_sequence(events)
# -> [0.021, 0.022]
# PVA[0] = score(events[0])    — valore assoluto del primo evento
# PVA[i] = score[i] - score[i-1]
```

#### Gestione Errori

- Input `None` o `NaN` → `return 0.0`
- Modello non caricato (file non trovato) → warning nel log, `return 0.0`
- Eccezione durante l'inferenza → `return 0.0` + log debug

#### Backward Compatibility

Il nuovo modello mantiene piena compatibilità con il codice che usava l'API del vecchio xT grid:

```python
pv.get_xT(x, y)               # -> pv.score(x, y, type_id=1)
pv.get_gpa(x, y)              # -> pv.get_xT(x, y)
pv.get_chain_pv_from_raw_events(df, ft_entry_time, shot_time)
# utilizzato da high_regains.py e altri moduli legacy
```

Se il pkl caricato è nel vecchio formato (contiene `xT_grid`), il modello usa automaticamente la griglia legacy emettendo un warning nel log.

### 4.2 Calcolo PV per ogni Tiro (`chance_creation.py`)

Il calcolo è nella funzione `_compute_shot_pv()` di `ChanceCreationAnalyzer`.
Il modulo usa un singleton `_pv = PossessionValueModel.get_instance()` a livello di modulo.

```python
# Logica di _compute_shot_pv:

# 1. Trova il primo evento non-tiro con x >= 66.67 (entrata nel FT)
ft_entry_row = primo evento con x >= 66.67 e type_id non in {13,14,15,16}

# 2a. Se trovato -> delta dall'entrata nel FT al tiro
if ft_entry_row:
    pv = _pv.delta(
        x_from=ft_entry_row['x'], y_from=ft_entry_row['y'],
        x_to=shot['x'],           y_to=shot['y'],
        type_id_from=ft_entry_row['type_id'],
        type_id_to=16   # Opta typeId per Goal
    )

# 2b. Possesso già in FT dall'inizio -> valore assoluto del tiro
else:
    pv = _pv.score(shot['x'], shot['y'], type_id=16)

# 3. Clamp a [-0.5, 0.5] per robustezza su dati sporchi
return max(-0.5, min(0.5, pv))
```

**Perché `type_id=16` per il tiro**: il modello usa `type_id` come feature. Usando 16 (Goal) per la valutazione del tiro, si indica al modello "da questa posizione si sta concludendo in porta" — differenziando il valore da un passaggio generico nella stessa zona.

### 4.3 Posizione nella Chain-to-Goal Matrix

La Chain-to-Goal Matrix aggrega i tiri di ogni partita per categoria di origine dell'azione.

**Aggregazione PV = SUM** (non mean), per tre motivi:
1. **Coerenza con xG**: xG è anch'esso sommato. Permette confronti diretti tra le due righe
2. **Volume account**: una categoria con più tiri accumula più PV totale, riflettendo sia quantità sia qualità
3. **Interpretabilità**: "questi High Regain hanno generato PV=0.18 totale" = "hanno spostato complessivamente P(goal) del 18%"

**Cosa significa la differenza PV vs xG**:

| | PV (sum) | xG (sum) |
|--|----------|----------|
| Misura | Pericolosità della **posizione** del tiro (dove) | Qualità della **chance** (quanto era probabile segnare) |
| Dipende da | x, y + tipo azione + possesso context | x, y + pressione + piede/testa + angolo |
| Lettura combinata | PV alto + xG alto = tiri in zone pericolose E di alta qualità | PV basso + xG alto = ottima chance da zona atipica |

---

## 5. Interpretazione

### 5.1 Come Leggere la Riga PV nella Chain-to-Goal Matrix

La riga PV mostra il **valore generato dal punto di entrata nel terzo offensivo fino al tiro**, sommato su tutti i tiri di quella categoria.

| Valore PV | Interpretazione |
|---|---|
| Alto positivo | Tiri in zone **molto più pericolose** del punto di entrata nel FT (es. recupero alto → tiro in area piccola) |
| Basso positivo | Tiri da zone leggermente più pericolose dell'entrata (es. build-up paziente che culmina con tiro da fuori area) |
| Negativo | Tiro da zona **meno pericolosa** dell'entrata nel FT (es. palla entrata in area → tiro forzato dall'ala) |

### 5.2 Esempio Concreto: Inter vs Bologna

Scenario con valori realistici:

| Categoria | N | PV | xG | GS |
|---|---|---|---|---|
| High Regain | 3 | **0.18** | 0.62 | 1 |
| Combination | 8 | 0.12 | 0.71 | 1 |
| Set Piece | 4 | 0.09 | 0.52 | 0 |
| Cross | 5 | −0.03 | 0.31 | 0 |

**Lettura**:

- **High Regain (PV=0.18)**: 3 tiri dopo recupero alto → i tiri finiscono in zone molto pericolose. Il pressing alto porta la palla direttamente vicino alla porta avversaria. Alto PV + alta conversione (1 gol su 3 tiri).

- **Combination (PV=0.12)**: 8 tiri da build-up paziente → più volume, pericolosità media più bassa per singolo tiro ma xG totale alto. Nessuna conversione nonostante xG=0.71 → sottoperformance.

- **Set Piece (PV=0.09)**: 4 tiri da palla inattiva → pericolosità moderata. I calci piazzati portano a tiri da zone variabili; PV bassa-media è atteso.

- **Cross (PV=−0.03)**: 5 tiri da cross → in media i tiri avvengono da posizione **meno pericolosa** del punto di entrata nel FT. Può indicare: cross raccolti lontano dalla porta, seconde palle da fuori area, duelli aerei in posizioni non ottimali.

### 5.3 PV Positivo vs Negativo nel Contesto dei Tiri

Un **PV negativo** per un tiro non significa che l'azione sia stata inefficace. Può indicare:
- Il pallone è entrato nel FT da posizione privilegiata (es. recupero a x=85) e il tiro è avvenuto da zona meno favorevole
- Tiro affrettato da fuori area dopo una penetrazione profonda (perdita di profondità)
- Pressing avversario che ha costretto a concludere prima del previsto

Il PV va sempre letto **in combinazione con xG**:

| Scenario | PV | xG | Lettura |
|---|---|---|---|
| Contropiede diretto | Alto | Alto | Tiro in zona pericolosa + alta qualità chance |
| Build-up elaborato | Basso | Medio | Possesso costruito ma conclusione non ottimale |
| Tiro da fuori area | Basso/neg | Basso | Zona poco pericolosa, chance di bassa qualità |
| Corner diretto | Variabile | Alto | Posizione sull'area piccola: alta qualità anche se PV dipende dall'entrata |

---

## 6. Limitazioni

### 6.1 Solo Event Data, No Tracking Data

Il modello non ha accesso a:
- **Velocità della palla**: un passaggio veloce in profondità è più pericoloso di uno lento nella stessa zona
- **Posizione del portiere**: determina dove sarebbe effettivamente impossibile segnare
- **Posizione dei difensori**: un tiro "libero" da 20m vale molto più di uno bloccato alla stessa distanza

Questo è un limite intrinseco degli event data Opta: il modello valuta posizione e tipo di azione, non la qualità dell'esecuzione o il contesto tattico-difensivo istantaneo.

### 6.2 Definizione di Possesso Semplificata

Il possesso è definito come: *sequenza continua di eventi della stessa squadra, interrotta da cambio team o gap > 5 secondi*.

Può causare:
- Unione di due situazioni distinte separate da un dribbling breve (gap < 5s)
- Frammentazione di azioni continue se c'è un ritardo non etichettato (infortuni, interruzioni VAR)

Le feature di possesso (`poss_event_index`, `x_max_in_poss_so_far`) dipendono dalla qualità di questa definizione.

### 6.3 Dipendenza dall'Identificazione del Final Third Entry

Il delta PV per i tiri dipende dall'identificazione corretta del primo evento nel terzo offensivo. Se i dati Opta contengono coordinate mancanti o errate, il calcolo ricade nel fallback (score assoluto del tiro — meno preciso).

### 6.4 Possibile Bias Stagionale (Serie A)

Il modello è addestrato esclusivamente su **Serie A 2008-2026**. Il calcio italiano ha caratteristiche stilistiche specifiche: difesa organizzata, bassa intensità di pressing rispetto a Premier League o Bundesliga. Le stime potrebbero essere sistematicamente diverse se applicate a dati di altre leghe.

### 6.5 Calibrazione Approssimata

Con solo event data, la calibrazione è approssimata: il modello stima P(goal | posizione + tipo azione) ma non corregge per fattori che solo il tracking può vedere (portiere fuori posizione, difensore che blocca il tiro, ecc.).

### 6.6 Out-of-Distribution Risk

Il modello può dare stime inaffidabili per eventi rari non rappresentati nel training:
- Punizioni da 40+ metri
- Retropassaggi estremi sotto pressione
- Situazioni di sovrannumero in area (non codificate negli event data Opta)

Per questi casi, le stime tendono verso la media empirica della zona.

---

## Appendice: Struttura del File `pv_model_serie_a.pkl`

```python
{
    "model":             # <sklearn/xgboost estimator fitted>,
    "model_type":        # "logistic_regression" | "xgboost",
    "scaler":            # <StandardScaler> | None   (solo per LR),
    "feature_cols":      [
        "x", "y", "x2", "y2", "xy",
        "dist_to_goal", "angle_to_goal",
        "in_box", "in_final_third", "central_corridor", "dist_to_center_y",
        "type_id", "outcome",
        "is_pass", "is_carry_touch", "is_recovery",
        "is_tackle", "is_interception",
        "through_ball", "cross", "head", "aerial",
        "poss_event_index", "x_max_in_poss_so_far"
    ],
    "label":             "ends_in_goal",
    "trained_on":        "Italy_Serie_A",
    "train_seasons":     "2008-2009 -> 2021-2022",
    "val_seasons":       "2022-2023 -> 2023-2024",
    "test_season":       "2024-2025",
    "roc_auc_val":       # <float>,
    "roc_auc_test":      # <float>,
    "avg_precision_val": # <float>,
    "brier_score_val":   # <float>,
    "n_train":           # <int>,
    "n_features":        24,
    "scale_pos_weight":  # <float> | None,
}
```

Il file viene caricato dal `PossessionValueModel` singleton in `pv_model.py`.
Viene aggiornato ogni volta che si riesegue `train_pv_model.py` con nuovi dati.

---

*Documento FMP SerieA Dashboard — Aprile 2026. Versione 2.0 ML.*
