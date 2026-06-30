# ARFlow Conversion Backend

Microservizio Python per la conversione di file CAD (STEP, ZIP multi-file, USD/USDZ) verso glTF/GLB.

## Stato attuale — v0.2.0

**STEP/STP funzionante davvero**, tramite pythonocc-core (binding Python di OpenCASCADE) + trimesh. Conversione asincrona via Celery + Redis.

## ⚠️ Setup richiesto su Railway — due servizi necessari

Questo backend ha bisogno di **due processi separati** che girano sulla stessa codebase:

1. **Web** (FastAPI) — riceve le richieste HTTP, accoda i job
2. **Worker** (Celery) — esegue effettivamente le conversioni in background

Su Railway, dopo il primo deploy (che crea il servizio "web"), devi aggiungere un **secondo servizio** nello stesso progetto:

1. Nel progetto Railway → "+ New" → "Empty Service" (oppure "GitHub Repo" di nuovo, stesso repo)
2. Vai su Settings del nuovo servizio → Deploy → **Start Command**, inserisci:
   ```
   conda run -n arflow celery -A app.celery_app worker --loglevel=info
   ```
3. Collega le stesse variabili d'ambiente del servizio web (vedi sotto)

## Variabili d'ambiente — OBBLIGATORIE su entrambi i servizi (web + worker)

```
SUPABASE_URL=https://lpucdkqgbwmgzcwpuajd.supabase.co
SUPABASE_SERVICE_KEY=<la tua service_role key — NON la anon key>
REDIS_URL=<collegata automaticamente da Railway se Redis è nello stesso progetto>
```

**Dove trovare `SUPABASE_SERVICE_KEY`:** Supabase dashboard → Settings → API → sezione "Project API keys" → `service_role` (è diversa dalla `anon` key che usi nel frontend — questa bypassa le Row Level Security policy, va tenuta segreta e usata solo lato server).

## Sviluppo locale (richiede conda)

```bash
conda create -n arflow python=3.11 -y
conda activate arflow
conda install -c conda-forge pythonocc-core=7.9.3 -y
pip install -r requirements.txt

# Terminal 1 — web server
uvicorn app.main:app --reload --port 8000

# Terminal 2 — worker Celery (richiede Redis locale o REDIS_URL remoto)
celery -A app.celery_app worker --loglevel=info
```

## Deploy su Railway

Il build usa **Docker** (non Nixpacks) perché pythonocc-core richiede conda — non è installabile con pip puro. Il primo build sarà lento (5-10 minuti) perché compila l'ambiente conda completo.

1. Railway rileva il `Dockerfile` automaticamente (configurato in `railway.toml`)
2. Aggiungi le variabili d'ambiente (vedi sopra) su **entrambi** i servizi
3. Genera il domain pubblico solo sul servizio "web" — il worker non serve esposto

## Schema database — esegui su Supabase prima del primo test

```sql
ALTER TABLE models ADD COLUMN IF NOT EXISTS conversion_error TEXT;
```
(file completo in `schema_addition.sql`)

## Endpoint disponibili

- `GET /health` — verifica che il servizio sia online
- `POST /convert` — accoda una conversione: `{ file_url, format, model_id, user_id }`
- `GET /jobs/{job_id}` — polling dello stato di un job

## Prossimi step (non ancora implementati)

- [ ] Gestione upload ZIP multi-file (OBJ+MTL+texture, FBX con asset esterni)
- [ ] Supporto USD/USDZ via usd-core
- [ ] Decimazione/ottimizzazione mesh per modelli STEP molto pesanti
- [ ] Estrazione gerarchia assembly più ricca (sub-assembly annidati)

