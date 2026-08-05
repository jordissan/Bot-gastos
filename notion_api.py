"""Capa HTTP de Notion: auth, reintentos, paginación y cache de meses."""
import logging
import time
import requests
from config import (NOTION_TOKEN, NOTION_API_BASE, NOTION_BALANCE_ID,
                    NOTION_T_SHORT, NOTION_T_DEFAULT, NOTION_T_LONG)

logger = logging.getLogger(__name__)

def nh(): return {"Authorization":f"Bearer {NOTION_TOKEN}","Content-Type":"application/json","Notion-Version":"2022-06-28"}

def notion_rich_text(props: dict, campo: str) -> str:
    rt = props.get(campo, {}).get("rich_text", [])
    return rt[0]["text"]["content"] if rt else ""

def notion_deep_link(page_id: str) -> str:
    pid = page_id.replace("-", "")
    return f"https://www.notion.so/{pid}"

# ── REINTENTOS ───────────────────────────────────────────────────────────────
def notion_request(method, url, **kwargs):
    intentos = 3
    for i in range(intentos):
        try:
            r = requests.request(method, url, **kwargs)
            if r.status_code < 500:
                return r
            logger.warning(f"Notion error {r.status_code}, intento {i+1}/{intentos}")
        except requests.exceptions.RequestException as e:
            logger.warning(f"Notion request exception: {e}, intento {i+1}/{intentos}")
        if i < intentos - 1:
            time.sleep(2)
    return None

def query_notion_db(database_id: str, filter_dict: dict = None) -> list:
    results, cursor = [], None
    body = {"page_size": 100}
    if filter_dict:
        body["filter"] = filter_dict
    while True:
        if cursor:
            body["start_cursor"] = cursor
        r = notion_request("POST", f"{NOTION_API_BASE}/databases/{database_id}/query",
                           headers=nh(), json=body, timeout=NOTION_T_LONG)
        if not r or r.status_code != 200:
            break
        data = r.json()
        results.extend(data.get("results", []))
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
    return results

# ── CACHE DE MESES ────────────────────────────────────────────────────────────
_meses_cache: dict = {}

def precargar_meses():
    if not NOTION_BALANCE_ID:
        logger.warning("NOTION_BALANCE_ID no configurado — meses no precargados")
        return
    try:
        r = requests.post(
            f"{NOTION_API_BASE}/databases/{NOTION_BALANCE_ID}/query",
            headers=nh(), json={"page_size": 50}, timeout=NOTION_T_LONG)
        if r.status_code == 200:
            for page in r.json().get("results", []):
                for prop_val in page.get("properties", {}).values():
                    if prop_val.get("type") == "title":
                        title_list = prop_val.get("title", [])
                        nombre = title_list[0]["text"]["content"] if title_list else ""
                        if nombre:
                            _meses_cache[nombre] = page["id"]
            logger.info(f"Cache de meses cargado: {list(_meses_cache.keys())}")
        else:
            logger.error(f"Error precargando meses: {r.status_code} {r.text[:100]}")
    except Exception as e:
        logger.error(f"Error precargando meses: {e}")

def buscar_mes_id(mes: str):
    if mes in _meses_cache:
        return _meses_cache[mes]
    if not NOTION_BALANCE_ID:
        logger.warning("NOTION_BALANCE_ID no configurado")
        return None
    try:
        r = notion_request("POST",
            f"{NOTION_API_BASE}/databases/{NOTION_BALANCE_ID}/query",
            headers=nh(), json={"page_size": 50}, timeout=NOTION_T_LONG)
        if r and r.status_code == 200:
            for page in r.json().get("results", []):
                for prop_val in page.get("properties", {}).values():
                    if prop_val.get("type") == "title":
                        title_list = prop_val.get("title", [])
                        nombre = title_list[0]["text"]["content"] if title_list else ""
                        if nombre:
                            _meses_cache[nombre] = page["id"]
            if mes in _meses_cache:
                logger.info(f"Mes {mes} encontrado: {_meses_cache[mes]}")
                return _meses_cache[mes]
            logger.error(f"Mes {mes} no encontrado en BD Balance")
        else:
            logger.error(f"Error consultando BD Balance: {r.status_code if r else 'sin respuesta'}")
    except Exception as e:
        logger.error(f"Error en buscar_mes_id({mes}): {e}")
    return None
