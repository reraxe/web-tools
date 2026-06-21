#!/usr/bin/env python3
"""Dex TCG inventory MVP.

Dependency-light HTTP API and static-file server backed by SQLite. The Docker
image adds QR generation support, while the core application stays portable.
"""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import mimetypes
import os
import re
import shutil
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import date, datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse


ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
DATA_DIR = Path(os.environ.get("DEX_DATA_DIR", ROOT / "data")).resolve()
DB_PATH = Path(os.environ.get("DEX_DB_PATH", DATA_DIR / "dex.db")).resolve()
IMAGE_DIR = Path(os.environ.get("DEX_IMAGE_DIR", DATA_DIR / "images")).resolve()
INBOUND_DIR = Path(os.environ.get("DEX_INBOUND_DIR", DATA_DIR / "inbound")).resolve()
HOST = os.environ.get("DEX_HOST", "0.0.0.0")
PORT = int(os.environ.get("DEX_PORT", "8080"))
MAX_BODY = 40 * 1024 * 1024
WATCH_INBOUND = os.environ.get("DEX_WATCH_INBOUND", "1") == "1"
SCAN_INTERVAL = int(os.environ.get("DEX_SCAN_INTERVAL", "5"))

GAME_PREFIXES = {"Pokemon": "PKM", "One Piece": "OP", "Riftbound": "RFB"}
DB_LOCK = threading.Lock()


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connect():
    db = sqlite3.connect(DB_PATH, timeout=20)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA journal_mode = WAL")
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    INBOUND_DIR.mkdir(parents=True, exist_ok=True)
    with connect() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS batches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_code TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                completed_at TEXT,
                status TEXT NOT NULL DEFAULT 'OPEN',
                game TEXT NOT NULL,
                set_code TEXT NOT NULL,
                set_name TEXT NOT NULL DEFAULT '',
                color TEXT NOT NULL DEFAULT '',
                finish_group TEXT NOT NULL DEFAULT 'Non-Foil',
                default_condition TEXT NOT NULL DEFAULT 'Near Mint',
                acquisition_type TEXT NOT NULL,
                total_cost REAL NOT NULL DEFAULT 0,
                location TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT NOT NULL UNIQUE,
                batch_id INTEGER NOT NULL REFERENCES batches(id),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                card_number TEXT NOT NULL DEFAULT '',
                name TEXT NOT NULL DEFAULT 'Needs identification',
                set_name TEXT NOT NULL DEFAULT '',
                rarity TEXT NOT NULL DEFAULT '',
                color TEXT NOT NULL DEFAULT '',
                variant TEXT NOT NULL DEFAULT 'Standard',
                condition TEXT NOT NULL DEFAULT 'Near Mint',
                status TEXT NOT NULL DEFAULT 'REVIEW',
                location TEXT NOT NULL DEFAULT '',
                front_image TEXT,
                back_image TEXT,
                source_hash TEXT,
                label_printed INTEGER NOT NULL DEFAULT 0,
                market_low REAL,
                market_average REAL,
                market_high REAL,
                market_updated_at TEXT,
                listing_platform TEXT,
                listing_price REAL,
                listing_reference TEXT
            );

            CREATE TABLE IF NOT EXISTS sale_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,
                order_number TEXT NOT NULL DEFAULT '',
                sold_at TEXT NOT NULL,
                subtotal REAL NOT NULL DEFAULT 0,
                shipping_collected REAL NOT NULL DEFAULT 0,
                platform_fees REAL NOT NULL DEFAULT 0,
                postage_cost REAL NOT NULL DEFAULT 0,
                notes TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS sale_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL REFERENCES sale_orders(id),
                card_id INTEGER NOT NULL UNIQUE REFERENCES cards(id),
                sale_price REAL NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS processed_scans (
                fingerprint TEXT PRIMARY KEY,
                batch_id INTEGER NOT NULL REFERENCES batches(id),
                processed_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_cards_batch ON cards(batch_id);
            CREATE INDEX IF NOT EXISTS idx_cards_status ON cards(status);
            CREATE INDEX IF NOT EXISTS idx_cards_identity
                ON cards(card_number, variant, condition);
            CREATE INDEX IF NOT EXISTS idx_sales_date ON sale_orders(sold_at);
            """
        )


def as_dict(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row is not None else None


def clean_text(value: object, limit: int = 180) -> str:
    return str(value or "").strip()[:limit]


def money(value: object) -> float:
    try:
        return round(max(0.0, float(value or 0)), 2)
    except (TypeError, ValueError):
        return 0.0


def make_batch_code(db: sqlite3.Connection, game: str) -> str:
    prefix = GAME_PREFIXES.get(game, "TCG")
    stamp = date.today().strftime("%Y%m%d")
    stem = f"{prefix}-B{stamp}"
    count = db.execute(
        "SELECT COUNT(*) FROM batches WHERE batch_code LIKE ?", (stem + "-%",)
    ).fetchone()[0]
    return f"{stem}-{count + 1:02d}"


def next_sku(db: sqlite3.Connection, game: str) -> str:
    prefix = GAME_PREFIXES.get(game, "TCG")
    stamp = date.today().strftime("%Y%m%d")
    stem = f"{prefix}-B{stamp}-"
    rows = db.execute(
        "SELECT sku FROM cards WHERE sku LIKE ? ORDER BY sku DESC LIMIT 1",
        (stem + "%",),
    ).fetchone()
    sequence = int(rows["sku"].rsplit("-", 1)[-1]) + 1 if rows else 1
    return f"{stem}{sequence:03d}"


def decode_image(data_url: str) -> tuple[bytes, str]:
    match = re.match(r"^data:(image/[a-zA-Z0-9.+-]+);base64,(.+)$", data_url, re.S)
    if not match:
        raise ValueError("Invalid image data")
    raw = base64.b64decode(match.group(2), validate=True)
    if len(raw) > 15 * 1024 * 1024:
        raise ValueError("Image exceeds 15 MB")
    mime = match.group(1).lower()
    ext = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}.get(mime)
    if not ext:
        raise ValueError("Only JPG, PNG, and WebP images are supported")
    return raw, ext


def save_image(sku: str, side: str, data_url: str | None) -> str | None:
    if not data_url:
        return None
    raw, ext = decode_image(data_url)
    card_dir = IMAGE_DIR / sku
    card_dir.mkdir(parents=True, exist_ok=True)
    path = card_dir / f"{side}{ext}"
    path.write_bytes(raw)
    return str(path.relative_to(DATA_DIR)).replace("\\", "/")


def copy_scan_image(sku: str, side: str, source: Path) -> str:
    ext = source.suffix.lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp"):
        raise ValueError(f"Unsupported scan format: {ext}")
    card_dir = IMAGE_DIR / sku
    card_dir.mkdir(parents=True, exist_ok=True)
    destination = card_dir / f"{side}{'.jpg' if ext == '.jpeg' else ext}"
    shutil.copy2(source, destination)
    return str(destination.relative_to(DATA_DIR)).replace("\\", "/")


def scan_fingerprint(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        stat = path.stat()
        digest.update(f"{path.resolve()}|{stat.st_size}|{stat.st_mtime_ns}".encode())
    return digest.hexdigest()


def pair_scan_files(files: list[Path]) -> list[tuple[Path, Path]]:
    """Pair explicit front/back names first, then pair remaining files in order."""
    explicit: dict[str, dict[str, Path]] = {}
    remaining: list[Path] = []
    side_pattern = re.compile(r"^(.*?)[_ -](front|back)$", re.I)
    for path in sorted(files, key=lambda item: item.name.lower()):
        match = side_pattern.match(path.stem)
        if match:
            explicit.setdefault(match.group(1).lower(), {})[match.group(2).lower()] = path
        else:
            remaining.append(path)
    pairs = [
        (sides["front"], sides["back"])
        for sides in explicit.values()
        if "front" in sides and "back" in sides
    ]
    pairs.extend(zip(remaining[0::2], remaining[1::2]))
    return pairs


def ingest_file_pair(batch_id: int, front_source: Path, back_source: Path) -> dict | None:
    fingerprint = scan_fingerprint([front_source, back_source])
    with DB_LOCK, connect() as db:
        if db.execute("SELECT 1 FROM processed_scans WHERE fingerprint = ?", (fingerprint,)).fetchone():
            return None
        batch = db.execute("SELECT * FROM batches WHERE id = ? AND status = 'OPEN'", (batch_id,)).fetchone()
        if not batch:
            return None
        sku = next_sku(db, batch["game"])
        front = copy_scan_image(sku, "front", front_source)
        back = copy_scan_image(sku, "back", back_source)
        now = utcnow()
        cursor = db.execute(
            """
            INSERT INTO cards (
                sku, batch_id, created_at, updated_at, name, set_name, color,
                variant, condition, status, location, front_image, back_image, source_hash
            ) VALUES (?, ?, ?, ?, 'Needs identification', ?, ?, 'Standard', ?, 'REVIEW', ?, ?, ?, ?)
            """,
            (
                sku, batch_id, now, now, batch["set_name"], batch["color"],
                batch["default_condition"], batch["location"], front, back, fingerprint,
            ),
        )
        db.execute(
            "INSERT INTO processed_scans (fingerprint, batch_id, processed_at) VALUES (?, ?, ?)",
            (fingerprint, batch_id, now),
        )
        return dict(db.execute("SELECT * FROM cards WHERE id = ?", (cursor.lastrowid,)).fetchone())


def watch_inbound() -> None:
    while True:
        try:
            with connect() as db:
                batches = db.execute("SELECT id, batch_code FROM batches WHERE status = 'OPEN'").fetchall()
            for batch in batches:
                folder = INBOUND_DIR / batch["batch_code"]
                if not folder.exists():
                    continue
                now = time.time()
                candidates = [
                    path for path in folder.iterdir()
                    if path.is_file()
                    and path.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")
                    and now - path.stat().st_mtime > 2
                ]
                for front, back in pair_scan_files(candidates):
                    ingest_file_pair(batch["id"], front, back)
        except Exception as exc:
            print(f"Inbound watcher: {exc}")
        time.sleep(max(2, SCAN_INTERVAL))


def create_card(db: sqlite3.Connection, batch: sqlite3.Row, payload: dict) -> dict:
    sku = next_sku(db, batch["game"])
    front = save_image(sku, "front", payload.get("front_image"))
    back = save_image(sku, "back", payload.get("back_image"))
    now = utcnow()
    card_number = clean_text(payload.get("card_number"), 40).upper()
    name = clean_text(payload.get("name")) or "Needs identification"
    status = "IN_STOCK" if card_number and name != "Needs identification" else "REVIEW"
    values = (
        sku,
        batch["id"],
        now,
        now,
        card_number,
        name,
        clean_text(payload.get("set_name")) or batch["set_name"],
        clean_text(payload.get("rarity"), 60),
        clean_text(payload.get("color"), 40) or batch["color"],
        clean_text(payload.get("variant"), 80) or "Standard",
        clean_text(payload.get("condition"), 40) or batch["default_condition"],
        status,
        clean_text(payload.get("location"), 80) or batch["location"],
        front,
        back,
    )
    cursor = db.execute(
        """
        INSERT INTO cards (
            sku, batch_id, created_at, updated_at, card_number, name, set_name,
            rarity, color, variant, condition, status, location, front_image, back_image
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        values,
    )
    return dict(db.execute("SELECT * FROM cards WHERE id = ?", (cursor.lastrowid,)).fetchone())


def inventory_groups(filters: dict[str, list[str]]) -> list[dict]:
    clauses = []
    params: list[object] = []
    q = clean_text(filters.get("q", [""])[0], 100)
    game = clean_text(filters.get("game", [""])[0], 40)
    status = clean_text(filters.get("status", [""])[0], 30)
    platform = clean_text(filters.get("platform", [""])[0], 30)
    if q:
        clauses.append("(c.name LIKE ? OR c.card_number LIKE ? OR c.sku LIKE ? OR c.location LIKE ?)")
        needle = f"%{q}%"
        params.extend([needle] * 4)
    if game:
        clauses.append("b.game = ?")
        params.append(game)
    if status:
        clauses.append("c.status = ?")
        params.append(status)
    if platform:
        clauses.append("COALESCE(c.listing_platform, '') = ?")
        params.append(platform)
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    with connect() as db:
        rows = db.execute(
            f"""
            SELECT c.*, b.game, b.set_code, b.batch_code, b.finish_group,
                   b.total_cost AS batch_total_cost,
                   (SELECT COUNT(*) FROM cards bc WHERE bc.batch_id = b.id) AS batch_card_count
            FROM cards c JOIN batches b ON b.id = c.batch_id
            {where}
            """,
            params,
        ).fetchall()

    grouped: dict[str, dict] = {}
    for row in rows:
        item = dict(row)
        identity = "|".join(
            [item["game"], item["card_number"] or item["sku"], item["variant"], item["condition"]]
        )
        group = grouped.setdefault(
            identity,
            {
                "key": identity,
                "game": item["game"],
                "card_number": item["card_number"],
                "name": item["name"],
                "set_code": item["set_code"],
                "set_name": item["set_name"],
                "rarity": item["rarity"],
                "color": item["color"],
                "variant": item["variant"],
                "condition": item["condition"],
                "market_low": item["market_low"],
                "market_average": item["market_average"],
                "market_high": item["market_high"],
                "market_updated_at": item["market_updated_at"],
                "copies": [],
            },
        )
        item["allocated_cost"] = round(
            item["batch_total_cost"] / max(1, item["batch_card_count"]), 2
        )
        group["copies"].append(item)
        for field in ("market_low", "market_average", "market_high", "market_updated_at"):
            if group[field] is None and item[field] is not None:
                group[field] = item[field]

    result = list(grouped.values())
    for group in result:
        group["quantity"] = len(group["copies"])
        group["in_stock"] = sum(1 for card in group["copies"] if card["status"] in ("IN_STOCK", "REVIEW"))
        group["tcg_slots"] = sum(
            1
            for card in group["copies"]
            if card["status"] == "IN_STOCK" and card["listing_platform"] == "TCGplayer"
        )
        group["locations"] = sorted({card["location"] for card in group["copies"] if card["location"]})

    sort = clean_text(filters.get("sort", ["average_desc"])[0], 30)
    reverse = not sort.endswith("_asc")
    field = {
        "average_desc": "market_average",
        "average_asc": "market_average",
        "low_desc": "market_low",
        "low_asc": "market_low",
        "high_desc": "market_high",
        "high_asc": "market_high",
        "name_asc": "name",
        "name_desc": "name",
    }.get(sort, "market_average")
    if field == "name":
        result.sort(key=lambda x: x["name"].lower(), reverse=reverse)
    else:
        result.sort(key=lambda x: (x[field] is not None, x[field] or 0), reverse=reverse)
    return result


def dashboard() -> dict:
    with connect() as db:
        values = dict(
            db.execute(
                """
                SELECT
                    COUNT(*) AS total_cards,
                    SUM(CASE WHEN status IN ('IN_STOCK', 'REVIEW') THEN 1 ELSE 0 END) AS in_stock,
                    SUM(CASE WHEN status = 'REVIEW' THEN 1 ELSE 0 END) AS needs_review,
                    SUM(CASE WHEN label_printed = 0 AND status != 'SOLD' THEN 1 ELSE 0 END) AS labels_waiting,
                    SUM(CASE WHEN listing_platform = 'TCGplayer' AND status = 'IN_STOCK' THEN 1 ELSE 0 END) AS tcg_slots,
                    SUM(CASE WHEN market_average >= 20 AND status = 'IN_STOCK' THEN 1 ELSE 0 END) AS ebay_candidates,
                    COALESCE(SUM(CASE WHEN status = 'IN_STOCK' THEN market_average ELSE 0 END), 0) AS market_value
                FROM cards
                """
            ).fetchone()
        )
        values["open_batches"] = db.execute(
            "SELECT COUNT(*) FROM batches WHERE status = 'OPEN'"
        ).fetchone()[0]
        values["recent_batches"] = [
            dict(row)
            for row in db.execute(
                """
                SELECT b.*, COUNT(c.id) AS card_count
                FROM batches b LEFT JOIN cards c ON c.batch_id = b.id
                GROUP BY b.id ORDER BY b.created_at DESC LIMIT 5
                """
            ).fetchall()
        ]
    return values


def seed_demo() -> None:
    if os.environ.get("DEX_SEED_DEMO", "0") != "1":
        return
    with connect() as db:
        if db.execute("SELECT COUNT(*) FROM batches").fetchone()[0]:
            return
        now = utcnow()
        code = make_batch_code(db, "One Piece")
        cursor = db.execute(
            """
            INSERT INTO batches (
                batch_code, created_at, status, game, set_code, set_name, color,
                finish_group, acquisition_type, total_cost, location
            ) VALUES (?, ?, 'OPEN', 'One Piece', 'OP16', 'The Azure Sea''s Seven',
                      'Yellow', 'Rare / Foil', 'Booster Box', 114.99, 'OP16-Yellow')
            """,
            (code, now),
        )
        batch_id = cursor.lastrowid
        demo = [
            ("OP16-112", "Boa Hancock", "Super Rare", 6.25, 8.41, 11.80, "TCGplayer"),
            ("OP16-042", "Kikunojo", "Rare", 1.19, 1.88, 2.75, "TCGplayer"),
            ("OP16-118", "Enel", "Secret Rare", 17.40, 22.65, 29.00, "eBay"),
            ("OP16-071", "Nami", "Super Rare", 3.82, 5.12, 7.25, None),
        ]
        for index, (number, name, rarity, low, avg, high, platform) in enumerate(demo, 1):
            sku = f"OP-B{date.today().strftime('%Y%m%d')}-{index:03d}"
            db.execute(
                """
                INSERT INTO cards (
                    sku, batch_id, created_at, updated_at, card_number, name,
                    set_name, rarity, color, variant, condition, status, location,
                    market_low, market_average, market_high, market_updated_at,
                    listing_platform, listing_price
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Yellow', 'Standard', 'Near Mint',
                          'IN_STOCK', 'OP16-Yellow', ?, ?, ?, ?, ?, ?)
                """,
                (sku, batch_id, now, now, number, name, "The Azure Sea's Seven", rarity,
                 low, avg, high, now, platform, avg),
            )
        db.commit()


class DexHandler(BaseHTTPRequestHandler):
    server_version = "Dex/0.1"

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"[{self.log_date_time_string()}] {fmt % args}")

    def send_json(self, value: object, status: int = 200) -> None:
        payload = json.dumps(value, separators=(",", ":"), default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def send_error_json(self, message: str, status: int = 400) -> None:
        self.send_json({"error": message}, status)

    def read_json(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("Invalid request length") from exc
        if length <= 0 or length > MAX_BODY:
            raise ValueError("Request body is empty or too large")
        try:
            value = json.loads(self.rfile.read(length))
        except json.JSONDecodeError as exc:
            raise ValueError("Invalid JSON") from exc
        if not isinstance(value, dict):
            raise ValueError("Expected a JSON object")
        return value

    def serve_file(self, path: Path, cache: bool = True) -> None:
        try:
            resolved = path.resolve()
            allowed = resolved.is_relative_to(STATIC_DIR.resolve()) or resolved.is_relative_to(DATA_DIR)
            if not allowed or not resolved.is_file():
                self.send_error(404)
                return
            body = resolved.read_bytes()
            mime = mimetypes.guess_type(resolved.name)[0] or "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "public, max-age=3600" if cache else "no-store")
            self.end_headers()
            self.wfile.write(body)
        except OSError:
            self.send_error(404)

    def serve_inventory_csv(self) -> None:
        with connect() as db:
            rows = db.execute(
                """
                SELECT c.sku, c.status, b.game, b.set_code, c.card_number, c.name,
                       c.rarity, c.color, c.variant, c.condition, c.location,
                       b.batch_code, b.acquisition_type,
                       ROUND(b.total_cost / MAX(1, (SELECT COUNT(*) FROM cards bc WHERE bc.batch_id = b.id)), 2) AS allocated_cost,
                       c.market_low, c.market_average, c.market_high, c.market_updated_at,
                       c.listing_platform, c.listing_price, o.sold_at,
                       o.platform AS sale_platform, o.order_number
                FROM cards c
                JOIN batches b ON b.id = c.batch_id
                LEFT JOIN sale_items si ON si.card_id = c.id
                LEFT JOIN sale_orders o ON o.id = si.order_id
                ORDER BY c.id
                """
            ).fetchall()
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        headers = list(rows[0].keys()) if rows else [
            "sku", "status", "game", "set_code", "card_number", "name", "rarity",
            "color", "variant", "condition", "location", "batch_code",
            "acquisition_type", "allocated_cost", "market_low", "market_average",
            "market_high", "market_updated_at", "listing_platform", "listing_price",
            "sold_at", "sale_platform", "order_number",
        ]
        writer.writerow(headers)
        writer.writerows(tuple(row) for row in rows)
        body = output.getvalue().encode("utf-8-sig")
        self.send_response(200)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="dex-inventory-{date.today().isoformat()}.csv"')
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        query = parse_qs(parsed.query)
        try:
            if path == "/api/health":
                self.send_json({"status": "ok", "name": "Dex", "time": utcnow()})
            elif path == "/api/dashboard":
                self.send_json(dashboard())
            elif path == "/api/inventory":
                self.send_json({"groups": inventory_groups(query)})
            elif path == "/api/export/inventory.csv":
                self.serve_inventory_csv()
            elif path == "/api/batches":
                with connect() as db:
                    rows = db.execute(
                        """
                        SELECT b.*, COUNT(c.id) AS card_count,
                               SUM(CASE WHEN c.status = 'REVIEW' THEN 1 ELSE 0 END) AS review_count
                        FROM batches b LEFT JOIN cards c ON c.batch_id = b.id
                        GROUP BY b.id ORDER BY b.created_at DESC
                        """
                    ).fetchall()
                self.send_json({"batches": [dict(row) for row in rows]})
            elif re.fullmatch(r"/api/batches/\d+", path):
                batch_id = int(path.rsplit("/", 1)[-1])
                with connect() as db:
                    batch = db.execute("SELECT * FROM batches WHERE id = ?", (batch_id,)).fetchone()
                    cards = db.execute(
                        "SELECT * FROM cards WHERE batch_id = ? ORDER BY id", (batch_id,)
                    ).fetchall()
                if not batch:
                    self.send_error_json("Batch not found", 404)
                else:
                    self.send_json({"batch": dict(batch), "cards": [dict(row) for row in cards]})
            elif re.fullmatch(r"/api/cards/[A-Z0-9-]+", path):
                sku = unquote(path.rsplit("/", 1)[-1])
                with connect() as db:
                    row = db.execute(
                        """SELECT c.*, b.game, b.set_code, b.batch_code, b.acquisition_type,
                                  b.total_cost, b.finish_group
                           FROM cards c JOIN batches b ON b.id = c.batch_id WHERE c.sku = ?""",
                        (sku,),
                    ).fetchone()
                if not row:
                    self.send_error_json("Card not found", 404)
                else:
                    self.send_json(dict(row))
            elif path == "/api/labels":
                with connect() as db:
                    rows = db.execute(
                        """
                        SELECT c.*, b.game, b.set_code FROM cards c
                        JOIN batches b ON b.id = c.batch_id
                        WHERE c.label_printed = 0 AND c.status != 'SOLD'
                        ORDER BY c.id
                        """
                    ).fetchall()
                self.send_json({"labels": [dict(row) for row in rows]})
            elif path == "/api/sales":
                with connect() as db:
                    rows = db.execute(
                        """
                        SELECT o.*, COUNT(i.id) AS item_count,
                               o.subtotal + o.shipping_collected - o.platform_fees - o.postage_cost AS net_proceeds
                        FROM sale_orders o LEFT JOIN sale_items i ON i.order_id = o.id
                        GROUP BY o.id ORDER BY o.sold_at DESC, o.id DESC LIMIT 100
                        """
                    ).fetchall()
                self.send_json({"sales": [dict(row) for row in rows]})
            elif path == "/api/qr":
                self.serve_qr(clean_text(query.get("value", [""])[0], 160))
            elif path.startswith("/media/"):
                rel = unquote(path.removeprefix("/media/"))
                self.serve_file(DATA_DIR / rel)
            elif path == "/":
                self.serve_file(STATIC_DIR / "index.html", cache=False)
            else:
                candidate = STATIC_DIR / path.lstrip("/")
                if candidate.is_file():
                    self.serve_file(candidate)
                elif "." not in Path(path).name:
                    self.serve_file(STATIC_DIR / "index.html", cache=False)
                else:
                    self.send_error(404)
        except Exception as exc:  # Keep the API response useful during the pilot.
            self.send_error_json(str(exc), 500)

    def serve_qr(self, value: str) -> None:
        if not value:
            self.send_error_json("Missing QR value")
            return
        try:
            import qrcode  # type: ignore

            image = qrcode.make(value, box_size=6, border=2)
            buffer = BytesIO()
            image.save(buffer, format="PNG")
            body = buffer.getvalue()
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "public, max-age=86400")
            self.end_headers()
            self.wfile.write(body)
        except ImportError:
            # Local no-dependency preview; Docker installs the real QR renderer.
            escaped = quote(value, safe="")
            svg = f"""<svg xmlns='http://www.w3.org/2000/svg' width='120' height='120'
              viewBox='0 0 120 120'><rect width='120' height='120' fill='white'/>
              <rect x='8' y='8' width='104' height='104' fill='none' stroke='#141918' stroke-width='5'/>
              <path d='M18 18h26v26H18zm58 0h26v26H76zM18 76h26v26H18zM54 54h12v12H54zm18 0h12v12H72zM54 72h12v12H54zm18 18h30v12H72z'
                fill='#141918'/><title>{escaped}</title></svg>""".encode()
            self.send_response(200)
            self.send_header("Content-Type", "image/svg+xml")
            self.send_header("Content-Length", str(len(svg)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(svg)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        try:
            payload = self.read_json()
            if path == "/api/batches":
                game = clean_text(payload.get("game"), 40)
                set_code = clean_text(payload.get("set_code"), 40).upper()
                acquisition = clean_text(payload.get("acquisition_type"), 40)
                if game not in GAME_PREFIXES or not set_code or not acquisition:
                    raise ValueError("Game, set, and acquisition type are required")
                with connect() as db:
                    code = make_batch_code(db, game)
                    location = clean_text(payload.get("location"), 80)
                    if not location:
                        color = clean_text(payload.get("color"), 40)
                        location = f"{set_code}-{color}" if color else set_code
                    cursor = db.execute(
                        """
                        INSERT INTO batches (
                            batch_code, created_at, game, set_code, set_name, color,
                            finish_group, default_condition, acquisition_type,
                            total_cost, location, notes
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            code, utcnow(), game, set_code, clean_text(payload.get("set_name")),
                            clean_text(payload.get("color"), 40),
                            clean_text(payload.get("finish_group"), 60) or "Non-Foil",
                            clean_text(payload.get("default_condition"), 40) or "Near Mint",
                            acquisition, money(payload.get("total_cost")), location,
                            clean_text(payload.get("notes"), 500),
                        ),
                    )
                    batch = dict(db.execute("SELECT * FROM batches WHERE id = ?", (cursor.lastrowid,)).fetchone())
                (INBOUND_DIR / code).mkdir(parents=True, exist_ok=True)
                self.send_json(batch, 201)
            elif re.fullmatch(r"/api/batches/\d+/cards", path):
                batch_id = int(path.split("/")[3])
                with connect() as db:
                    batch = db.execute("SELECT * FROM batches WHERE id = ?", (batch_id,)).fetchone()
                    if not batch:
                        self.send_error_json("Batch not found", 404)
                        return
                    card = create_card(db, batch, payload)
                self.send_json(card, 201)
            elif re.fullmatch(r"/api/batches/\d+/complete", path):
                batch_id = int(path.split("/")[3])
                with connect() as db:
                    db.execute(
                        "UPDATE batches SET status = 'COMPLETE', completed_at = ? WHERE id = ?",
                        (utcnow(), batch_id),
                    )
                    batch = db.execute("SELECT * FROM batches WHERE id = ?", (batch_id,)).fetchone()
                if not batch:
                    self.send_error_json("Batch not found", 404)
                else:
                    self.send_json(dict(batch))
            elif path == "/api/labels/printed":
                skus = payload.get("skus", [])
                if not isinstance(skus, list) or not skus:
                    raise ValueError("Select at least one label")
                with connect() as db:
                    placeholders = ",".join("?" for _ in skus)
                    db.execute(f"UPDATE cards SET label_printed = 1 WHERE sku IN ({placeholders})", skus)
                self.send_json({"updated": len(skus)})
            elif path == "/api/sales":
                skus = payload.get("skus", [])
                platform = clean_text(payload.get("platform"), 30)
                if platform not in ("eBay", "TCGplayer") or not isinstance(skus, list) or not skus:
                    raise ValueError("Platform and at least one SKU are required")
                unique_skus = list(dict.fromkeys(clean_text(sku, 40) for sku in skus))
                with connect() as db:
                    placeholders = ",".join("?" for _ in unique_skus)
                    cards = db.execute(
                        f"SELECT * FROM cards WHERE sku IN ({placeholders})", unique_skus
                    ).fetchall()
                    if len(cards) != len(unique_skus):
                        found = {row["sku"] for row in cards}
                        raise ValueError("Unknown SKU: " + ", ".join(s for s in unique_skus if s not in found))
                    unavailable = [row["sku"] for row in cards if row["status"] == "SOLD"]
                    if unavailable:
                        raise ValueError("Already sold: " + ", ".join(unavailable))
                    subtotal = money(payload.get("subtotal"))
                    cursor = db.execute(
                        """
                        INSERT INTO sale_orders (
                            platform, order_number, sold_at, subtotal, shipping_collected,
                            platform_fees, postage_cost, notes
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            platform, clean_text(payload.get("order_number"), 80),
                            clean_text(payload.get("sold_at"), 30) or date.today().isoformat(),
                            subtotal, money(payload.get("shipping_collected")),
                            money(payload.get("platform_fees")), money(payload.get("postage_cost")),
                            clean_text(payload.get("notes"), 500),
                        ),
                    )
                    order_id = cursor.lastrowid
                    per_item = round(subtotal / len(cards), 2)
                    for card in cards:
                        db.execute(
                            "INSERT INTO sale_items (order_id, card_id, sale_price) VALUES (?, ?, ?)",
                            (order_id, card["id"], per_item),
                        )
                        db.execute(
                            "UPDATE cards SET status = 'SOLD', updated_at = ? WHERE id = ?",
                            (utcnow(), card["id"]),
                        )
                    order = dict(db.execute("SELECT * FROM sale_orders WHERE id = ?", (order_id,)).fetchone())
                self.send_json(order, 201)
            else:
                self.send_error_json("Not found", 404)
        except ValueError as exc:
            self.send_error_json(str(exc), 400)
        except sqlite3.IntegrityError as exc:
            self.send_error_json(f"Database conflict: {exc}", 409)
        except Exception as exc:
            self.send_error_json(str(exc), 500)

    def do_PATCH(self) -> None:
        path = urlparse(self.path).path.rstrip("/")
        try:
            payload = self.read_json()
            batch_match = re.fullmatch(r"/api/batches/(\d+)", path)
            if batch_match:
                allowed = {"color", "finish_group", "location"}
                updates = {
                    key: clean_text(value, 80)
                    for key, value in payload.items()
                    if key in allowed
                }
                if not updates:
                    raise ValueError("No scan-group fields supplied")
                assignments = ", ".join(f"{key} = ?" for key in updates)
                with connect() as db:
                    db.execute(
                        f"UPDATE batches SET {assignments} WHERE id = ?",
                        [*updates.values(), int(batch_match.group(1))],
                    )
                    row = db.execute(
                        "SELECT * FROM batches WHERE id = ?", (int(batch_match.group(1)),)
                    ).fetchone()
                if not row:
                    self.send_error_json("Batch not found", 404)
                else:
                    self.send_json(dict(row))
                return
            match = re.fullmatch(r"/api/cards/([A-Z0-9-]+)", path)
            if not match:
                self.send_error_json("Not found", 404)
                return
            sku = unquote(match.group(1))
            allowed = {
                "card_number", "name", "set_name", "rarity", "color", "variant",
                "condition", "status", "location", "market_low", "market_average",
                "market_high", "listing_platform", "listing_price", "listing_reference",
            }
            updates = {key: value for key, value in payload.items() if key in allowed}
            if not updates:
                raise ValueError("No editable fields supplied")
            for field in ("market_low", "market_average", "market_high", "listing_price"):
                if field in updates:
                    updates[field] = money(updates[field]) if updates[field] not in (None, "") else None
            for field in set(updates) - {"market_low", "market_average", "market_high", "listing_price"}:
                updates[field] = clean_text(updates[field], 180)
            if any(field in updates for field in ("market_low", "market_average", "market_high")):
                updates["market_updated_at"] = utcnow()
            updates["updated_at"] = utcnow()
            assignments = ", ".join(f"{key} = ?" for key in updates)
            with connect() as db:
                db.execute(
                    f"UPDATE cards SET {assignments} WHERE sku = ?",
                    [*updates.values(), sku],
                )
                row = db.execute("SELECT * FROM cards WHERE sku = ?", (sku,)).fetchone()
            if not row:
                self.send_error_json("Card not found", 404)
            else:
                self.send_json(dict(row))
        except ValueError as exc:
            self.send_error_json(str(exc), 400)
        except Exception as exc:
            self.send_error_json(str(exc), 500)


def run() -> None:
    init_db()
    seed_demo()
    if WATCH_INBOUND:
        threading.Thread(target=watch_inbound, name="dex-inbound", daemon=True).start()
    server = ThreadingHTTPServer((HOST, PORT), DexHandler)
    print(f"Dex is running at http://127.0.0.1:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    run()
