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

# Modulo de traduccion multi-proveedor con cache. Debe estar en el mismo
# directorio que este archivo.
from traductor import (
    traducir_estricto,
    TraduccionFallida,
    autotest,
    resumen_stats,
    guardar_cache,
    proveedores_agotados,
)

# ---------------------------------------------------------------------------
# Configuracion
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

# Candidatas que se recogen por fuente en cada visita. Con la politica
# estricta hace falta mas de una: si la primera no se traduce, se prueba la
# siguiente de la MISMA fuente antes de rotar.
CANDIDATAS_POR_FUENTE = 3

MAX_LARGO_TITULO = 250
MAX_LARGO_RESUMEN = 800

# Young Guitar: cuanto texto del articulo se manda a traducir. El original
# usaba 3000 chars, que con el chunking del traductor son varias llamadas
# por noticia. 1500 basta para un resumen util a la mitad de coste.
MAX_TEXTO_ARTICULO_JA = 1500
MAX_LARGO_RESUMEN_JA = 1000

# --- Politica de traduccion estricta ---------------------------------------
MAX_CANDIDATOS_EVALUADOS = 45
MAX_FALLOS_SIN_NINGUN_EXITO = 6     # traductor caido -> abortar
MAX_FALLOS_TRAS_UN_EXITO = 15       # degradacion parcial -> seguir buscando
EXIGIR_RESUMEN_TRADUCIDO = False    # el titulo es obligatorio; el resumen no
ABORTAR_SI_NO_HAY_TRADUCTOR = True

HEADERS_HTTP = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

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
    {"nombre": "Young Guitar", "tipo": "youngguitar", "url": "https://youngguitar.jp/feed/"}
]
for _nombre, _url in FUENTES.items():
    FUENTES_ORDENADAS.append({"nombre": _nombre, "tipo": "rss", "url": _url})

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
# Historial y estado de rotacion
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


TELEGRAM_URL = f"https://api.telegram.org/bot{TOKEN}/sendMessage"


# ---------------------------------------------------------------------------
# Utilidades de texto
# ---------------------------------------------------------------------------

def limpiar_html(texto):
    soup = BeautifulSoup(texto or "", "html.parser")
    return soup.get_text(separator=" ", strip=True)


def contiene_japones(texto):
    if not texto:
        return False
    for char in texto:
        if ("\u3040" <= char <= "\u30ff" or
                "\u3400" <= char <= "\u4dbf" or
                "\u4e00" <= char <= "\u9fff"):
            return True
    return False


def sin_japones(texto):
    """Validador que se pasa al traductor: rechaza salidas con japones
    residual, de modo que la cascada pruebe el siguiente proveedor en vez
    de dar por buena una traduccion a medias."""
    return bool(texto) and not contiene_japones(texto)


def escape(texto):
    return html.escape(texto or "")


def truncar(texto, maximo, sufijo="..."):
    if texto and len(texto) > maximo:
        return texto[:maximo].strip() + sufijo
    return texto


def noticia_reciente(entry):
    try:
        if getattr(entry, "published_parsed", None):
            fecha = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        elif getattr(entry, "updated_parsed", None):
            fecha = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)
        else:
            return True
        return fecha >= datetime.now(timezone.utc) - timedelta(days=14)
    except Exception:
        return True


def es_relevante(titulo, descripcion):
    texto = f"{titulo} {descripcion}".lower()
    return any(keyword.lower() in texto for keyword in KEYWORDS)


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------

def enviar_texto(texto):
    if len(texto) > 3900:
        texto = texto[:3900] + "..."

    try:
        r = requests.post(
            TELEGRAM_URL,
            data={
                "chat_id": CHAT_ID,
                "text": texto,
                "parse_mode": "HTML",
                "disable_web_page_preview": False
            },
            timeout=20
        )
        log.info(f"Telegram status: {r.status_code}")

        if r.status_code != 200:
            log.error(f"Telegram respondio con error: {r.text}")
            return False

        cuerpo = r.json()
        if not cuerpo.get("ok", False):
            log.error(f"Telegram ok=false: {cuerpo}")
            return False

        return True

    except requests.exceptions.RequestException as error:
        log.error(f"Excepcion enviando a Telegram: {error}")
        return False


# ---------------------------------------------------------------------------
# Obtencion de candidatas (SIN traducir)
# ---------------------------------------------------------------------------

def _descargar_feed(url):
    try:
        response = requests.get(url, headers=HEADERS_HTTP, timeout=15)
        response.raise_for_status()
        return feedparser.parse(response.content)
    except requests.exceptions.RequestException as error:
        log.warning(f"No se pudo descargar el feed ({url}): {error}")
        return feedparser.parse(url)


def obtener_texto_articulo(url):
    """Scraping del cuerpo del articulo. Se llama de forma PEREZOSA, solo
    al preparar una noticia japonesa, no al recolectar candidatas."""
    try:
        response = requests.get(url, headers=HEADERS_HTTP, timeout=12)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        parrafos = [
            p.get_text(" ", strip=True)
            for p in soup.find_all(["p", "h1", "h2", "h3"])
        ]
        parrafos = [t for t in parrafos if t and len(t) >= 25]

        return " ".join(parrafos)[:5000]

    except Exception as e:
        log.warning(f"No se pudo leer articulo: {url} | {e}")
        return ""


def candidatas_youngguitar(vistos, limite):
    candidatas = []
    try:
        feed = _descargar_feed("https://youngguitar.jp/feed/")

        for entry in feed.entries:
            if len(candidatas) >= limite:
                break
            if not noticia_reciente(entry):
                continue

            titulo = entry.get("title", "")
            link = entry.get("link", "")
            if not titulo or not link or link in vistos:
                continue

            candidatas.append({
                "fuente": "Young Guitar",
                "titulo": titulo,
                "descripcion": limpiar_html(entry.get("summary", "")),
                "link": link,
                "tipo": "japones"
            })

    except Exception as e:
        log.warning(f"Error Young Guitar: {e}")

    return candidatas


def candidatas_rss(fuente, rss_url, vistos, limite):
    candidatas = []

    try:
        feed = _descargar_feed(rss_url)
        for entry in feed.entries:
            if len(candidatas) >= limite:
                break
            if not noticia_reciente(entry):
                continue

            titulo = entry.get("title", "")
            descripcion = limpiar_html(entry.get("summary", ""))
            link = entry.get("link", "")

            if not titulo or not link or link in vistos:
                continue
            if not es_relevante(titulo, descripcion):
                continue

            candidatas.append({
                "fuente": fuente,
                "titulo": titulo,
                "descripcion": descripcion,
                "link": link,
                "tipo": "auto"
            })

    except Exception as e:
        log.warning(f"RSS fallo en {fuente}: {e}")

    if candidatas:
        return candidatas

    # Fallback: scraping de enlaces si el RSS no trajo nada
    try:
        response = requests.get(rss_url, headers=HEADERS_HTTP, timeout=12)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        usados = set()

        for enlace in soup.find_all("a", href=True):
            if len(candidatas) >= limite:
                break

            titulo = enlace.get_text(" ", strip=True)
            href = enlace.get("href", "")

            if not titulo or len(titulo) < 20:
                continue
            if href in usados or href in vistos:
                continue
            if not any(k.lower() in f"{titulo} {href}".lower() for k in KEYWORDS):
                continue

            if href.startswith("/"):
                dominio = urlparse(rss_url)
                href = f"{dominio.scheme}://{dominio.netloc}{href}"

            candidatas.append({
                "fuente": fuente,
                "titulo": titulo,
                "descripcion": f"Nueva publicacion detectada desde {fuente}.",
                "link": href,
                "tipo": "auto"
            })
            usados.add(href)

    except Exception as e:
        log.warning(f"Scraping fallo en {fuente}: {e}")

    return candidatas


def candidatas_de_fuente(fuente, vistos, limite=CANDIDATAS_POR_FUENTE):
    if fuente["tipo"] == "youngguitar":
        return candidatas_youngguitar(vistos, limite)
    return candidatas_rss(fuente["nombre"], fuente["url"], vistos, limite)


# ---------------------------------------------------------------------------
# Preparacion (traduccion estricta)
# ---------------------------------------------------------------------------

def _preparar_japonesa(noticia):
    try:
        titulo_es = traducir_estricto(
            truncar(noticia["titulo"], MAX_LARGO_TITULO, sufijo=""),
            origen="ja",
            validador=sin_japones
        )
    except TraduccionFallida as error:
        log.warning(f"DESCARTADA JA (titulo): {noticia['titulo'][:60]} | {error}")
        return None

    # Scraping perezoso: solo ahora que el titulo ya paso.
    base = obtener_texto_articulo(noticia["link"]) or noticia.get("descripcion", "")
    base = (base or "").strip()[:MAX_TEXTO_ARTICULO_JA]

    resumen_es = ""
    if base:
        try:
            resumen_es = limpiar_html(
                traducir_estricto(base, origen="ja", validador=sin_japones)
            )
            resumen_es = truncar(resumen_es, MAX_LARGO_RESUMEN_JA)
        except TraduccionFallida as error:
            if EXIGIR_RESUMEN_TRADUCIDO:
                log.warning(f"DESCARTADA JA (resumen): {noticia['titulo'][:60]} | {error}")
                return None
            log.warning("Resumen japones sin traducir; se publica solo el titulo.")
            resumen_es = ""

    return titulo_es, resumen_es


def _preparar_occidental(noticia):
    try:
        titulo_es = traducir_estricto(
            truncar(noticia["titulo"], MAX_LARGO_TITULO, sufijo="")
        )
    except TraduccionFallida as error:
        log.warning(f"DESCARTADA (titulo): {noticia['titulo'][:60]} | {error}")
        return None

    descripcion = (noticia.get("descripcion") or "").strip()
    resumen_es = ""

    if descripcion:
        try:
            resumen_es = truncar(
                traducir_estricto(truncar(descripcion, MAX_LARGO_RESUMEN, sufijo="")),
                MAX_LARGO_RESUMEN
            )
        except TraduccionFallida as error:
            if EXIGIR_RESUMEN_TRADUCIDO:
                log.warning(f"DESCARTADA (resumen): {noticia['titulo'][:60]} | {error}")
                return None
            log.warning("Resumen sin traducir; se publica solo el titulo.")
            resumen_es = ""

    return titulo_es, resumen_es


def preparar_noticia(noticia):
    """Traduce y arma el mensaje. Devuelve None si no es publicable."""
    if noticia.get("tipo") == "japones":
        resultado = _preparar_japonesa(noticia)
    else:
        resultado = _preparar_occidental(noticia)

    if resultado is None:
        return None

    titulo_es, resumen_es = resultado

    if resumen_es:
        mensaje = f"<b>{escape(titulo_es)}</b>\n\n{escape(resumen_es)}\n\n{noticia['link']}"
    else:
        mensaje = f"<b>{escape(titulo_es)}</b>\n\n{noticia['link']}"

    return {
        "link": noticia["link"],
        "fuente": noticia["fuente"],
        "titulo_original": noticia["titulo"],
        "mensaje": mensaje
    }


# ---------------------------------------------------------------------------
# Seleccion con rotacion de fuentes
# ---------------------------------------------------------------------------

def seleccionar_lote(historial, indice_inicial):
    """Rota por las fuentes traduciendo una candidata a la vez y quedandose
    solo con las publicables. Devuelve (lote, siguiente_indice)."""
    vistos = set(historial)
    lote = []

    evaluadas = 0
    descartadas = 0
    fallos_consecutivos = 0

    total_fuentes = len(FUENTES_ORDENADAS)
    indice = indice_inicial if 0 <= indice_inicial < total_fuentes else 0
    revisiones = 0
    max_revisiones = total_fuentes * 3

    while len(lote) < NOTICIAS_POR_CORRIDA and revisiones < max_revisiones:
        umbral = MAX_FALLOS_TRAS_UN_EXITO if lote else MAX_FALLOS_SIN_NINGUN_EXITO

        if fallos_consecutivos >= umbral:
            if lote:
                log.error(
                    f"Circuit breaker: {fallos_consecutivos} fallos consecutivos "
                    f"tras {len(lote)} exitos. Proveedor degradado; se publica "
                    f"lo obtenido."
                )
            else:
                log.error(
                    f"Circuit breaker: {fallos_consecutivos} fallos consecutivos "
                    f"sin ninguna traduccion exitosa. Traductor caido."
                )
            break

        if proveedores_agotados():
            log.error("Todos los proveedores de traduccion quedaron agotados.")
            break

        if evaluadas >= MAX_CANDIDATOS_EVALUADOS:
            log.warning(f"Techo de {MAX_CANDIDATOS_EVALUADOS} candidatas evaluadas.")
            break

        fuente = FUENTES_ORDENADAS[indice]
        log.info(f"Revisando {fuente['nombre']} ({len(lote)}/{NOTICIAS_POR_CORRIDA})")

        candidatas = candidatas_de_fuente(fuente, vistos)
        publicadas_de_esta_fuente = 0

        for candidata in candidatas:
            if publicadas_de_esta_fuente >= NOTICIAS_POR_FUENTE:
                break
            if evaluadas >= MAX_CANDIDATOS_EVALUADOS:
                break

            evaluadas += 1
            preparada = preparar_noticia(candidata)

            # Se marca como vista en cualquier caso para no reevaluarla
            # dentro de esta misma corrida. Al NO entrar al historial en
            # disco, seguira disponible en la proxima.
            vistos.add(candidata["link"])

            if preparada is None:
                descartadas += 1
                fallos_consecutivos += 1
                continue

            fallos_consecutivos = 0
            lote.append(preparada)
            publicadas_de_esta_fuente += 1
            log.info(f"[{len(lote)}/{NOTICIAS_POR_CORRIDA}] Lista: "
                     f"{preparada['fuente']} - {preparada['titulo_original'][:60]}")

        indice = (indice + 1) % total_fuentes
        revisiones += 1

    log.info(
        f"Seleccion: {len(lote)} publicables | {evaluadas} evaluadas | "
        f"{descartadas} descartadas por traduccion | {revisiones} fuentes revisadas"
    )

    if len(lote) < NOTICIAS_POR_CORRIDA:
        log.warning(
            f"Solo {len(lote)}/{NOTICIAS_POR_CORRIDA}. Las descartadas NO se "
            f"marcan en el historial y se reintentaran en la proxima corrida."
        )

    return lote, indice


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

    proveedor = autotest()
    if proveedor is None and ABORTAR_SI_NO_HAY_TRADUCTOR:
        log.error(
            "Sin traductor disponible. En modo estricto no se publicaria nada; "
            "se aborta sin tocar el historial ni el estado de rotacion."
        )
        return

    historial = cargar_historial()
    log.info(f"Historial cargado: {len(historial)} noticias")

    estado = cargar_estado_fuentes()
    indice_inicial = estado.get("next_index", 0)

    # Seleccion ANTES del encabezado: evita un encabezado huerfano si
    # ninguna noticia resulta publicable.
    lote, siguiente_indice = seleccionar_lote(historial, indice_inicial)

    guardar_cache()
    guardar_estado_fuentes(siguiente_indice)

    if not lote:
        log.warning("Ninguna noticia resulto publicable. No se envia nada.")
        log.info(resumen_stats())
        return

    enviar_texto(
        "🎸 <b>GUITAR GEAR NEWS</b>\n\n"
        f"<b>Fecha:</b> {datetime.now().strftime('%d/%m/%Y')}\n"
    )
    time.sleep(2)

    enviadas = 0
    fallidas = 0

    for noticia in lote:
        if enviar_texto(noticia["mensaje"]):
            historial.append(noticia["link"])
            guardar_historial(historial)
            enviadas += 1
        else:
            fallidas += 1
            log.warning(f"No se pudo enviar (se reintentara): {noticia['titulo_original']}")
        time.sleep(2)

    log.info(f"Noticias enviadas: {enviadas} | Fallidas: {fallidas}")
    log.info(resumen_stats())


if __name__ == "__main__":
    main()
