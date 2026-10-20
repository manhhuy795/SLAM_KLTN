#!/usr/bin/env bash
set -euo pipefail
repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
command -v python3 >/dev/null
command -v node >/dev/null || { echo "Install Node.js 22 (see README.md)."; exit 1; }
command -v npm >/dev/null
node -e 'const [m,n]=process.versions.node.split(".").map(Number); if(!((m===20&&n>=19)||(m===22&&n>=12)||m>=24)){console.error("Use Node.js 22.12+ or 24+.");process.exit(1)}'
cd "$repo_dir/web/backend"
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python init_db.py
.venv/bin/python seed.py
.venv/bin/python import_demo.py
.venv/bin/python import_demo.py --dataset simulation
cd "$repo_dir/web"
npm ci
npm run build
echo "Ready. Open two terminals for backend/frontend using README.md."
