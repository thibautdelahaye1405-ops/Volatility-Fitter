"""Dev server entry point for the volfit API.

Run from the repo root (volfit is pip-installed editable in .venv):
    .venv\\Scripts\\python backend\\serve.py

Binds to 127.0.0.1:8000; the Vite frontend (localhost:5173) is CORS-allowed.
"""

import uvicorn

if __name__ == "__main__":
    uvicorn.run("volfit.api.app:app", host="127.0.0.1", port=8000)
