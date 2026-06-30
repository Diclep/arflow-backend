# ARFlow Conversion Backend

Microservizio Python per la conversione di file CAD (STEP, ZIP multi-file, USD/USDZ) verso glTF/GLB, da integrare con la piattaforma ARFlow.

## Stato attuale — v0.1.0 (scheletro)

Questo è lo scheletro base: un endpoint `/convert` che accetta richieste e risponde, ma **non esegue ancora la conversione reale**. Serve a validare che il deploy su Railway funzioni prima di aggiungere la logica pesante (pythonOCC-core, Celery, worker).

## Sviluppo locale

```bash
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Apri `http://localhost:8000/docs` per la documentazione interattiva Swagger.

## Deploy su Railway

1. Crea un nuovo progetto su [railway.app](https://railway.app) → "Deploy from GitHub repo"
2. Seleziona questo repository
3. Railway rileva automaticamente Python e usa `railway.toml` per il comando di start
4. Dopo il deploy, Railway fornisce un URL pubblico tipo `https://arflow-backend.up.railway.app`
5. Testa con: `curl https://arflow-backend.up.railway.app/health`

## Prossimi step (non ancora implementati)

- [ ] Integrazione pythonOCC-core per conversione STEP/STP reale
- [ ] Celery + Redis per processing asincrono (i file CAD possono richiedere minuti)
- [ ] Gestione upload ZIP multi-file (OBJ+MTL+texture, FBX con asset esterni)
- [ ] Supporto USD/USDZ via usd-core
- [ ] Estrazione metadati avanzata (stesso formato JSON del Blocco A)
- [ ] Upload risultato su Supabase Storage + update tabella `models`
- [ ] Webhook/polling per notificare la dashboard a fine conversione

## Variabili d'ambiente (da configurare su Railway)

```
SUPABASE_URL=https://lpucdkqgbwmgzcwpuajd.supabase.co
SUPABASE_SERVICE_KEY=<chiave service_role, NON quella anon — serve per scrivere senza RLS>
REDIS_URL=<fornito automaticamente da Railway se aggiungi il plugin Redis>
```
