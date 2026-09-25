"""Publica la imagen más antigua de la franja actual (día/noche) vía Buffer.

Uso: python bot/publish.py [dia|noche]   (sin argumento, decide por la hora)
Una publicación nunca se repite: al publicarse queda marcada como "publicada"
en data/queue.json y ya no vuelve a elegirse.
"""
import os
import sys
import time

import requests

from common import (
    CONFIG, FRANJAS, load_queue, now_local, franja_actual, resumen_stock,
    save_queue, stock, tg_send,
)

BUFFER_API_KEY = os.environ.get("BUFFER_API_KEY", "")
BUFFER_CHANNEL_ID = os.environ.get("BUFFER_CHANNEL_ID", "")
REPO = os.environ.get("GITHUB_REPOSITORY", "")  # lo completa GitHub Actions


def url_publica(archivo):
    return f"https://raw.githubusercontent.com/{REPO}/{CONFIG['rama']}/media/{archivo}"


def esperar_url(url, intentos=6):
    """El repo recién actualizado puede tardar un poco en servir la imagen."""
    for _ in range(intentos):
        if requests.head(url, timeout=30).status_code == 200:
            return True
        time.sleep(20)
    return False


# Si en Primero Vos tu mutation de Buffer es distinta, reemplazá SOLO esta función.
def publicar_en_buffer(texto, image_url):
    mutation = """
    mutation CrearPost($input: CreatePostInput!) {
      createPost(input: $input) {
        ... on PostActionSuccess { post { id } }
        ... on MutationError { message }
      }
    }"""
    variables = {"input": {
        "channelId": BUFFER_CHANNEL_ID,
        "text": texto,
        "schedulingType": "automatic",
        "mode": "shareNow",
        "assets": [{"image": {"url": image_url}}],
        "metadata": {"facebook": {"type": "post"}},
    }}
    r = requests.post(
        "https://api.buffer.com",
        json={"query": mutation, "variables": variables},
        headers={"Authorization": f"Bearer {BUFFER_API_KEY}"},
        timeout=60,
    )
    r.raise_for_status()
    data = r.json()
    if data.get("errors"):
        raise RuntimeError(data["errors"])
    res = (data.get("data") or {}).get("createPost") or {}
    if res.get("message"):
        raise RuntimeError(res["message"])
    return (res.get("post") or {}).get("id", "")


def main():
    if not (BUFFER_API_KEY and BUFFER_CHANNEL_ID and REPO):
        raise SystemExit("Faltan BUFFER_API_KEY / BUFFER_CHANNEL_ID / GITHUB_REPOSITORY")

    franja = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] in FRANJAS else franja_actual()
    queue = load_queue()
    cola = sorted(
        (e for e in queue if e["estado"] == "pendiente" and e["franja"] == franja),
        key=lambda e: e["agregada"],
    )
    if not cola:
        tg_send(f"🚨 No había imágenes de {FRANJAS[franja]} para publicar. ¡Cargá más!")
        print("Cola vacía:", franja)
        return

    e = cola[0]
    url = url_publica(e["archivo"])
    try:
        if not esperar_url(url):
            raise RuntimeError(f"La imagen no es accesible en {url} (¿el repo es público?)")
        post_id = publicar_en_buffer(e["texto"], url)
    except Exception as ex:
        e["intentos"] = e.get("intentos", 0) + 1
        if e["intentos"] >= 3:
            e["estado"] = "error"  # la saca de la cola para no trabar las siguientes
        save_queue(queue)
        tg_send(f"❌ Falló la publicación de {FRANJAS[franja]} (intento {e['intentos']}): {ex}")
        raise

    e["estado"] = "publicada"
    e["publicada"] = now_local().isoformat(timespec="seconds")
    e["buffer_id"] = post_id
    save_queue(queue)
    print("Publicada:", e["id"], post_id)

    dias = stock(queue)[franja] / CONFIG["publicaciones_por_franja_por_dia"]
    if dias < CONFIG["alerta_dias_restantes"]:
        tg_send(f"⏳ Queda poco stock de {FRANJAS[franja]}.\n\n" + resumen_stock(queue))


if __name__ == "__main__":
    main()
