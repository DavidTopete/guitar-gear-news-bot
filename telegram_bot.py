import os
import json
import time
import html
import requests
import feedparser

from urllib.parse import urlparse

from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
from deep_translator import GoogleTranslator

TOKEN = os.getenv("TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

HISTORY_FILE = "noticias_enviadas.json"
SOURCE_STATE_FILE = "fuente_estado.json"

NOTICIAS_POR_CORRIDA = 12
NOTICIAS_POR_FUENTE = 1

FUENTES = {

    # REVISTAS
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
    "Blabbermouth": "https://blabbermouth.net/feed",

    # MARCAS
    "Fender News": "https://www.fender.com/articles",
    "Ibanez News": "https://www.ibanez.com/usa/news/",
    "PRS Guitars": "https://prsguitars.com/blog",
    "Line 6 News": "https://line6.com/news/",
    "Fractal Audio News": "https://forum.fractalaudio.com/forums/news.94/",
    "Kemper News": "https://www.kemper-amps.com/news",
    "Boss News": "https://www.boss.info/global/promos/",
    "Neural DSP News": "https://neuraldsp.com/news"
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

    # GENERAL
    "electric guitar",
    "guitar",
    "guitar gear",
    "guitar pedals",
    "guitar amps",
    "guitar amplifier",
    "guitar plugins",
    "guitarristas",
    "guitarists",
    "guitar events",
    "NAMM",

    # GEAR
    "Line 6 Helix",
    "Fractal Audio",
    "Kemper",
    "Boss pedals",
    "Ibanez guitar",
    "Fender guitar",
    "Gibson guitar",
    "PRS guitar",
    "pedalboard",
    "amp modeler",
    "multi effects",
    "plugin",
    "plugins",
    "guitarist",
    "amp",
    "pedal",
    "effects",

    # METAL
    "metal",
    "prog",
    "progressive metal",
    "shred",
    "djent",
    "death metal",
    "thrash metal",

    # GUITARRISTAS
    "John Petrucci",
    "Steve Vai",
    "Joe Satriani",
    "Tosin Abasi",
    "Tim Henson",
    "Plini",
    "Synyster Gates",
    "Zakk Wylde",
    "Yngwie",
    "Paul Gilbert",

    # AUDIO
    "vst",
    "audio interface",
    "IR loader",
    "cab sim",
    "amp sim",
    "firmware",

    # MARCAS
    "Fender",
    "Ibanez",
    "PRS",
    "Line 6",
    "Helix",
    "Fractal",
    "Axe-Fx",
    "FM3",
    "FM9",
    "Kemper",
    "Boss",
    "Neural DSP",
    "Quad Cortex",
    "firmware update",
    "preset",
    "cabinet IR",
    "amp capture",
    "profiling amp",
    "tone match",
    "modeler",
    "modeling",
    "multi-effects"
]

try:

    if os.path.exists(HISTORY_FILE) and os.path.getsize(HISTORY_FILE) > 0:

        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            noticias_enviadas = json.load(f)

    else:
        noticias_enviadas = []

except:
    noticias_enviadas = []

try:

    if os.path.exists(SOURCE_STATE_FILE) and os.path.getsize(SOURCE_STATE_FILE) > 0:

        with open(SOURCE_STATE_FILE, "r", encoding="utf-8") as f:
            estado_fuentes = json.load(f)

    else:
        estado_fuentes = {"next_index": 0}

except:
    estado_fuentes = {"next_index": 0}

telegram_message_url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

traductor_auto = GoogleTranslator(
    source="auto",
    target="es"
)

traductor_japones = GoogleTranslator(
    source="ja",
    target="es"
)

def limpiar_html(texto):

    soup = BeautifulSoup(
        texto or "",
        "html.parser"
    )

    return soup.get_text(
        separator=" ",
        strip=True
    )

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

def traducir(texto):

    try:
        return traductor_auto.translate(texto)

    except:
        return texto

def traducir_japones(texto):

    if not texto:
        return ""

    try:

        traducido = traductor_japones.translate(texto)

        if traducido and not contiene_japones(traducido):
            return traducido

    except:
        pass

    try:

        traducido = traductor_auto.translate(texto)

        if traducido:
            return traducido

    except:
        pass

    return texto

def escape(texto):
    return html.escape(texto or "")

def noticia_reciente(entry):

    try:

        if hasattr(entry, "published_parsed") and entry.published_parsed:

            fecha_noticia = datetime(
                *entry.published_parsed[:6],
                tzinfo=timezone.utc
            )

        elif hasattr(entry, "updated_parsed") and entry.updated_parsed:

            fecha_noticia = datetime(
                *entry.updated_parsed[:6],
                tzinfo=timezone.utc
            )

        else:
            return True

        hace_dos_semanas = (
            datetime.now(timezone.utc)
            - timedelta(days=14)
        )

        return fecha_noticia >= hace_dos_semanas

    except:
        return True

def crear_resumen(descripcion):

    if not descripcion:

        return (
            "Consulta el enlace para leer la noticia completa."
        )

    resumen = descripcion.strip()

    if len(resumen) > 800:
        resumen = resumen[:800].strip() + "..."

    return resumen

def crear_resumen_youngguitar(texto_articulo, descripcion_rss=""):

    base = (
        texto_articulo.strip()
        if texto_articulo
        else descripcion_rss.strip()
    )

    if not base:

        return (
            "Consulta el enlace original para revisar la publicación completa."
        )

    base = base[:3000]

    texto_es = traducir_japones(base)
    texto_es = limpiar_html(texto_es)

    if len(texto_es) > 1000:
        texto_es = texto_es[:1000].strip() + "..."

    return texto_es

def es_relevante(titulo, descripcion):

    texto = f"{titulo} {descripcion}".lower()

    return any(
        keyword.lower() in texto
        for keyword in KEYWORDS
    )

def enviar_texto(texto):

    if len(texto) > 3900:
        texto = texto[:3900] + "..."

    payload = {
        "chat_id": CHAT_ID,
        "text": texto,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }

    r = requests.post(
        telegram_message_url,
        data=payload
    )

    print(r.text)

def obtener_texto_articulo(url):

    try:

        headers = {
            "User-Agent": "Mozilla/5.0"
        }

        response = requests.get(
            url,
            headers=headers,
            timeout=12
        )

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        for tag in soup([
            "script",
            "style",
            "nav",
            "footer",
            "header",
            "aside"
        ]):
            tag.decompose()

        parrafos = []

        for p in soup.find_all([
            "p",
            "h1",
            "h2",
            "h3"
        ]):

            texto = p.get_text(
                " ",
                strip=True
            )

            if not texto:
                continue

            if len(texto) < 25:
                continue

            parrafos.append(texto)

        return " ".join(parrafos)[:5000]

    except Exception as e:

        print(f"No se pudo leer artículo: {url}")
        print(e)

        return ""

def obtener_noticia_youngguitar():

    noticias = []

    try:

        feed = feedparser.parse(
            "https://youngguitar.jp/feed/"
        )

        for entry in feed.entries:

            if not noticia_reciente(entry):
                continue

            titulo = entry.get("title", "")
            descripcion = limpiar_html(
                entry.get("summary", "")
            )

            link = entry.get("link", "")

            if not titulo or not link:
                continue

            if link in noticias_enviadas:
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

        print("Error Young Guitar")
        print(e)

    return noticias

def obtener_noticia_rss(fuente, rss_url):

    noticias = []

    print(f"Buscando en {fuente}")

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    # ==========================================
    # RSS
    # ==========================================

    try:

        feed = feedparser.parse(rss_url)

        if feed.entries:

            for entry in feed.entries:

                if not noticia_reciente(entry):
                    continue

                titulo_original = entry.get(
                    "title",
                    ""
                )

                descripcion_original = limpiar_html(
                    entry.get("summary", "")
                )

                link = entry.get("link", "")

                if not titulo_original or not link:
                    continue

                if link in noticias_enviadas:
                    continue

                if not es_relevante(
                    titulo_original,
                    descripcion_original
                ):
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

        print(f"RSS fallo en {fuente}")
        print(e)

    # ==========================================
    # SCRAPING WEB
    # ==========================================

    try:

        response = requests.get(
            rss_url,
            headers=headers,
            timeout=12
        )

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        enlaces = soup.find_all(
            "a",
            href=True
        )

        usados = set()

        for enlace in enlaces:

            titulo = enlace.get_text(
                " ",
                strip=True
            )

            href = enlace.get("href", "")

            if not titulo:
                continue

            if len(titulo) < 20:
                continue

            if href in usados:
                continue

            if href in noticias_enviadas:
                continue

            texto_revision = (
                f"{titulo} {href}"
            ).lower()

            if not any(
                keyword.lower() in texto_revision
                for keyword in KEYWORDS
            ):
                continue

            if href.startswith("/"):

                dominio = urlparse(rss_url)

                href = (
                    f"{dominio.scheme}://"
                    f"{dominio.netloc}{href}"
                )

            noticias.append({
                "fuente": fuente,
                "titulo": titulo,
                "descripcion": (
                    f"Nueva publicación detectada desde {fuente}."
                ),
                "link": href,
                "tipo": "auto"
            })

            usados.add(href)

            if len(noticias) >= NOTICIAS_POR_FUENTE:
                return noticias

    except Exception as e:

        print(f"Scraping fallo en {fuente}")
        print(e)

    return noticias

def obtener_noticia_de_fuente(fuente):

    if fuente["tipo"] == "youngguitar":
        return obtener_noticia_youngguitar()

    return obtener_noticia_rss(
        fuente["nombre"],
        fuente["url"]
    )

def guardar_estado_fuentes(next_index):

    with open(
        SOURCE_STATE_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            {"next_index": next_index},
            f,
            ensure_ascii=False,
            indent=4
        )

fecha_hoy = datetime.now().strftime(
    "%d/%m/%Y"
)

noticias_finales = []
links_usados = set()

total_fuentes = len(FUENTES_ORDENADAS)

start_index = estado_fuentes.get(
    "next_index",
    0
)

if start_index >= total_fuentes:
    start_index = 0

indice_actual = start_index
fuentes_revisadas = 0

while (
    len(noticias_finales) < NOTICIAS_POR_CORRIDA
    and fuentes_revisadas < total_fuentes
):

    fuente = FUENTES_ORDENADAS[indice_actual]

    nuevas = obtener_noticia_de_fuente(
        fuente
    )

    for noticia in nuevas:

        link = noticia.get("link", "")

        if not link:
            continue

        if link in links_usados:
            continue

        noticias_finales.append(noticia)

        links_usados.add(link)

        if (
            len(noticias_finales)
            >= NOTICIAS_POR_CORRIDA
        ):
            break

    indice_actual = (
        indice_actual + 1
    ) % total_fuentes

    fuentes_revisadas += 1

guardar_estado_fuentes(indice_actual)

if not noticias_finales:

    print(
        "No hay noticias nuevas para publicar."
    )

    exit()

encabezado = (
    f"🎸 <b>GUITAR GEAR NEWS</b>\n\n"
    f"<b>Fecha:</b> {fecha_hoy}\n"
)

enviar_texto(encabezado)

time.sleep(2)

nuevos_links = []
total_enviadas = 0

for noticia in noticias_finales:

    if noticia.get("tipo") == "japones":

        titulo = escape(
            traducir_japones(
                noticia["titulo"]
            )
        )

        resumen_young = (
            crear_resumen_youngguitar(
                noticia.get(
                    "texto_articulo",
                    ""
                ),
                noticia.get(
                    "descripcion",
                    ""
                )
            )
        )

        resumen = escape(
            resumen_young
        )

    else:

        titulo = escape(
            traducir(
                noticia["titulo"]
            )
        )

        descripcion = traducir(
            noticia.get(
                "descripcion",
                ""
            )
        )

        resumen = escape(
            crear_resumen(
                descripcion
            )
        )

    link = noticia["link"]

    mensaje = (
        f"<b>{total_enviadas + 1}. "
        f"{titulo}</b>\n\n"
        f"{resumen}\n\n"
        f"{link}"
    )

    enviar_texto(mensaje)

    nuevos_links.append(link)

    total_enviadas += 1

    time.sleep(2)

noticias_enviadas.extend(
    nuevos_links
)

noticias_enviadas = (
    noticias_enviadas[-2000:]
)

with open(
    HISTORY_FILE,
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        noticias_enviadas,
        f,
        ensure_ascii=False,
        indent=4
    )

print(
    f"Noticias enviadas correctamente: "
    f"{total_enviadas}"
)
