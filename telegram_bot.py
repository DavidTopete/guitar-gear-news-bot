import os
import json
import time
import html
import requests
import feedparser
from bs4 import BeautifulSoup
from datetime import datetime
from deep_translator import GoogleTranslator

# ==========================================
# CONFIGURACION
# ==========================================

TOKEN = os.getenv("TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

HISTORY_FILE = "noticias_enviadas.json"
NOTICIAS_POR_FUENTE = 2

# ==========================================
# FUENTES RSS
# ==========================================

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

# ==========================================
# PALABRAS CLAVE
# ==========================================

KEYWORDS = [
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
    "Neural DSP",
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
    "effects"
]

# ==========================================
# CARGAR HISTORIAL
# ==========================================

try:
    if os.path.exists(HISTORY_FILE) and os.path.getsize(HISTORY_FILE) > 0:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            noticias_enviadas = json.load(f)
    else:
        noticias_enviadas = []
except:
    noticias_enviadas = []

# ==========================================
# TELEGRAM
# ==========================================

telegram_message_url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

# ==========================================
# TRADUCTORES
# ==========================================

traductor_auto = GoogleTranslator(source="auto", target="es")
traductor_japones = GoogleTranslator(source="ja", target="es")

# ==========================================
# FUNCIONES
# ==========================================

def limpiar_html(texto):
    soup = BeautifulSoup(texto or "", "html.parser")
    return soup.get_text(separator=" ", strip=True)

def traducir(texto):
    try:
        return traductor_auto.translate(texto)
    except:
        return texto

def traducir_japones(texto):
    try:
        return traductor_japones.translate(texto)
    except:
        return texto

def escape(texto):
    return html.escape(texto or "")

# ==========================================
# RESUMEN DETALLADO
# ==========================================

def crear_resumen(descripcion):

    if not descripcion:
        return (
            "Consulta el enlace para leer la información completa sobre esta noticia. "
        )

    resumen = descripcion.strip()

    if len(resumen) > 700:
        resumen = resumen[:700].strip() + "..."

    if len(resumen) < 250:
        resumen += (
            " Esta noticia puede ser relevante para guitarristas interesados en mejorar su sonido, "
            "conocer nuevos productos, seguir tendencias de gear o descubrir herramientas modernas "
            "para grabación, práctica y presentaciones en vivo."
        )

    return resumen

def crear_resumen_youngguitar(texto_articulo, descripcion_rss=""):

    base = texto_articulo.strip() if texto_articulo else descripcion_rss.strip()

    if not base:
        return (
            "Esta noticia de Young Guitar está relacionada con guitarristas, equipo, "
            "guitarras eléctricas, entrevistas, lanzamientos o novedades del rock y metal japonés. "
            "Consulta el enlace original para revisar todos los detalles publicados por la revista."
        )

    # Limitar texto japonés antes de traducir para evitar errores
    base = base[:3000]

    texto_es = traducir_japones(base)
    texto_es = limpiar_html(texto_es)

    if len(texto_es) > 900:
        texto_es = texto_es[:900].strip() + "..."

    if len(texto_es) < 300:
        texto_es += (
            " Esta publicación puede ser importante para guitarristas interesados en la escena japonesa, "
            "nuevos lanzamientos, entrevistas con músicos, equipo profesional, técnicas de ejecución "
            "o novedades relacionadas con guitarra eléctrica, rock y metal."
        )

    return texto_es

# ==========================================
# FILTRO DE RELEVANCIA
# ==========================================

def es_relevante(titulo, descripcion):

    texto = f"{titulo} {descripcion}".lower()

    return any(
        keyword.lower() in texto
        for keyword in KEYWORDS
    )

# ==========================================
# ENVIAR A TELEGRAM
# ==========================================

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

# ==========================================
# EXTRAER TEXTO DE ARTICULO
# ==========================================

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

            if not texto:
                continue

            if len(texto) < 25:
                continue

            # Evitar textos comunes de navegación
            texto_lower = texto.lower()

            if "cookie" in texto_lower:
                continue

            if "privacy" in texto_lower:
                continue

            if "copyright" in texto_lower:
                continue

            parrafos.append(texto)

        texto_final = " ".join(parrafos)

        return texto_final[:5000]

    except Exception as e:

        print(f"No se pudo extraer texto del artículo: {url}")
        print(e)

        return ""

# ==========================================
# NEURAL DSP
# ==========================================

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

            if link in usados or link in noticias_enviadas:
                continue

            titulo = enlace.get_text(" ", strip=True)

            if not titulo or len(titulo) < 8:
                continue

            noticias.append({
                "titulo": titulo,
                "descripcion": (
                    "Nueva publicación de Neural DSP relacionada con plugins, "
                    "actualizaciones, modeladores de amplificador, tecnología de audio "
                    "o herramientas digitales para guitarristas modernos. "
                    "La noticia puede incluir mejoras de software, nuevos artistas, "
                    "compatibilidad con hardware, presets o cambios importantes "
                    "en productos utilizados por músicos profesionales."
                ),
                "link": link
            })

            usados.add(link)

            if len(noticias) >= NOTICIAS_POR_FUENTE:
                break

    except Exception as e:
        print("Error Neural DSP")
        print(e)

    return noticias

# ==========================================
# YOUNG GUITAR
# ==========================================

def obtener_noticias_youngguitar():

    noticias = []
    usados = set()

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    try:

        feed = feedparser.parse(
            "https://youngguitar.jp/feed/"
        )

        for entry in feed.entries:

            titulo = entry.get("title", "")
            descripcion = limpiar_html(
                entry.get("summary", "")
            )

            link = entry.get("link", "")

            if not titulo or not link:
                continue

            if link in usados or link in noticias_enviadas:
                continue

            texto_articulo = obtener_texto_articulo(link)

            noticias.append({
                "titulo": titulo,
                "descripcion": descripcion,
                "texto_articulo": texto_articulo,
                "link": link
            })

            usados.add(link)

            if len(noticias) >= NOTICIAS_POR_FUENTE:
                return noticias

    except Exception as e:
        print("Error RSS Young Guitar")
        print(e)

    try:

        response = requests.get(
            "https://youngguitar.jp/",
            headers=headers,
            timeout=10
        )

        soup = BeautifulSoup(response.text, "html.parser")

        enlaces = soup.find_all("a", href=True)

        for enlace in enlaces:

            href = enlace.get("href", "")

            if "youngguitar.jp" not in href:
                continue

            if href in usados or href in noticias_enviadas:
                continue

            titulo = enlace.get_text(" ", strip=True)

            if not titulo or len(titulo) < 8:
                continue

            texto_articulo = obtener_texto_articulo(href)

            noticias.append({
                "titulo": titulo,
                "descripcion": (
                    "Noticia publicada por Young Guitar relacionada con guitarristas, "
                    "guitarras eléctricas, entrevistas, lanzamientos, equipo profesional "
                    "o novedades importantes del mundo del rock y metal."
                ),
                "texto_articulo": texto_articulo,
                "link": href
            })

            usados.add(href)

            if len(noticias) >= NOTICIAS_POR_FUENTE:
                break

    except Exception as e:
        print("Error scraping Young Guitar")
        print(e)

    return noticias

# ==========================================
# ENCABEZADO
# ==========================================

fecha_hoy = datetime.now().strftime("%d/%m/%Y")

encabezado = (
    f"🎸 <b>GUITAR GEAR NEWS</b>\n\n"
    f"<b>Fecha:</b> {fecha_hoy}\n"
)

enviar_texto(encabezado)

time.sleep(2)

nuevos_links = []
total_enviadas = 0

# ==========================================
# NEURAL DSP
# ==========================================

for noticia in obtener_noticias_neuraldsp():

    titulo = escape(
        traducir(noticia["titulo"])
    )

    descripcion = traducir(
        noticia["descripcion"]
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

# ==========================================
# YOUNG GUITAR
# ==========================================

for noticia in obtener_noticias_youngguitar():

    titulo = escape(
        traducir_japones(noticia["titulo"])
    )

    resumen_young = crear_resumen_youngguitar(
        noticia.get("texto_articulo", ""),
        noticia.get("descripcion", "")
    )

    resumen = escape(resumen_young)

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

# ==========================================
# FUENTES RSS
# ==========================================

for fuente, rss_url in FUENTES.items():

    print(f"Buscando en {fuente}")

    try:

        feed = feedparser.parse(rss_url)

    except Exception as e:

        print(f"Error leyendo {fuente}: {e}")

        continue

    contador_fuente = 0

    for entry in feed.entries:

        titulo_original = entry.get("title", "")

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

        titulo = escape(
            traducir(titulo_original)
        )

        descripcion = traducir(
            descripcion_original
        )

        resumen = escape(
            crear_resumen(descripcion)
        )

        mensaje = (
            f"<b>{total_enviadas + 1}. {titulo}</b>\n\n"
            f"{resumen}\n\n"
            f"{link}"
        )

        enviar_texto(mensaje)

        nuevos_links.append(link)

        total_enviadas += 1
        contador_fuente += 1

        time.sleep(2)

        if contador_fuente >= NOTICIAS_POR_FUENTE:
            break

# ==========================================
# GUARDAR HISTORIAL
# ==========================================

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
