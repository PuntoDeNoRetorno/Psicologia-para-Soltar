# Bot de cola de imágenes (Meta AI → Telegram → GitHub → Buffer → Facebook)

Vos cargás las imágenes y textos de Meta AI en un bot de Telegram.
GitHub Actions las guarda, las separa en día o noche según el color de fondo
y publica 2 a la mañana y 2 a la noche, sin repetir nunca.

## Instalación (una sola vez, ~15 min)

### 1. Bot de Telegram
1. En Telegram hablale a **@BotFather** → `/newbot` → elegí nombre → copiá el **token**.
2. Abrí tu bot nuevo y mandale `/start`.
3. Entrá en el navegador a `https://api.telegram.org/bot<TOKEN>/getUpdates`
   y buscá `"chat":{"id": 123456789` → ese número es tu **chat_id**.

### 2. Buffer
1. Conectá la página nueva de Facebook como canal en Buffer (plan gratis: hasta 3 canales).
2. Obtené el **channel ID** igual que hiciste en Primero Vos. La API key es la misma que ya usás.

### 3. Repositorio en GitHub
1. Creá un repo **público**. Buffer necesita poder descargar la imagen por URL.
   Los secrets siguen siendo privados; lo único visible son las imágenes, que igual se publican.
2. Subí todo el contenido de esta carpeta, incluida `.github/`.
3. **Settings → Secrets and variables → Actions → New repository secret**:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
   - `BUFFER_API_KEY`
   - `BUFFER_CHANNEL_ID`
4. **Settings → Actions → General → Workflow permissions → Read and write permissions** → Save.
5. Si la rama principal no se llama `main`, cambiala en `config.json` (`"rama"`).

### 4. Prueba
1. Mandale una foto con texto al bot de Telegram.
2. **Actions → Ingesta desde Telegram → Run workflow**. Te tiene que llegar "✅ Guardada en…".
3. **Actions → Publicar en Facebook → Run workflow** (elegí `dia` o `noche`) y revisá la página.

## Uso diario
- Guardás la imagen de Meta AI y la compartís al bot, **una por una**
  (los álbumes solo llevan texto en la primera foto), con la descripción como pie de foto.
- Si el texto es largo (Telegram corta los pies de foto en 1024 caracteres), mandá la
  foto sola y después la descripción como mensaje aparte: se asigna a la última imagen sin texto.
- La franja se detecta sola por el brillo del borde. Para forzarla, empezá el texto con `#dia` o `#noche`
  (la etiqueta no se publica).
- `/estado` → cuántas quedan en cola · `/borrar` → elimina la última cargada.
- El bot te avisa si mandás una imagen o un texto repetido, si queda poco stock
  (menos de 3 días, se cambia en `config.json`) o si falla una publicación.

## Horarios
Están en `.github/workflows/publicar.yml`, en **UTC** (Argentina = UTC-3):
08:00, 11:00, 20:00 y 23:00 hora argentina. GitHub puede demorar los disparos
entre 5 y 30 minutos. La franja se decide por la hora real: de 5 a 17 h es día, el resto es noche.

## Si Buffer da error
La publicación está aislada en la función `publicar_en_buffer` de `bot/publish.py`.
Si la mutation que te funciona en Primero Vos es distinta, pegá esa función ahí y listo.
Tras 3 fallos seguidos, la imagen se marca como `error` para no trabar la cola.
