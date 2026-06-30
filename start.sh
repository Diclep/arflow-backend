#!/bin/bash
conda run -n arflow --no-capture-output uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
