# ARFlow Backend

Microservizio FastAPI per la conversione di modelli 3D:
GLB / glTF / OBJ / STL → OpenUSD (hub interno) → GLB.

STEP/STP e altri formati CAD nativi non sono ancora supportati
(fase successiva, richiederà OpenCASCADE).

## Variabili d'ambiente richieste

- `SUPABASE_URL`
- `SUPABASE_SERVICE_KEY` (service role key, non la anon key)
- `GEMINI_API_KEY` (per la chat AI del viewer — mai esposta al client)

## Endpoint

- `GET /health` — healthcheck
- `POST /convert` — avvia la conversione in background
  ```json
  {
    "file_url": "...",
    "format": "glb",
    "model_id": "...",
    "user_id": "..."
  }
  ```
  Lo stato va letto dalla tabella `models` su Supabase (colonna `status`:
  `processing` / `ready` / `error`).

- `POST /chat` — proxy verso Gemini (chiave lato server)
  ```json
  {
    "message": "...",
    "history": [{"role": "user", "content": "..."}],
    "context": {"name": "...", "format": "...", "category": "...", "material": "...", "notes": "..."}
  }
  ```
  Risposta: `{"reply": "..."}`
