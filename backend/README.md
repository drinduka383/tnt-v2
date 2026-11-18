# TNT v2 analysis API

See ../README.md for setup and ../ARCHITECTURE.md for contracts. Run `python main.py` from this directory with requirements.txt installed. Waitress binds to 127.0.0.1:5000 by default. Native baseline models live in models/. Runtime runs, evidence and SQLite state live in data/. Use one process per data directory; a lock enforces ownership.

Endpoints: GET /health, GET /models, GET /search, POST /runs, GET /runs/:id, POST /runs/:id/cancel. Training is offline through train.py. No pickle model loading or legacy side-effecting GET /analyze is exposed.
