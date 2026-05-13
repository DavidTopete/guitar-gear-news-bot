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
# FUENTES
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
    "plugins"
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
# TRADUCTOR
# ==========================================

traductor = GoogleTranslator(source="auto", target="es")

# ==========================================
# FUNCIONES
# ==========================================

def limpiar_html(texto):
    soup = BeautifulSoup(texto or "", "html.parser")
    return soup.get_text(separator=" ", strip=True)

def traducir(texto):
    try:
        return traductor.translate(texto)
    except:
        return texto

def escape(texto):
    return html.escape(texto or "")

def crear_resumen(descripcion):
    if not descripcion:
        return (
            "Consulta el enlace para leer la información completa sobre esta noticia "
            "relacionada con guitarra eléctrica, equipo, amplificadores, pedales, plugins "
            "o tecnología para guitarristas."
        )

    resumen = descripcion.strip()

    if len(resumen) > 420:
        resumen = resumen[:420].strip() + "..."

    return resumen

def es_relevante(titulo, descripcion):
    texto = f"{titulo} {descripcion}".lower()

    return any(
        keyword.lower() in texto
        for keyword in KEYWORDS
    )

def enviar_texto(texto):
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
# NEURAL DSP SCRAPING
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
            href = enlace.get(
                "href",
                ""
            )

            if "/news/" not in href:
                continue

            if href.startswith("/"):
                link = "https://neuraldsp.com" + href
            else:
                link = href

            if link in usados or link in noticias_enviadas:
                continue

            titulo = enlace.get_text(
                " ",
                strip=True
            )

            if not titulo or len(titulo) < 8:
                continue

            noticias.append({
                "titulo": titulo,
                "descripcion": (
                    "Nueva publicación de Neural DSP relacionada con plugins, "
                    "actualizaciones, modeladores de amplificador, tecnología de audio "
                    "o herramientas digitales para guitarristas modernos."
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
# ENCABEZADO
# ==========================================

fecha_hoy = datetime.now().strftime("%d/%m/%Y")

encabezado = (
    f"🎸 <b>GUITAR GEAR NEWS</b>\n\n"
    f"<b>Fecha:</b> {fecha_hoy}\n"
    f"<b>Cobertura:</b> últimas noticias disponibles\n\n"
    f"<b>Temas:</b>\n"
    f"Guitarras\n"
    f"Amplificadores\n"
    f"Pedales\n"
    f"Plugins\n"
    f"Modeladores\n"
    f"Gear para guitarristas"
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
        traducir(
            noticia["titulo"]
        )
    )

    descripcion = traducir(
        noticia["descripcion"]
    )

    resumen = escape(
        crear_resumen(
            descripcion
        )
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

        titulo_original = entry.get(
            "title",
            ""
        )

        descripcion_original = limpiar_html(
            entry.get(
                "summary",
                ""
            )
        )

        link = entry.get(
            "link",
            ""
        )

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
            traducir(
                titulo_original
            )
        )

        descripcion = traducir(
            descripcion_original
        )

        resumen = escape(
            crear_resumen(
                descripcion
            )
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

noticias_enviadas.extend(
    nuevos_links
)

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
