"""Funciones compartidas: config, cola, Telegram y utilidades."""
import hashlib
import json
import os
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
QUEUE_PATH = ROOT / "data" / "queue.json"
STATE_PATH = ROOT / "data" / "state.json"
MEDIA_DIR = ROOT / "media"

TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "")

FRANJAS = {"dia": "☀️ DÍA (fondo beige)", "noche": "🌙 NOCHE (fondo negro)"}


# ---------- archivos ----------
def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_queue():
    return load_json(QUEUE_PATH, [])


def save_queue(queue):
    save_json(QUEUE_PATH, queue)


# ---------- tiempo ----------
def now_local():
    return datetime.now(timezone(timedelta(hours=CONFIG["utc_offset"])))


def franja_actual():
    h = now_local().hour
    return "dia" if CONFIG["hora_inicio_dia"] <= h < CONFIG["hora_fin_dia"] else "noche"


# ---------- textos ----------
def normalizar_texto(t):
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode()
    t = re.sub(r"[^a-z0-9 ]", " ", t.lower())
    return re.sub(r"\s+", " ", t).strip()


def hash_texto(t):
    n = normalizar_texto(t)
    return hashlib.sha256(n.encode()).hexdigest()[:16] if n else ""


# ---------- stock ----------
def stock(queue):
    s = {"dia": 0, "noche": 0, "sin_texto": 0}
    for e in queue:
        if e["estado"] == "pendiente":
            s[e["franja"]] += 1
        elif e["estado"] == "sin_texto":
            s["sin_texto"] += 1
    return s


def resumen_stock(queue):
    s = stock(queue)
    ppd = CONFIG["publicaciones_por_franja_por_dia"]
    lineas = [
        f"☀️ Día: {s['dia']} en cola (~{s['dia'] / ppd:.1f} días)",
        f"🌙 Noche: {s['noche']} en cola (~{s['noche'] / ppd:.1f} días)",
    ]
    if s["sin_texto"]:
        lineas.append(f"⚠️ {s['sin_texto']} imagen(es) esperando descripción")
    return "\n".join(lineas)


# ---------- Telegram ----------
def tg(method, **params):
    r = requests.post(
        f"https://api.telegram.org/bot{TG_TOKEN}/{method}", json=params, timeout=60
    )
    r.raise_for_status()
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram {method}: {data}")
    return data["result"]


def tg_send(text):
    if not TG_TOKEN or not TG_CHAT:
        print("[telegram desactivado]", text)
        return
    try:
        tg("sendMessage", chat_id=TG_CHAT, text=text[:4000])
    except Exception as ex:  # un aviso fallido nunca debe frenar el bot
        print("No se pudo avisar por Telegram:", ex)


def tg_download(file_id):
    info = tg("getFile", file_id=file_id)
    url = f"https://api.telegram.org/file/bot{TG_TOKEN}/{info['file_path']}"
    r = requests.get(url, timeout=120)
    r.raise_for_status()
    return r.content
