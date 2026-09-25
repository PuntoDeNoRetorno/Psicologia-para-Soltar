"""Lee los mensajes nuevos del bot de Telegram y los agrega a la cola.

Formas de cargar:
  - Foto con la descripción como pie de foto (lo más cómodo).
  - Foto sola y a continuación un mensaje de texto: el texto se asigna a la
    última imagen que quedó sin descripción.
Opcional: empezar el pie con #dia o #noche para forzar la franja.
Comandos: /estado  -> cuántas quedan en cola
          /borrar  -> elimina la última imagen cargada (si no se publicó)
"""
import io
import uuid
import re

from PIL import Image, ImageStat

from common import (
    CONFIG, FRANJAS, MEDIA_DIR, STATE_PATH, TG_CHAT, TG_TOKEN,
    hash_texto, load_json, load_queue, now_local, resumen_stock,
    save_json, save_queue, tg, tg_download, tg_send,
)

TAG_RE = re.compile(r"^\s*#(dia|día|mañana|manana|noche)\b\s*", re.IGNORECASE)


# ---------- imagen ----------
def clasificar(img):
    """Mide el brillo promedio de los bordes: beige = claro, negro = oscuro."""
    g = img.convert("L")
    w, h = g.size
    b = max(4, int(min(w, h) * 0.06))
    zonas = [(0, 0, w, b), (0, h - b, w, h), (0, 0, b, h), (w - b, 0, w, h)]
    brillo = sum(ImageStat.Stat(g.crop(z)).mean[0] for z in zonas) / 4
    return ("noche" if brillo < CONFIG["umbral_brillo"] else "dia"), brillo


def ahash(img):
    """Huella perceptual: detecta la misma imagen aunque Telegram la recomprima."""
    g = img.convert("L").resize((16, 16), Image.LANCZOS)
    px = list(g.getdata())
    prom = sum(px) / len(px)
    bits = "".join("1" if p > prom else "0" for p in px)
    return f"{int(bits, 2):064x}"


def distancia(a, b):
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def separar_tag(caption):
    m = TAG_RE.match(caption or "")
    if not m:
        return None, (caption or "").strip()
    tag = m.group(1).lower()
    franja = "noche" if tag == "noche" else "dia"
    return franja, caption[m.end():].strip()


def texto_duplicado(queue, texto, ignorar_id=None):
    h = hash_texto(texto)
    if not h:
        return None
    for e in queue:
        if e["id"] != ignorar_id and e.get("hash_texto") == h:
            return e
    return None


# ---------- procesamiento ----------
def procesar_imagen(queue, data, caption):
    img = Image.open(io.BytesIO(data))
    img.load()
    huella = ahash(img)

    for e in queue:
        if distancia(huella, e["hash_imagen"]) <= CONFIG["distancia_max_imagen_duplicada"]:
            tg_send(f"♻️ Imagen repetida (ya cargada el {e['agregada'][:10]}, "
                    f"estado: {e['estado']}). La descarté.")
            return

    forzada, texto = separar_tag(caption)
    auto, brillo = clasificar(img)
    franja = forzada or auto

    if texto:
        dup = texto_duplicado(queue, texto)
        if dup:
            tg_send(f"♻️ Esa descripción ya existe (cargada el {dup['agregada'][:10]}). "
                    "Descarté la imagen: mandala de nuevo con otro texto.")
            return

    ahora = now_local()
    eid = ahora.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    archivo = f"{eid}.jpg"
    MEDIA_DIR.mkdir(exist_ok=True)
    img.convert("RGB").save(MEDIA_DIR / archivo, "JPEG", quality=92)

    queue.append({
        "id": eid,
        "archivo": archivo,
        "franja": franja,
        "brillo": round(brillo, 1),
        "texto": texto,
        "hash_imagen": huella,
        "hash_texto": hash_texto(texto),
        "estado": "pendiente" if texto else "sin_texto",
        "agregada": ahora.isoformat(timespec="seconds"),
        "intentos": 0,
    })

    origen = "forzada con #" if forzada else f"detectada, brillo {brillo:.0f}"
    msg = f"✅ Guardada en {FRANJAS[franja]} ({origen})."
    if not texto:
        msg += "\n✍️ Falta la descripción: mandámela ahora como mensaje de texto."
    tg_send(msg + "\n\n" + resumen_stock(queue))


def asignar_texto(queue, texto):
    espera = [e for e in queue if e["estado"] == "sin_texto"]
    if not espera:
        tg_send("⚠️ Recibí un texto pero no hay ninguna imagen esperando descripción.")
        return
    e = espera[-1]
    forzada, texto = separar_tag(texto)
    if not texto:
        return
    dup = texto_duplicado(queue, texto, ignorar_id=e["id"])
    if dup:
        tg_send("♻️ Esa descripción ya existe. Mandame otro texto para la imagen.")
        return
    e["texto"] = texto
    e["hash_texto"] = hash_texto(texto)
    e["estado"] = "pendiente"
    if forzada:
        e["franja"] = forzada
    tg_send(f"✅ Descripción asignada ({FRANJAS[e['franja']]}).\n\n" + resumen_stock(queue))


def borrar_ultima(queue):
    candidatas = [e for e in queue if e["estado"] in ("pendiente", "sin_texto")]
    if not candidatas:
        tg_send("No hay nada sin publicar para borrar.")
        return
    e = candidatas[-1]
    queue.remove(e)
    (MEDIA_DIR / e["archivo"]).unlink(missing_ok=True)
    tg_send(f"🗑️ Borrada la última imagen ({FRANJAS[e['franja']]}).\n\n" + resumen_stock(queue))


def main():
    if not TG_TOKEN:
        raise SystemExit("Falta el secret TELEGRAM_BOT_TOKEN")

    state = load_json(STATE_PATH, {"offset": 0})
    updates = tg("getUpdates", offset=state["offset"], timeout=0,
                 allowed_updates=["message"])

    if not TG_CHAT:
        # Modo configuración: muestra los chat_id que le escribieron al bot.
        for u in updates:
            m = u.get("message", {})
            print("chat_id:", m.get("chat", {}).get("id"), "| de:", m.get("from", {}).get("first_name"))
        raise SystemExit("Cargá el chat_id de arriba en el secret TELEGRAM_CHAT_ID")

    queue = load_queue()
    for u in updates:
        state["offset"] = u["update_id"] + 1
        msg = u.get("message")
        if not msg or str(msg["chat"]["id"]) != str(TG_CHAT):
            continue  # ignora a cualquier otra persona que le escriba al bot
        try:
            texto = msg.get("text", "")
            doc = msg.get("document") or {}
            if texto.startswith("/estado") or texto.startswith("/start"):
                tg_send(resumen_stock(queue))
            elif texto.startswith("/borrar"):
                borrar_ultima(queue)
            elif msg.get("photo"):
                procesar_imagen(queue, tg_download(msg["photo"][-1]["file_id"]), msg.get("caption", ""))
            elif doc.get("mime_type", "").startswith("image/"):
                procesar_imagen(queue, tg_download(doc["file_id"]), msg.get("caption", ""))
            elif texto:
                asignar_texto(queue, texto)
        except Exception as ex:
            print("Error procesando mensaje:", ex)
            tg_send(f"❌ No pude procesar un mensaje: {ex}")
        save_queue(queue)
        save_json(STATE_PATH, state)

    save_json(STATE_PATH, state)
    print(f"{len(updates)} mensajes procesados.")


if __name__ == "__main__":
    main()
