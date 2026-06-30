# ── ARFlow Backend — Dockerfile con conda per pythonocc-core ──────────────────
# Usa miniconda come base perché pythonocc-core NON è installabile via pip:
# richiede i binding precompilati di OpenCASCADE disponibili solo su conda-forge.

FROM continuumio/miniconda3:latest

WORKDIR /app

# Librerie di sistema richieste a runtime da OpenCASCADE (OpenGL, OpenMP, X11)
# libgomp1: runtime OpenMP, usato internamente da OCCT per il multi-threading
# Le altre sono necessarie per il rendering OpenGL anche se headless
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    libgl1 \
    libglu1-mesa \
    libxmu6 \
    libxi6 \
    libxext6 \
    libsm6 \
    libxrender1 \
    && rm -rf /var/lib/apt/lists/*

# Crea ambiente conda con Python 3.11 + pythonocc-core da conda-forge
RUN conda create -n arflow python=3.11 -y && \
    conda install -n arflow -c conda-forge pythonocc-core=7.9.3 -y && \
    conda clean -afy

# Attiva l'ambiente conda per tutti i comandi successivi
SHELL ["conda", "run", "-n", "arflow", "/bin/bash", "-c"]

# Copia e installa le dipendenze pip (FastAPI, Celery, ecc.)
# pythonocc-core resta gestito da conda, il resto via pip dentro lo stesso ambiente
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia il codice applicativo
COPY app/ ./app/

# Script di avvio copiato direttamente (più affidabile della generazione con echo,
# che può corrompere i newline secondo la shell di build usata da Railway)
COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

EXPOSE 8000
CMD ["/app/start.sh"]
