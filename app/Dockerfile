FROM python:3.11-slim

# Librerie di sistema richieste da Blender in modalità headless (nessuna GPU/X11 necessaria)
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget xz-utils \
    libxi6 libxrender1 libxfixes3 libxkbcommon0 libsm6 libgl1 libxxf86vm1 \
    && rm -rf /var/lib/apt/lists/*

# Blender headless (versione confermata: 5.1.2, https://download.blender.org/release/Blender5.1/)
RUN wget -q https://download.blender.org/release/Blender5.1/blender-5.1.2-linux-x64.tar.xz -O /tmp/blender.tar.xz \
    && mkdir -p /opt/blender \
    && tar -xf /tmp/blender.tar.xz -C /opt/blender --strip-components=1 \
    && rm /tmp/blender.tar.xz \
    && ln -s /opt/blender/blender /usr/local/bin/blender

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
