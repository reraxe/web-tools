#!/usr/bin/env python3
"""Create a consistent Dex database backup while the app is running."""

import os
import sqlite3
from datetime import datetime
from pathlib import Path


data_dir = Path(os.environ.get("DEX_DATA_DIR", "/data"))
source = Path(os.environ.get("DEX_DB_PATH", data_dir / "dex.db"))
backup_dir = Path(os.environ.get("DEX_BACKUP_DIR", data_dir / "backups"))
backup_dir.mkdir(parents=True, exist_ok=True)
destination = backup_dir / f"dex-{datetime.now().strftime('%Y%m%d-%H%M%S')}.db"

with sqlite3.connect(source) as src, sqlite3.connect(destination) as dst:
    src.backup(dst)

print(destination)
