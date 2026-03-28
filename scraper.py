#!/usr/bin/env python3
"""
Komik Release Bot v3 - Uscite settimanali fumetti e manga italiani
Indipendente da KiloClaw, funziona su GitHub Actions.
Fonti: RSS, curl_cffi, cloudscraper, DuckDuckGo, calendario editoriale.
"""

import json
import os
import sys
import re
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import unquote

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).parent
CONFIG_PATH = SCRIPT_DIR / "config.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("komik")

# Carica config da file o da env vars (per GitHub Actions)
def load_config():
    # Priorità: env vars (GitHub Actions secrets) > config.json
    bot_token = os.environ.get("BOT_TOKEN")
    chat_id = os.environ.get("CHAT_ID")
    topic_id = os.environ.get("TOPIC_ID")

    if bot_token and chat_id:
        return {
            "bot_token": bot_token,
            "chat_id": chat_id,
            "topic_id": int(topic_id) if topic_id else None,
        }

    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return json.load(f)

    log.error("Nessuna config trovata! Imposta BOT_TOKEN e CHAT_ID o crea config.json")
    sys.exit(1)


# ---------------------------------------------------------------------------
# HTTP clients
# ---------------------------------------------------------------------------
def get_session():
    """Crea sessione HTTP con emulazione browser."""
    try:
        from curl_cffi import requests as cffi_requests
        log.info("Usando curl_cffi (Chrome impersonation)")
        return cffi_requests, "curl_cffi"
    except ImportError:
        pass

    try:
        import cloudscraper
        log.info("Usando cloudscraper")
        return cloudscraper, "cloudscraper"
    except ImportError:
        pass

    import requests
    log.warning("Usando requests standard (potrebbe non battere anti-bot)")
    return requests, "requests"


http, http_lib = get_session()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def smart_get(url, **kwargs):
    """GET intelligente: usa impersonation se curl_cffi, altrimenti normale."""
    kwargs.setdefault("headers", HEADERS)
    kwargs.setdefault("timeout", 20)
    if http_lib == "curl_cffi":
        kwargs.setdefault("impersonate", "chrome")
    return http.get(url, **kwargs)


# ---------------------------------------------------------------------------
# Telegram sender
# ---------------------------------------------------------------------------
TELEGRAM_API = "https://api.telegram.org"


def send_telegram(bot_token, chat_id, text, topic_id=None):
    import requests as std_requests
    url = f"{TELEGRAM_API}/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if topic_id:
        payload["message_thread_id"] = topic_id

    resp = std_requests.post(url, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram: {data.get('description', 'unknown')}")
    log.info(f"Messaggio inviato (msg_id={data['result']['message_id']})")
    return data


# ---------------------------------------------------------------------------
# Source 1: RSS Feed
# ---------------------------------------------------------------------------
def scrape_rss():
    releases = []
    feeds = [
        {
            "url": "https://www.mangaforever.net/feed/",
            "name": "MangaForever",
            "keywords": ["uscit", "novità", "volume", "tankobon", "edicola", "libreria", "settimana"],
        },
        {
            "url": "https://fumettologica.it/feed/",
            "name": "Fumettologica",
            "keywords": ["uscit", "novità", "volume", "edicola", "libreria", "settimana", "fumetti in uscita"],
        },
    ]

    for feed in feeds:
        try:
            log.info(f"RSS: {feed['name']}")
            resp = smart_get(feed["url"])
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
            items = root.findall(".//item")
            week_ago = datetime.now() - timedelta(days=7)

            for item in items:
                title = item.findtext("title", "")
                desc = item.findtext("description", "")
                pub_date_str = item.findtext("pubDate", "")
                link = item.findtext("link", "")

                try:
                    pub_date = parsedate_to_datetime(pub_date_str)
                    if pub_date.tzinfo:
                        pub_date = pub_date.replace(tzinfo=None)
                except Exception:
                    pub_date = datetime.now()

                if pub_date < week_ago:
                    continue

                text = (title + " " + desc).lower()
                if any(kw in text for kw in feed["keywords"]):
                    clean_desc = re.sub(r'<[^>]+>', '', desc).strip()
                    releases.append({
                        "casa": feed["name"],
                        "nome": title.strip(),
                        "data": pub_date.strftime("%d/%m/%Y"),
                        "sinossi": clean_desc[:150],
                        "link": link,
                    })
            log.info(f"RSS {feed['name']}: {len([r for r in releases if r['casa'] == feed['name']])} risultati")
        except Exception as e:
            log.error(f"RSS {feed['name']}: {e}")

    return releases


# ---------------------------------------------------------------------------
# Source 2: Web scraping con curl_cffi/cloudscraper
# ---------------------------------------------------------------------------
def scrape_starcomics():
    releases = []
    try:
        today = datetime.now()
        days_ahead = (1 - today.weekday()) % 7 or 7  # prossimo martedì
        next_tue = today + timedelta(days=days_ahead)
        url = f"https://www.starcomics.com/uscite?data={next_tue.strftime('%Y-%m-%d')}"
        log.info(f"Star Comics: {url}")

        resp = smart_get(url)
        if resp.status_code != 200:
            log.warning(f"Star Comics: status {resp.status_code}")
            return releases

        html = resp.text
        log.info(f"Star Comics: ricevuti {len(html)} bytes")

        # Salva per debug
        debug_path = SCRIPT_DIR / "debug_starcomics.html"
        with open(debug_path, "w") as f:
            f.write(html)

        # Cerca pattern JSON embedded o dati strutturati
        json_match = re.search(r'__NEXT_DATA__.*?({.*?})\s*</script>', html, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                log.info(f"Star Comics: trovato __NEXT_DATA__")
                # Naviga la struttura JSON per i prodotti
                _extract_from_json(data, "Star Comics", next_tue.strftime("%d/%m/%Y"), releases)
            except json.JSONDecodeError:
                pass

        # Cerca pattern JSON tipo "products" o "releases"
        for pattern in [
            r'"products"\s*:\s*(\[.*?\])',
            r'"releases"\s*:\s*(\[.*?\])',
            r'"uscite"\s*:\s*(\[.*?\])',
            r'"items"\s*:\s*(\[.*?\])',
        ]:
            match = re.search(pattern, html, re.DOTALL)
            if match:
                try:
                    items = json.loads(match.group(1))
                    for item in items:
                        name = item.get("name") or item.get("title") or item.get("nome", "")
                        if name:
                            releases.append({
                                "casa": "Star Comics",
                                "nome": name.strip(),
                                "data": next_tue.strftime("%d/%m/%Y"),
                                "sinossi": item.get("description", "")[:150],
                            })
                    log.info(f"Star Comics: estratti {len(items)} da JSON")
                    break
                except json.JSONDecodeError:
                    pass

        # Fallback: parsing HTML con regex
        if not releases:
            # Cerca titoli in tag h2/h3/h4 dentro sezioni prodotto
            title_patterns = [
                r'<h[2-4][^>]*class="[^"]*(?:title|name|nome)[^"]*"[^>]*>(.*?)</h[2-4]>',
                r'<a[^>]*href="[^"]*(?:/manga/|/comic/|/catalogo/)[^"]*"[^>]*>(.*?)</a>',
            ]
            seen = set()
            for pattern in title_patterns:
                for match in re.finditer(pattern, html, re.DOTALL | re.IGNORECASE):
                    title = re.sub(r'<[^>]+>', '', match.group(1)).strip()
                    if title and len(title) > 3 and title.lower() not in seen:
                        seen.add(title.lower())
                        releases.append({
                            "casa": "Star Comics",
                            "nome": title,
                            "data": next_tue.strftime("%d/%m/%Y"),
                            "sinossi": "",
                        })

        log.info(f"Star Comics: {len(releases)} uscite totali")
    except Exception as e:
        log.error(f"Star Comics: {e}")

    return releases


def _extract_from_json(data, casa, date_str, releases, depth=0):
    """Ricorsivamente estrai titoli da un oggetto JSON."""
    if depth > 10:
        return
    if isinstance(data, dict):
        for key in ["name", "title", "nome", "titolo"]:
            if key in data and isinstance(data[key], str) and len(data[key]) > 3:
                releases.append({
                    "casa": casa,
                    "nome": data[key].strip(),
                    "data": date_str,
                    "sinossi": str(data.get("description", data.get("descrizione", "")))[:150],
                })
        for v in data.values():
            _extract_from_json(v, casa, date_str, releases, depth + 1)
    elif isinstance(data, list):
        for item in data:
            _extract_from_json(item, casa, date_str, releases, depth + 1)


def scrape_jpop():
    releases = []
    try:
        url = "https://j-pop.it/it/ultime-uscite/"
        log.info(f"J-Pop: {url}")
        resp = smart_get(url)
        if resp.status_code != 200:
            log.warning(f"J-Pop: status {resp.status_code}")
            return releases

        html = resp.text
        debug_path = SCRIPT_DIR / "debug_jpop.html"
        with open(debug_path, "w") as f:
            f.write(html)

        # Cerca product names
        patterns = [
            r'class="product-item-link"[^>]*>(.*?)</a>',
            r'class="product-name"[^>]*>.*?<(?:a|h2)[^>]*>(.*?)</(?:a|h2)>',
            r'"name"\s*:\s*"([^"]+)"',
        ]
        seen = set()
        for pattern in patterns:
            for match in re.finditer(pattern, html, re.DOTALL):
                title = re.sub(r'<[^>]+>', '', match.group(1)).strip()
                if title and len(title) > 3 and title.lower() not in seen:
                    seen.add(title.lower())
                    releases.append({
                        "casa": "J-Pop",
                        "nome": title,
                        "data": datetime.now().strftime("%d/%m/%Y"),
                        "sinossi": "",
                    })

        log.info(f"J-Pop: {len(releases)} prodotti")
    except Exception as e:
        log.error(f"J-Pop: {e}")
    return releases


def scrape_panini():
    releases = []
    try:
        url = "https://www.panini.it/shp_ita_it/catalogsearch/result/?q=uscite+marzo+2026"
        log.info(f"Panini: {url}")
        resp = smart_get(url)
        if resp.status_code != 200:
            log.warning(f"Panini: status {resp.status_code}")
            return releases

        html = resp.text
        debug_path = SCRIPT_DIR / "debug_panini.html"
        with open(debug_path, "w") as f:
            f.write(html)

        patterns = [
            r'class="product-item-link"[^>]*>(.*?)</a>',
            r'"name"\s*:\s*"([^"]+)"',
        ]
        seen = set()
        for pattern in patterns:
            for match in re.finditer(pattern, html, re.DOTALL):
                title = re.sub(r'<[^>]+>', '', match.group(1)).strip()
                if title and len(title) > 5 and title.lower() not in seen:
                    seen.add(title.lower())
                    releases.append({
                        "casa": "Panini Comics",
                        "nome": title,
                        "data": datetime.now().strftime("%d/%m/%Y"),
                        "sinossi": "",
                    })

        log.info(f"Panini: {len(releases)} prodotti")
    except Exception as e:
        log.error(f"Panini: {e}")
    return releases


def scrape_rwedizioni():
    releases = []
    try:
        url = "https://www.rwedizioni.it/"
        log.info(f"RW Edizioni: {url}")
        resp = smart_get(url)
        if resp.status_code != 200:
            return releases

        html = resp.text
        # Cerca link a pagine uscite/novità
        uscite_match = re.search(r'href="([^"]*(?:uscit|novit|new)[^"]*)"', html, re.IGNORECASE)
        if uscite_match:
            uscite_url = uscite_match.group(1)
            if not uscite_url.startswith("http"):
                uscite_url = f"https://www.rwedizioni.it{uscite_url}"
            log.info(f"RW Edizioni: pagina uscite {uscite_url}")
            resp = smart_get(uscite_url)
            html = resp.text

        # Cerca titoli
        patterns = [
            r'<h[2-4][^>]*>(.*?)</h[2-4]>',
            r'class="[^"]*product[^"]*"[^>]*>.*?<(?:a|h[2-4])[^>]*>(.*?)</(?:a|h[2-4])>',
        ]
        seen = set()
        for pattern in patterns:
            for match in re.finditer(pattern, html, re.DOTALL):
                title = re.sub(r'<[^>]+>', '', match.group(1)).strip()
                if title and len(title) > 3 and title.lower() not in seen:
                    seen.add(title.lower())
                    releases.append({
                        "casa": "RW Edizioni",
                        "nome": title,
                        "data": datetime.now().strftime("%d/%m/%Y"),
                        "sinossi": "",
                    })

        log.info(f"RW Edizioni: {len(releases)} risultati")
    except Exception as e:
        log.error(f"RW Edizioni: {e}")
    return releases


# ---------------------------------------------------------------------------
# Source 3: DuckDuckGo
# ---------------------------------------------------------------------------
def scrape_ddg():
    releases = []
    queries = [
        "uscite manga fumetti settimana italia",
        "panini comics star comics uscite questa settimana",
        "j-pop manga uscite marzo 2026",
    ]

    for query in queries:
        try:
            log.info(f"DDG: {query}")
            resp = smart_get(
                "https://html.duckduckgo.com/html/",
                data={"q": query},
                headers={**HEADERS, "Content-Type": "application/x-www-form-urlencoded"},
            )
            # DDG restituisce HTML
            results = re.findall(
                r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                resp.text,
                re.DOTALL,
            )
            for href, title in results[:3]:
                title = re.sub(r'<[^>]+>', '', title).strip()
                href_match = re.search(r'uddg=([^&]+)', href)
                real_url = unquote(href_match.group(1)) if href_match else href

                if title and len(title) > 10:
                    releases.append({
                        "casa": "📰 News",
                        "nome": title,
                        "data": datetime.now().strftime("%d/%m/%Y"),
                        "sinossi": "",
                        "link": real_url,
                    })
            log.info(f"DDG '{query[:30]}...': {len(results[:3])} risultati")
        except Exception as e:
            log.error(f"DDG: {e}")

    return releases


# ---------------------------------------------------------------------------
# Source 4: Calendario editoriale
# ---------------------------------------------------------------------------
CALENDAR_PATH = SCRIPT_DIR / "calendario.json"


def load_calendar():
    if not CALENDAR_PATH.exists():
        return []
    try:
        with open(CALENDAR_PATH) as f:
            data = json.load(f)
        today = datetime.now()
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)
        releases = []
        for item in data:
            try:
                item_date = datetime.strptime(item["data"], "%d/%m/%Y")
                if week_start <= item_date <= week_end:
                    releases.append(item)
            except (ValueError, KeyError):
                continue
        log.info(f"Calendario: {len(releases)} uscite questa settimana")
        return releases
    except Exception as e:
        log.error(f"Calendario: {e}")
        return []


# ---------------------------------------------------------------------------
# Format message
# ---------------------------------------------------------------------------
def format_message(all_releases):
    if not all_releases:
        return (
            "📚 <b>USCITE SETTIMANALI FUMETTI & MANGA</b>\n\n"
            "⚠️ Nessuna uscita trovata questa settimana.\n"
            "I siti potrebbero non essere ancora aggiornati.\n\n"
            "🤖 <i>Komik Release Bot</i>"
        )

    today = datetime.now()
    days_ahead = (1 - today.weekday()) % 7 or 7
    next_tuesday = today + timedelta(days=days_ahead)
    week_str = next_tuesday.strftime("%d/%m/%Y")

    lines = [
        f"📚 <b>USCITE SETTIMANALI FUMETTI & MANGA</b>",
        f"📅 Settimana del {week_str}",
        "─" * 30,
        "",
    ]

    by_publisher = {}
    for r in all_releases:
        casa = r["casa"]
        by_publisher.setdefault(casa, []).append(r)

    for casa, items in by_publisher.items():
        lines.append(f"🏠 <b>{casa}</b>")
        for i, item in enumerate(items, 1):
            nome = item["nome"]
            sinossi = item.get("sinossi", "")
            link = item.get("link", "")
            if link:
                lines.append(f"  {i}. <a href=\"{link}\">{nome}</a>")
            else:
                lines.append(f"  {i}. {nome}")
            if sinossi:
                if len(sinossi) > 150:
                    sinossi = sinossi[:147] + "..."
                lines.append(f"     <i>{sinossi}</i>")
        lines.append("")

    lines.append("🤖 <i>Komik Release Bot</i>")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def run():
    config = load_config()
    bot_token = config["bot_token"]
    chat_id = config["chat_id"]
    topic_id = config.get("topic_id")

    log.info("=== Komik Release Bot v3 - Avvio ===")
    log.info(f"HTTP library: {http_lib}")

    all_releases = []

    # Fonti
    all_releases.extend(scrape_rss())
    all_releases.extend(scrape_starcomics())
    all_releases.extend(scrape_jpop())
    all_releases.extend(scrape_panini())
    all_releases.extend(scrape_rwedizioni())
    all_releases.extend(scrape_ddg())
    all_releases.extend(load_calendar())

    # Deduplica
    seen = set()
    unique = []
    for r in all_releases:
        key = r["nome"].lower().strip()
        if key not in seen and len(key) > 3:
            seen.add(key)
            unique.append(r)

    log.info(f"Totale unico: {len(unique)} uscite")

    # Formatta
    message = format_message(unique)
    log.info(f"Messaggio ({len(message)} chars)")

    # Salva log locale
    log_path = SCRIPT_DIR / "last_run.log"
    with open(log_path, "w") as f:
        f.write(f"=== {datetime.now().isoformat()} ===\n")
        f.write(message)

    # Invia
    try:
        send_telegram(bot_token, chat_id, message, topic_id)
        log.info("=== Invio completato ===")
    except Exception as e:
        log.error(f"Errore invio Telegram: {e}")
        sys.exit(1)


if __name__ == "__main__":
    run()
