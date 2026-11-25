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

def _cargar_meses_balance() -> bool:
    """Lee TODAS las filas de Balance (paginado) y llena `_meses_cache`.

    Antes se pedía una sola página de 50: con 51+ meses en Balance algún ciclo
    quedaba fuera del cache y los gastos se guardaban sin relación de Mes.
    """
    paginas = query_notion_db(NOTION_BALANCE_ID)
    for page in paginas:
        for prop_val in page.get("properties", {}).values():
            if prop_val.get("type") == "title":
                title_list = prop_val.get("title", [])
                t0 = title_list[0] if title_list else {}
                nombre = t0.get("plain_text") or t0.get("text", {}).get("content", "")
                if nombre:
                    _meses_cache[nombre.strip()] = page["id"]
    return bool(paginas)

def precargar_meses():
    if not NOTION_BALANCE_ID:
        logger.warning("NOTION_BALANCE_ID no configurado — meses no precargados")
        return
    try:
        if _cargar_meses_balance():
            logger.info(f"Cache de meses cargado ({len(_meses_cache)}): {sorted(_meses_cache.keys())}")
        else:
            logger.error("Error precargando meses: Balance vacío o sin respuesta")
    except Exception as e:
        logger.error(f"Error precargando meses: {e}")

def buscar_mes_id(mes: str):
    if mes in _meses_cache:
        return _meses_cache[mes]
    if not NOTION_BALANCE_ID:
        logger.warning("NOTION_BALANCE_ID no configurado")
        return None
    try:
        _cargar_meses_balance()
        if mes in _meses_cache:
            logger.info(f"Mes {mes} encontrado: {_meses_cache[mes]}")
            return _meses_cache[mes]
        logger.error(f"Mes {mes} no encontrado en BD Balance — hay que crear la fila en Notion")
    except Exception as e:
        logger.error(f"Error en buscar_mes_id({mes}): {e}")
    return None

def meses_conocidos() -> list:
    """Códigos de ciclo ya cargados en cache (ej. ['AGO26','JUL26']).
    Acceso público al cache: `_meses_cache` es privado y NO viaja con `import *`,
    así que bot.py debe leerlo por aquí (ver v28.1.0)."""
    return sorted(_meses_cache.keys())
