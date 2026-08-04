import os
import json
import time
import html
import logging
import requests
import feedparser

from urllib.parse import urlparse

from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
from deep_translator import GoogleTranslator

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger("guitar_gear_news_bot")

TOKEN = os.getenv("TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

HISTORY_FILE = "noticias_enviadas.json"
SOURCE_STATE_FILE = "fuente_estado.json"

NOTICIAS_POR_CORRIDA = 5
NOTICIAS_POR_FUENTE = 1

MAX_LARGO_TITULO = 250
MAX_LARGO_RESUMEN = 800

HEADERS_HTTP = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# Firmas que indican que el traductor devolvió una página de error
# de Google (HTTP 200 con cuerpo de error) en vez de una traducción real.
FIRMAS_ERROR_TRADUCCION = [
    "that's an error",
    "there was an error",
    "please try again later",
    "that's all we know",
    "error 500",
    "error 429",
    "<html", "<!doctype"
]

FUENTES = {
    "Guitar World": "https://www.guitarworld.com/feeds/all",
    "Ultimate Guitar": "https://www.ultimate-guitar.com/rss/news",
    "Premier Guitar": "https://www.premierguitar.com/feeds/news",
    "MusicRadar": "https://www.musicradar.com/rss",
    "Guitar Player": "https://www.guitarplayer.com/feeds/all",
    "Reverb News": "https://reverb.com/news/rss",
    "Sweetwater News": "https://www.sweetwater.com/insync/feed/",
    "Gearnews Guitar": "https://www.gearnews.com/zone/guitar/feed/",
    "Guitar.com": "https://guitar.com/feed/",
    "Guitar Interactive Magazine": "https://guitarinteractivemagazine.com/feed/",
    "Vintage Guitar Magazine": "https://www.vintageguitar.com/feed/",
    "Total Guitar": "https://www.musicradar.com/total-guitar/rss",
    "Guitar Techniques": "https://www.musicradar.com/guitar-techniques/rss",
    "Acoustic Guitar Magazine": "https://acousticguitar.com/feed/",
    "Jazz Guitar Today": "https://jazzguitartoday.com/feed/",
    "Classical Guitar Magazine": "https://classicalguitarmagazine.com/feed/",
    "KVR Audio News": "https://www.kvraudio.com/news.rss",
    "Gearspace": "https://gearspace.com/board/external.php?type=RSS2",
    "Metal Injection": "https://metalinjection.net/feed",
    "Louder Sound": "https://www.loudersound.com/feeds/all",
    "Blabbermouth": "https://blabbermouth.net/feed"
}

FUENTES_ORDENADAS = [
    {
        "nombre": "Young Guitar",
        "tipo": "youngguitar",
        "url": "https://youngguitar.jp/feed/"
    }
]

for nombre, url in FUENTES.items():
    FUENTES_ORDENADAS.append({
        "nombre": nombre,
        "tipo": "rss",
        "url": url
    })

KEYWORDS = [
    "electric guitar", "guitar", "guitar gear", "guitar pedals",
    "guitar amps", "guitar amplifier", "guitar plugins",
    "guitarristas", "guitarists", "guitar events", "NAMM",
    "Line 6 Helix", "Fractal Audio", "Kemper", "Boss pedals",
    "Ibanez guitar", "Fender guitar", "Gibson guitar", "PRS guitar",
    "pedalboard", "amp modeler", "multi effects", "plugin", "plugins",
    "guitarist", "amp", "pedal", "effects",
    "metal", "prog", "progressive metal", "shred", "djent",
    "death metal", "thrash metal",
    "John Petrucci", "Steve Vai", "Joe Satriani", "Tosin Abasi",
    "Tim Henson", "Plini", "Synyster Gates", "Zakk Wylde",
    "Yngwie", "Paul Gilbert",
    "vst", "audio interface", "IR loader", "cab sim", "amp sim",
    "firmware",
    "Fender", "Ibanez", "PRS", "Line 6", "Helix", "Fractal",
    "Axe-Fx", "FM3", "FM9", "Kemper", "Boss", "Neural DSP",
    "Quad Cortex", "firmware update", "preset", "cabinet IR",
    "amp capture", "profiling amp", "tone match", "modeler",
    "modeling", "multi-effects",
    "Schecter", "Schecter Guitar", "Schecter Guitar Research",
    "Suhr", "Suhr Guitars", "Charvel", "Vigier", "Vigier Guitars",
    "Tom Anderson", "Tom Anderson Guitarworks", "Anderson Guitarworks",
    "boutique guitar", "custom guitar", "superstrat"
]


# ---------------------------------------------------------------------------
# Historial y estado
# ---------------------------------------------------------------------------

def cargar_historial():
    try:
        if os.path.exists(HISTORY_FILE) and os.path.getsize(HISTORY_FILE) > 0:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                historial = json.load(f)
                return historial if isinstance(historial, list) else []
        return []
    except Exception as error:
        log.error(f"Error leyendo historial, se respalda y reinicia: {error}")
        if os.path.exists(HISTORY_FILE):
            try:
                os.replace(HISTORY_FILE, f"{HISTORY_FILE}.bak_{int(time.time())}")
            except OSError:
                pass
        return []


def guardar_historial(historial):
    historial_limpio = list(dict.fromkeys(historial))[-2000:]
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(historial_limpio, f, ensure_ascii=False, indent=4)
    log.info(f"Historial guardado: {len(historial_limpio)} noticias")


def cargar_estado_fuentes():
    try:
        if os.path.exists(SOURCE_STATE_FILE) and os.path.getsize(SOURCE_STATE_FILE) > 0:
            with open(SOURCE_STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"next_index": 0}
    except Exception:
        return {"next_index": 0}


def guardar_estado_fuentes(next_index):
    with open(SOURCE_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"next_index": next_index}, f, ensure_ascii=False, indent=4)


noticias_enviadas = cargar_historial()
noticias_enviadas_set = set(noticias_enviadas)
estado_fuentes = cargar_estado_fuentes()

telegram_message_url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

traductor_auto = GoogleTranslator(source="auto", target="es")
traductor_japones = GoogleTranslator(source="ja", target="es")


# ---------------------------------------------------------------------------
# Utilidades de texto / traducción
# ---------------------------------------------------------------------------

def limpiar_html(texto):
    soup = BeautifulSoup(texto or "", "html.parser")
    return soup.get_text(separator=" ", strip=True)


def contiene_japones(texto):
    if not texto:
        return False

    for char in texto:
        if (
            "\u3040" <= char <= "\u30ff" or
            "\u3400" <= char <= "\u4dbf" or
            "\u4e00" <= char <= "\u9fff"
        ):
            return True

    return False


def _parece_error_de_traduccion(texto):
    """Detecta si el traductor devolvió una página de error de Google
    (HTTP 200 con cuerpo de error) en vez de una traducción real."""
    if not texto:
        return False

    texto_lower = texto.lower()
    return any(firma in texto_lower for firma in FIRMAS_ERROR_TRADUCCION)


def traducir(texto, max_intentos=3, espera_base=2):
    """Traduce con reintentos y backoff exponencial. Si falla o el
    resultado es inválido (página de error), retorna el texto original."""
    if not texto:
        return ""

    for intento in range(1, max_intentos + 1):
        try:
            resultado = traductor_auto.translate(texto)

            if resultado and not _parece_error_de_traduccion(resultado):
                return resultado

            log.warning(
                f"Traducción inválida (intento {intento}/{max_intentos}), "
                f"firma de error detectada."
            )

        except Exception as error:
            log.warning(f"Fallo de traducción (intento {intento}/{max_intentos}): {error}")

        if intento < max_intentos:
            time.sleep(espera_base * (2 ** (intento - 1)))

    log.error("No se pudo traducir tras varios intentos. Se usa texto original.")
    return texto


def traducir_japones(texto, max_intentos=3, espera_base=2):
    """Traduce texto en japonés, con reintentos y validación de contenido
    (ni error de servicio, ni japonés residual)."""
    if not texto:
        return ""

    for intento in range(1, max_intentos + 1):
        try:
            traducido = traductor_japones.translate(texto)

            if (
                traducido
                and not _parece_error_de_traduccion(traducido)
                and not contiene_japones(traducido)
            ):
                return traducido

            log.warning(
                f"Traducción JA inválida (intento {intento}/{max_intentos})."
            )

        except Exception as error:
            log.warning(f"Fallo traducción JA (intento {intento}/{max_intentos}): {error}")

        if intento < max_intentos:
            time.sleep(espera_base * (2 ** (intento - 1)))

    # Fallback: intentar con el traductor automático (detección de idioma)
    try:
        traducido = traductor_auto.translate(texto)
        if (
            traducido
            and not _parece_error_de_traduccion(traducido)
            and not contiene_japones(traducido)
        ):
            return traducido
    except Exception as error:
        log.warning(f"Fallo fallback traducción auto: {error}")

    log.error("No se pudo traducir texto en japonés tras varios intentos.")
    return ""


def escape(texto):
    return html.escape(texto or "")


def noticia_reciente(entry):
    try:
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            fecha_noticia = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
            fecha_noticia = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)
        else:
            return True

        hace_dos_semanas = datetime.now(timezone.utc) - timedelta(days=14)
        return fecha_noticia >= hace_dos_semanas

    except Exception:
        return True


def crear_resumen(descripcion):
    if not descripcion:
        return "Consulta el enlace para leer la noticia completa."

    resumen = descripcion.strip()

    if len(resumen) > MAX_LARGO_RESUMEN:
        resumen = resumen[:MAX_LARGO_RESUMEN].strip() + "..."

    return resumen


def crear_resumen_youngguitar(texto_articulo, descripcion_rss=""):
    base = texto_articulo.strip() if texto_articulo else descripcion_rss.strip()

    if not base:
        return ""

    base = base[:3000]

    texto_es = traducir_japones(base)
    texto_es = limpiar_html(texto_es)

    if not texto_es:
        return ""

    if contiene_japones(texto_es):
        return ""

    if len(texto_es) > 1000:
        texto_es = texto_es[:1000].strip() + "..."

    return texto_es


def truncar_titulo(titulo):
    if titulo and len(titulo) > MAX_LARGO_TITULO:
        return titulo[:MAX_LARGO_TITULO].strip() + "..."
    return titulo


def es_relevante(titulo, descripcion):
    texto = f"{titulo} {descripcion}".lower()
    return any(keyword.lower() in texto for keyword in KEYWORDS)


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------

def enviar_texto(texto):
    """Envía un mensaje a Telegram. Retorna True solo si Telegram confirma
    la entrega (HTTP 200 + ok:true en el payload)."""
    if len(texto) > 3900:
        texto = texto[:3900] + "..."

    payload = {
        "chat_id": CHAT_ID,
        "text": texto,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }

    try:
        r = requests.post(telegram_message_url, data=payload, timeout=20)
        log.info(f"Telegram status: {r.status_code}")

        if r.status_code != 200:
            log.error(f"Telegram respondió con error: {r.text}")
            return False

        cuerpo = r.json()
        if not cuerpo.get("ok", False):
            log.error(f"Telegram ok=false: {cuerpo}")
            return False

        return True

    except requests.exceptions.RequestException as error:
        log.error(f"Excepción enviando a Telegram: {error}")
        return False


# ---------------------------------------------------------------------------
# Obtención de artículos / feeds
# ---------------------------------------------------------------------------

def obtener_texto_articulo(url):
    try:
        response = requests.get(url, headers=HEADERS_HTTP, timeout=12)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        parrafos = []
        for p in soup.find_all(["p", "h1", "h2", "h3"]):
            texto = p.get_text(" ", strip=True)
            if not texto or len(texto) < 25:
                continue
            parrafos.append(texto)

        return " ".join(parrafos)[:5000]

    except Exception as e:
        log.warning(f"No se pudo leer artículo: {url} | {e}")
        return ""


def _descargar_feed(url):
    """Descarga el feed con User-Agent explícito antes de parsear,
    evitando feeds vacíos por bloqueo silencioso del servidor."""
    try:
        response = requests.get(url, headers=HEADERS_HTTP, timeout=15)
        response.raise_for_status()
        return feedparser.parse(response.content)
    except requests.exceptions.RequestException as error:
        log.warning(f"No se pudo descargar el feed ({url}): {error}")
        return feedparser.parse(url)  # fallback al método original


def obtener_noticia_youngguitar():
    noticias = []

    try:
        feed = _descargar_feed("https://youngguitar.jp/feed/")

        for entry in feed.entries:
            if not noticia_reciente(entry):
                continue

            titulo = entry.get("title", "")
            descripcion = limpiar_html(entry.get("summary", ""))
            link = entry.get("link", "")

            if not titulo or not link:
                continue

            if link in noticias_enviadas_set:
                continue

            texto_articulo = obtener_texto_articulo(link)

            noticias.append({
                "fuente": "Young Guitar",
                "titulo": titulo,
                "descripcion": descripcion,
                "texto_articulo": texto_articulo,
                "link": link,
                "tipo": "japones"
            })

            if len(noticias) >= NOTICIAS_POR_FUENTE:
                return noticias

    except Exception as e:
        log.warning(f"Error Young Guitar: {e}")

    return noticias


def obtener_noticia_rss(fuente, rss_url):
    noticias = []
    log.info(f"Buscando en {fuente}")

    try:
        feed = _descargar_feed(rss_url)

        if feed.entries:
            for entry in feed.entries:
                if not noticia_reciente(entry):
                    continue

                titulo_original = entry.get("title", "")
                descripcion_original = limpiar_html(entry.get("summary", ""))
                link = entry.get("link", "")

                if not titulo_original or not link:
                    continue

                if link in noticias_enviadas_set:
                    continue

                if not es_relevante(titulo_original, descripcion_original):
                    continue

                noticias.append({
                    "fuente": fuente,
                    "titulo": titulo_original,
                    "descripcion": descripcion_original,
                    "link": link,
                    "tipo": "auto"
                })

                if len(noticias) >= NOTICIAS_POR_FUENTE:
                    return noticias

    except Exception as e:
        log.warning(f"RSS falló en {fuente}: {e}")

    # Fallback: scraping de enlaces si el RSS no trajo resultados
    try:
        response = requests.get(rss_url, headers=HEADERS_HTTP, timeout=12)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        enlaces = soup.find_all("a", href=True)
        usados = set()

        for enlace in enlaces:
            titulo = enlace.get_text(" ", strip=True)
            href = enlace.get("href", "")

            if not titulo or len(titulo) < 20:
                continue

            if href in usados or href in noticias_enviadas_set:
                continue

            texto_revision = f"{titulo} {href}".lower()
            if not any(keyword.lower() in texto_revision for keyword in KEYWORDS):
                continue

            if href.startswith("/"):
                dominio = urlparse(rss_url)
                href = f"{dominio.scheme}://{dominio.netloc}{href}"

            noticias.append({
                "fuente": fuente,
                "titulo": titulo,
                "descripcion": f"Nueva publicación detectada desde {fuente}.",
                "link": href,
                "tipo": "auto"
            })

            usados.add(href)

            if len(noticias) >= NOTICIAS_POR_FUENTE:
                return noticias

    except Exception as e:
        log.warning(f"Scraping falló en {fuente}: {e}")

    return noticias


def obtener_noticia_de_fuente(fuente):
    if fuente["tipo"] == "youngguitar":
        return obtener_noticia_youngguitar()

    return obtener_noticia_rss(fuente["nombre"], fuente["url"])


# ---------------------------------------------------------------------------
# Construcción de mensajes
# ---------------------------------------------------------------------------

def construir_mensaje(noticia):
    if noticia.get("tipo") == "japones":
        titulo = escape(truncar_titulo(traducir_japones(noticia["titulo"])))

        resumen_young = crear_resumen_youngguitar(
            noticia.get("texto_articulo", ""),
            noticia.get("descripcion", "")
        )
        resumen = escape(resumen_young)

    else:
        titulo = escape(truncar_titulo(traducir(noticia["titulo"])))

        descripcion = traducir(noticia.get("descripcion", ""))
        resumen = escape(crear_resumen(descripcion))

    link = noticia["link"]

    if resumen:
        return f"<b>{titulo}</b>\n\n{resumen}\n\n{link}"

    return f"<b>{titulo}</b>\n\n{link}"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if not TOKEN:
        log.error("Falta configurar TOKEN.")
        return

    if not CHAT_ID:
        log.error("Falta configurar CHAT_ID.")
        return

    fecha_hoy = datetime.now().strftime("%d/%m/%Y")

    noticias_finales = []
    links_usados = set()

    total_fuentes = len(FUENTES_ORDENADAS)
    start_index = estado_fuentes.get("next_index", 0)

    if start_index >= total_fuentes:
        start_index = 0

    indice_actual = start_index
    fuentes_revisadas = 0
    max_revisiones = total_fuentes * 3

    while (
        len(noticias_finales) < NOTICIAS_POR_CORRIDA
        and fuentes_revisadas < max_revisiones
    ):
        fuente = FUENTES_ORDENADAS[indice_actual]
        nuevas = obtener_noticia_de_fuente(fuente)

        for noticia in nuevas:
            link = noticia.get("link", "")

            if not link or link in links_usados:
                continue

            noticias_finales.append(noticia)
            links_usados.add(link)

            if len(noticias_finales) >= NOTICIAS_POR_CORRIDA:
                break

        indice_actual = (indice_actual + 1) % total_fuentes
        fuentes_revisadas += 1

    guardar_estado_fuentes(indice_actual)

    if not noticias_finales:
        log.info("No hay noticias nuevas para publicar.")
        return

    encabezado = (
        f"🎸 <b>GUITAR GEAR NEWS</b>\n\n"
        f"<b>Fecha:</b> {fecha_hoy}\n"
    )
    enviar_texto(encabezado)
    time.sleep(2)

    total_enviadas = 0
    total_fallidas = 0

    for noticia in noticias_finales:
        mensaje = construir_mensaje(noticia)
        exito = enviar_texto(mensaje)

        if exito:
            noticias_enviadas.append(noticia["link"])
            noticias_enviadas_set.add(noticia["link"])
            guardar_historial(noticias_enviadas)
            total_enviadas += 1
        else:
            total_fallidas += 1
            log.warning(
                f"No se pudo enviar (se reintentará en próxima corrida): "
                f"{noticia['titulo']}"
            )

        time.sleep(2)

    log.info(f"Noticias enviadas correctamente: {total_enviadas} | Fallidas: {total_fallidas}")


if __name__ == "__main__":
    main()
