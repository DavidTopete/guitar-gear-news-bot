import os
import json
import time
import html
import requests
import feedparser
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
from deep_translator import GoogleTranslator

TOKEN = os.getenv("TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

HISTORY_FILE = "noticias_enviadas.json"
NOTICIAS_POR_FUENTE = 1

FUENTES = {
    "Guitar World": "https://www.guitarworld.com/feeds/all",
    "Ultimate Guitar": "https://www.ultimate-guitar.com/rss/news",
    "Premier Guitar": "https://www.premierguitar.com/feeds/news",
    "MusicRadar": "https://www.musicradar.com/rss",
    "Guitar Player": "https://www.guitarplayer.com/feeds/all",
    "Reverb News": "https://reverb.com/news/rss",
    "Sweetwater News": "https://www.sweetwater.com/insync/feed/",
    "Gearnews Guitar": "https://www.gearnews.com/zone/guitar/feed/",
    "Guitar.com": "https://guitar.com/feed/"
}

KEYWORDS = [
    "electric guitar", "guitar", "guitar gear", "guitar pedals",
    "guitar amps", "guitar amplifier", "guitar plugins",
    "guitarristas", "guitarists", "guitar events", "NAMM",
    "Neural DSP", "Line 6 Helix", "Fractal Audio", "Kemper",
    "Boss pedals", "Ibanez guitar", "Fender guitar",
    "Gibson guitar", "PRS guitar", "pedalboard",
    "amp modeler", "multi effects", "plugin", "plugins",
    "guitarist", "amp", "pedal", "effects"
]

try:
    if os.path.exists(HISTORY_FILE) and os.path.getsize(HISTORY_FILE) > 0:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            noticias_enviadas = json.load(f)
    else:
        noticias_enviadas = []
except:
    noticias_enviadas = []

telegram_message_url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

traductor_auto = GoogleTranslator(source="auto", target="es")
traductor_japones = GoogleTranslator(source="ja", target="es")

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

    return (
        "No se pudo traducir automáticamente el texto completo de esta noticia japonesa. "
        "Consulta el enlace original para revisar la publicación completa."
    )

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
            return False

        hace_dos_semanas = datetime.now(timezone.utc) - timedelta(days=14)

        return fecha_noticia >= hace_dos_semanas

    except Exception as e:
        print("Error validando fecha")
        print(e)

        return False

def crear_resumen(descripcion):
    if not descripcion:
        return "Consulta el enlace para leer la información completa sobre esta noticia."

    resumen = descripcion.strip()

    if len(resumen) > 700:
        resumen = resumen[:700].strip() + "..."

    return resumen.strip()

def crear_resumen_youngguitar(texto_articulo, descripcion_rss=""):
    base = texto_articulo.strip() if texto_articulo else descripcion_rss.strip()

    if not base:
        return "Consulta el enlace original para revisar la publicación completa."

    base = base[:3000]

    texto_es = traducir_japones(base)
    texto_es = limpiar_html(texto_es)

    if contiene_japones(texto_es):
        texto_es = (
            "La publicación original está en japonés y no pudo traducirse completamente de forma automática. "
            "Consulta el enlace original para revisar todos los detalles."
        )

    if len(texto_es) > 900:
        texto_es = texto_es[:900].strip() + "..."

    return texto_es.strip()

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

        soup = BeautifulSoup(response.text, "html.parser")

        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        parrafos = []

        for p in soup.find_all(["p", "h1", "h2", "h3"]):
            texto = p.get_text(" ", strip=True)

            if not texto or len(texto) < 25:
                continue

            texto_lower = texto.lower()

            if "cookie" in texto_lower:
                continue

            if "privacy" in texto_lower:
                continue

            if "copyright" in texto_lower:
                continue

            parrafos.append(texto)

        return " ".join(parrafos)[:5000]

    except Exception as e:
        print(f"No se pudo extraer texto del artículo: {url}")
        print(e)

        return ""

def obtener_noticias_neuraldsp():
    noticias = []

    try:
        headers = {
            "User-Agent": "Mozilla/5.0"
        }

        response = requests.get(
            "https://neuraldsp.com/news",
            headers=headers,
            timeout=10
        )

        soup = BeautifulSoup(response.text, "html.parser")
        enlaces = soup.find_all("a", href=True)
        usados = set()

        for enlace in enlaces:
            href = enlace.get("href", "")

            if "/news/" not in href:
                continue

            if href.startswith("/"):
                link = "https://neuraldsp.com" + href
            else:
                link = href

            if link in usados:
                continue

            if link in noticias_enviadas:
                continue

            titulo = enlace.get_text(" ", strip=True)

            if not titulo or len(titulo) < 8:
                continue

            noticias.append({
                "titulo": titulo,
                "descripcion": (
                    "Nueva publicación de Neural DSP relacionada con plugins, "
                    "actualizaciones, modeladores de amplificador, tecnología de audio "
                    "o herramientas digitales para guitarristas modernos."
                ),
                "link": link,
                "tipo": "auto"
            })

            usados.add(link)

            if len(noticias) >= NOTICIAS_POR_FUENTE:
                break

    except Exception as e:
        print("Error Neural DSP")
        print(e)

    return noticias

def obtener_noticias_youngguitar():
    noticias = []
    usados = set()

    try:
        feed = feedparser.parse("https://youngguitar.jp/feed/")

        for entry in feed.entries:
            if not noticia_reciente(entry):
                continue

            titulo = entry.get("title", "")
            descripcion = limpiar_html(entry.get("summary", ""))
            link = entry.get("link", "")

            if not titulo or not link:
                continue

            if link in usados:
                continue

            if link in noticias_enviadas:
                continue

            texto_articulo = obtener_texto_articulo(link)

            noticias.append({
                "titulo": titulo,
                "descripcion": descripcion,
                "texto_articulo": texto_articulo,
                "link": link,
                "tipo": "japones"
            })

            usados.add(link)

            if len(noticias) >= NOTICIAS_POR_FUENTE:
                return noticias

    except Exception as e:
        print("Error RSS Young Guitar")
        print(e)

    return noticias

def obtener_noticias_rss(fuente, rss_url):
    noticias = []

    print(f"Buscando en {fuente}")

    try:
        feed = feedparser.parse(rss_url)

    except Exception as e:
        print(f"Error leyendo {fuente}: {e}")

        return noticias

    for entry in feed.entries:
        if not noticia_reciente(entry):
            continue

        titulo_original = entry.get("title", "")
        descripcion_original = limpiar_html(entry.get("summary", ""))
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
            "titulo": titulo_original,
            "descripcion": descripcion_original,
            "link": link,
            "tipo": "auto"
        })

        if len(noticias) >= NOTICIAS_POR_FUENTE:
            break

    return noticias

def agregar_noticias(lista_base, nuevas, links_usados):
    for noticia in nuevas:
        link = noticia.get("link", "")

        if not link:
            continue

        if link in links_usados:
            continue

        lista_base.append(noticia)
        links_usados.add(link)

    return lista_base

fecha_hoy = datetime.now().strftime("%d/%m/%Y")

noticias_finales = []
links_usados = set()

agregar_noticias(
    noticias_finales,
    obtener_noticias_neuraldsp(),
    links_usados
)

agregar_noticias(
    noticias_finales,
    obtener_noticias_youngguitar(),
    links_usados
)

for fuente, rss_url in FUENTES.items():
    agregar_noticias(
        noticias_finales,
        obtener_noticias_rss(fuente, rss_url),
        links_usados
    )

if not noticias_finales:
    print("No hay noticias nuevas para publicar.")
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
            traducir_japones(noticia["titulo"])
        )

        resumen_young = crear_resumen_youngguitar(
            noticia.get("texto_articulo", ""),
            noticia.get("descripcion", "")
        )

        resumen = escape(resumen_young)

    else:
        titulo = escape(
            traducir(noticia["titulo"])
        )

        descripcion = traducir(
            noticia.get("descripcion", "")
        )

        resumen = escape(
            crear_resumen(descripcion)
        )

    link = noticia["link"]

    mensaje = (
        f"<b>{total_enviadas + 1}. {titulo}</b>\n\n"
        f"{resumen}\n\n"
        f"{link}"
    )

    enviar_texto(mensaje)

    nuevos_links.append(link)

    total_enviadas += 1

    time.sleep(2)

noticias_enviadas.extend(nuevos_links)

noticias_enviadas = noticias_enviadas[-1500:]

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
