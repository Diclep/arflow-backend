"""
Proxy verso Gemini per la chat AI del viewer (dashboard + demo).
La API key resta lato server (env var GEMINI_API_KEY), mai esposta al browser.
"""
import os

import requests

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-2.5-flash-lite"  # gemini-1.5-flash è deprecato
GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
)

if not GEMINI_API_KEY:
    print("⚠ ATTENZIONE: GEMINI_API_KEY non configurata. Imposta questa variabile su Railway.")


def _build_system_prompt(context: dict) -> str:
    name = context.get("name", "modello")
    fmt = context.get("format", "")
    category = context.get("category", "")
    material = context.get("material", "")
    notes = context.get("notes", "")

    prompt = (
        "Sei ARFlow AI Agent, assistente tecnico specializzato in modelli 3D industriali.\n"
        f"Modello: {name} | Formato: {fmt} | Categoria: {category} | Materiale: {material}\n"
    )
    if notes:
        prompt += f"Knowledge tecnica:\n{notes}\n"
    prompt += (
        "Rispondi in italiano, tecnico ma accessibile, massimo 3-4 frasi. "
        "Non inventare dati non presenti nei metadati."
    )
    return prompt


def ask_gemini(message: str, history: list, context: dict) -> str:
    """
    history: lista di {"role": "user"|"assistant", "content": "..."}
    context: {"name", "format", "category", "material", "notes"}
    """
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY non configurata sul backend.")

    system_prompt = _build_system_prompt(context)

    contents = []
    for h in history:
        role = "user" if h.get("role") == "user" else "model"
        contents.append({"role": role, "parts": [{"text": h.get("content", "")}]})
    contents.append({"role": "user", "parts": [{"text": message}]})

    payload = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": contents,
        "generationConfig": {"maxOutputTokens": 512, "temperature": 0.7},
    }

    resp = requests.post(
        f"{GEMINI_URL}?key={GEMINI_API_KEY}",
        headers={"Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        return "Risposta non disponibile."
