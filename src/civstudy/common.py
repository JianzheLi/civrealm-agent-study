import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(os.environ.get('CIVSTUDY_ROOT', Path(__file__).resolve().parents[2]))


def plain(value):
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    if hasattr(value, 'tolist'):
        return plain(value.tolist())
    if hasattr(value, 'get_bitvector_in_ascii'):
        return value.get_bitvector_in_ascii()
    if isinstance(value, Path):
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plain(data), ensure_ascii=False, indent=2) + '\n')


def append_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a') as f:
        f.write(json.dumps(plain(data), ensure_ascii=False) + '\n')


def read_jsonl(path):
    path = Path(path)
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []


def write_csv(path, rows, fields=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = fields or list(dict.fromkeys(k for row in rows for k in row))
    with path.open('w', newline='') as f:
        out = csv.DictWriter(f, fieldnames=fields)
        out.writeheader()
        for row in rows:
            out.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v for k, v in row.items()})


def load_config(path=None):
    return json.loads(Path(path or ROOT / 'configs/development.json').read_text())
