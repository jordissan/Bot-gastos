# Integración Groq — Llama 3.3 70B (texto) + Llama 4 Scout (visión) — Bot Gastos

> **Para Claude Code — instrucciones de ejecución:**
> 1. Ejecuta cada sección de este archivo en orden.
> 2. **Antes de empezar**, pide al usuario la `GROQ_API_KEY` con este mensaje exacto: _"Para continuar necesito tu GROQ_API_KEY. Pégala aquí — no la guardaré en ningún archivo del repositorio."_
> 3. Usa la key que el usuario proporcione **solo** para escribirla en el archivo `.env` local (ver Paso 2). Nunca la escribas en `bot.py`, `requirements.txt`, ni en ningún archivo `.md`.
> 4. No modifiques la lógica existente — el LLM actúa como capa adicional con fallback al parser original.

---

## Objetivo

Añadir cinco mejoras al bot usando dos modelos de Groq:

1. **Parseo flexible** — entender mensajes informales como "fui al super, unos 350" o "ayer comí con Nane, fueron como 800 con BBVA05" *(Llama 3.3 70B)*
2. **Memoria de contexto** — recordar el último gasto guardado por usuario para ediciones contextuales *(Llama 3.3 70B)*
3. **Consultas en lenguaje natural** — responder preguntas como "¿cuánto gasté en restaurantes este mes?" *(Llama 3.3 70B)*
4. **Insights post-guardado** — alertar cuando una categoría supera su promedio mensual *(Llama 3.3 70B)*
5. **OCR inteligente de tickets** — reemplaza Google Vision API: Llama 4 Scout recibe la foto directamente y devuelve `{concepto, monto, fecha}` en un solo paso, sin regex ni diccionarios de comercios *(Llama 4 Scout 17B — multimodal)*

**Principio clave:** si `GROQ_API_KEY` no está configurada o cualquier llamada falla, el bot cae al comportamiento original. Cero regresiones. Google Vision sigue como fallback para tickets si Groq falla.

---

## Paso 1 — requirements.txt

Añade esta línea al final de `requirements.txt`:

```
groq==0.11.0
```

---

## Paso 2 — Variable de entorno (dos lugares)

### 2a — Archivo `.env` local (para pruebas)

Crea el archivo `/Users/jordi/Bot-gastos/.env` si no existe, y añade la línea:

```
GROQ_API_KEY=<key_que_el_usuario_proporcionó>
```

Luego verifica que `.env` esté en `.gitignore`. Si el archivo `.gitignore` no existe, créalo con este contenido:

```
.env
__pycache__/
*.pyc
```

> Esto evita que la key llegue a GitHub accidentalmente.

### 2b — Render (producción)

Indica al usuario que añada manualmente la variable en Render:

> "Entra a tu servicio en https://render.com → Environment → Add Environment Variable:
> - Key: `GROQ_API_KEY`
> - Value: `<tu key>`
> Guarda y haz Restart."

Este paso lo hace el usuario — Claude Code no accede al panel de Render.

**Modelos utilizados:**
- Texto: `llama-3.3-70b-versatile` — 1,000 req/día, 12K TPM
- Visión (tickets): `meta-llama/llama-4-scout-17b-16e-instruct` — 1,000 req/día, 30K TPM

Ambos dentro del free tier. Para 2 usuarios con ~100 mensajes/día y fotos ocasionales de tickets, nunca se alcanzarán los límites.

---

## Paso 3 — Cambios en bot.py

### 3.1 — Importaciones

Verifica que `asyncio` esté en los imports de la línea 1. Si no está, añádelo junto a los demás:

```python
import asyncio
```

### 3.2 — Nueva variable de entorno (después de la línea `NOTION_BALANCE_ID = ...`, ~línea 19)

```python
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
```

### 3.3 — Inicialización del cliente Groq (insertar después del bloque de variables de entorno, antes de `USUARIOS_AUTORIZADOS`)

```python
# ── GROQ LLM ──────────────────────────────────────────────────────────────────
_groq_client = None

def get_groq():
    global _groq_client
    if _groq_client is None and GROQ_API_KEY:
        try:
            from groq import Groq
            _groq_client = Groq(api_key=GROQ_API_KEY)
            logger.info("Groq (Llama 3.3 70B) inicializado correctamente")
        except Exception as e:
            logger.error(f"Error inicializando Groq: {e}")
    return _groq_client

def groq_completar(prompt: str, max_tokens: int = 300) -> str | None:
    """Llamada síncrona a Groq (texto). Retorna el texto generado o None si falla."""
    client = get_groq()
    if not client:
        return None
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.warning(f"Groq texto error: {e}")
        return None

def groq_vision(image_bytes: bytes, prompt: str, max_tokens: int = 200) -> str | None:
    """Llamada síncrona a Groq con imagen (Llama 4 Scout). Retorna texto o None si falla."""
    client = get_groq()
    if not client:
        return None
    try:
        img_b64 = base64.b64encode(image_bytes).decode()
        response = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"},
                    },
                    {"type": "text", "text": prompt},
                ],
            }],
            temperature=0.1,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.warning(f"Groq vision error: {e}")
        return None
```

### 3.4 — Memoria de contexto (insertar después de `get_groq()` y `groq_completar()`)

```python
# ── CONTEXTO DE CONVERSACION ──────────────────────────────────────────────────
# Guarda el último gasto guardado por usuario para ediciones contextuales
_ultimo_gasto_usuario: dict[int, dict] = {}

def guardar_contexto(user_id: int, gasto: dict):
    """Guarda el último gasto completo del usuario para uso contextual."""
    _ultimo_gasto_usuario[user_id] = gasto.copy()

def obtener_contexto(user_id: int) -> dict | None:
    return _ultimo_gasto_usuario.get(user_id)
```

### 3.5 — Parser con Groq (insertar después de `parsear_mensaje()`, ~línea 784)

```python
def parsear_mensaje_groq(texto: str) -> dict | None:
    """
    Intenta parsear un mensaje de gasto usando Groq/Llama 3.3 70B.
    Retorna dict con las mismas claves que parsear_mensaje(), o None si falla.
    El resultado pasa por la misma lógica de tarjeta/mes/categoría que el parser original.
    """
    if not GROQ_API_KEY:
        return None

    hoy = datetime.datetime.now(zoneinfo.ZoneInfo("America/Mexico_City")).date()
    tarjetas_validas = ["BBVA05", "BBVA12", "HEYB25", "BMEX04", "EFVO"]

    prompt = f"""Extrae los datos de este mensaje de gasto personal escrito en español mexicano informal. Hoy es {hoy.strftime('%d/%m/%Y')}.

Mensaje: "{texto}"

Responde SOLO con JSON válido, sin texto adicional, sin markdown:
{{
  "concepto": "nombre del comercio o descripción corta en Title Case",
  "monto": número (solo dígitos sin signo $),
  "fecha": "YYYY-MM-DD",
  "tarjeta": "una de {tarjetas_validas} o null"
}}

Reglas:
- Si el mensaje NO es un gasto (es pregunta o comando), responde: {{"error": "no_es_gasto"}}
- Concepto conciso: "Starbucks", "Super", "Comida", "Gasolina", etc.
- Si dice "ayer" resta 1 día a la fecha de hoy. Sin fecha mencionada = hoy.
- Montos aproximados ("como 350", "unos 400") → usa ese número.
- Dos montos → usa el mayor (el total)."""

    raw = groq_completar(prompt, max_tokens=120)
    if not raw:
        return None

    try:
        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)
        data = json.loads(raw)

        if data.get("error") == "no_es_gasto":
            return None

        concepto = data.get("concepto", "").strip()
        monto = data.get("monto")
        fecha_str = data.get("fecha", hoy.strftime("%Y-%m-%d"))
        tarjeta_raw = data.get("tarjeta")

        if not concepto or monto is None:
            return None

        try:
            fecha = datetime.date.fromisoformat(fecha_str)
        except (ValueError, TypeError):
            fecha = hoy

        tarjeta_exp = tarjeta_raw if tarjeta_raw in tarjetas_validas else None
        tarjeta = calcular_tarjeta(fecha, tarjeta_exp)
        mes = calcular_mes(fecha, tarjeta)
        sub, pre, seguro = inferir_categoria(concepto)

        return {
            "concepto": concepto.title(),
            "monto": float(monto),
            "fecha": fecha.strftime("%Y-%m-%d"),
            "tarjeta": tarjeta,
            "mes": mes,
            "subcategoria": sub,
            "presupuesto": pre,
            "seguro": seguro,
        }
    except Exception as e:
        logger.warning(f"Groq parseo fallido: {e} — texto: {texto[:80]}")
        return None
```

### 3.6 — Detector de consultas y respuestas en lenguaje natural (insertar después de `parsear_mensaje_groq()`)

```python
def _parece_gasto_estricto(texto: str) -> bool:
    """
    Retorna True si el texto ya tiene formato estricto (Concepto Monto [opcional])
    y NO necesita LLM. Ahorra llamadas a la API.
    Ejemplos estrictos: "Oxxo 45", "Starbucks 150 BBVA05", "Super 350 ayer"
    """
    tokens = texto.strip().split()
    if len(tokens) < 2:
        return False
    for t in tokens[-3:]:
        try:
            float(t.replace("$", "").replace(",", ""))
            return True
        except ValueError:
            pass
    return False


def _parece_gasto(texto: str) -> bool:
    """Heurística: ¿el mensaje parece un gasto o una pregunta/consulta?"""
    texto_n = normalizar(texto)
    indicadores_consulta = [
        "cuanto", "cuánto", "cuantos", "cual", "cuál",
        "cuando", "cuándo", "qué tal", "como voy",
        "resumen", "estadistica", "compara", "?",
    ]
    return not any(ind in texto_n for ind in indicadores_consulta)


async def responder_consulta_groq(texto: str, user_id: int, update, context) -> bool:
    """
    Si el mensaje parece una consulta en lenguaje natural, la responde usando Groq
    con datos reales de Notion. Retorna True si respondió, False si no era consulta.
    """
    if not GROQ_API_KEY:
        return False

    mes = mes_activo_str()
    mid = buscar_mes_id(mes)
    resumen_ctx = ""
    if mid:
        try:
            gastos = await asyncio.to_thread(
                query_notion_db, NOTION_DATABASE_ID,
                {"property": "Mes", "relation": {"contains": mid}}
            )
            totales = {}
            for g in gastos:
                props = g.get("properties", {})
                monto = props.get("Monto", {}).get("number", 0) or 0
                rel_pre = props.get("Presupuesto", {}).get("relation", [])
                if rel_pre:
                    pr_id = rel_pre[0].get("id", "").replace("-", "")
                    pr_nombre = next((k for k, v in PR.items() if v == pr_id), None)
                    if pr_nombre:
                        totales[pr_nombre] = totales.get(pr_nombre, 0) + monto
            if totales:
                lineas = [f"- {k}: ${v:,.0f}" for k, v in sorted(totales.items(), key=lambda x: x[1], reverse=True)]
                resumen_ctx = f"Gastos de {mes}:\n" + "\n".join(lineas)
                resumen_ctx += f"\nTotal: ${sum(totales.values()):,.0f}"
        except Exception as e:
            logger.warning(f"Error obteniendo contexto para consulta: {e}")

    ultimo = obtener_contexto(user_id)
    ultimo_ctx = ""
    if ultimo:
        ultimo_ctx = f"Último gasto: {ultimo['concepto']} ${ultimo['monto']:,.2f} ({ultimo['subcategoria']})"

    prompt = f"""Eres el asistente del bot de gastos de Jordi y Nane. Responde en español mexicano, breve y directo (máx 2 oraciones). Usa emojis con moderación.

{resumen_ctx or "Sin datos de gastos este mes."}
{ultimo_ctx}

Pregunta: "{texto}"

Si no puedes responder con los datos disponibles, di que no tienes esa información."""

    respuesta = await asyncio.to_thread(groq_completar, prompt, 150)
    if respuesta:
        await update.message.reply_text(respuesta)
        return True
    return False
```

### 3.7 — Función de insights (insertar después de `responder_consulta_groq()`)

```python
async def generar_insight_groq(gasto: dict, user_id: int, context) -> None:
    """
    Después de guardar un gasto, verifica si la categoría supera su promedio.
    Se llama en background — no bloquea la confirmación del gasto.
    Solo actúa si el total acumulado en la categoría supera $3,000.
    """
    if not GROQ_API_KEY:
        return

    presupuesto = gasto.get("presupuesto", "")
    mes_actual = gasto.get("mes", "")
    if not presupuesto or not mes_actual:
        return

    try:
        mid = buscar_mes_id(mes_actual)
        if not mid:
            return
        gastos_mes = query_notion_db(NOTION_DATABASE_ID,
                                     {"property": "Mes", "relation": {"contains": mid}})
        total_categoria = sum(
            (g.get("properties", {}).get("Monto", {}).get("number", 0) or 0)
            for g in gastos_mes
            if next((k for k, v in PR.items()
                     if v == (g.get("properties", {}).get("Presupuesto", {}).get("relation", [{}])[0].get("id", "")).replace("-", "")),
                    None) == presupuesto
        )

        if total_categoria < 3000:
            return

        prompt = f"""Bot de gastos personales. Acaban de registrar:
- {gasto['concepto']}: ${gasto['monto']:,.2f}
- Categoría {presupuesto}, total acumulado este mes: ${total_categoria:,.2f}

¿Hay algo notable? Responde en 1 línea en español o exactamente "sin_insight" si no hay nada relevante."""

        insight = await asyncio.to_thread(groq_completar, prompt, 60)
        if insight and insight.strip() != "sin_insight" and len(insight) > 5:
            await context.bot.send_message(chat_id=user_id, text=f"💡 {insight}")
    except Exception as e:
        logger.debug(f"Insight omitido: {e}")
```

### 3.8 — Modificar `registrar_y_notificar()` para guardar contexto e invocar insight

Busca la función `registrar_y_notificar` (~línea 842). Después de la línea:

```python
threading.Thread(target=guardar_historial_notion, args=(gasto_completo, uid), daemon=True).start()
```

Añade estas dos líneas:

```python
    guardar_contexto(uid, gasto_completo)
    asyncio.create_task(generar_insight_groq(gasto_completo, uid, context))
```

### 3.9 — Modificar el handler principal de texto para usar Groq

En el ConversationHandler de gastos, localiza la función donde se llama `parsear_mensaje(texto)` para procesar el mensaje del usuario (es la primera función del `conv_gasto`, antes de `CONFIRMAR_MONTO`).

Reemplaza la llamada actual:
```python
gasto = parsear_mensaje(texto)
```

Por este bloque:
```python
# Intentar con Groq si el mensaje no tiene formato estricto
gasto = None
if GROQ_API_KEY and not _parece_gasto_estricto(texto):
    gasto = parsear_mensaje_groq(texto)
if gasto is None:
    gasto = parsear_mensaje(texto)
```

### 3.10 — Añadir manejo de consultas en lenguaje natural

En la misma función del handler de texto, añade este bloque **antes** del bloque anterior (antes del `try` que intenta parsear):

```python
    # Consulta en lenguaje natural (no es un gasto)
    if not _parece_gasto_estricto(texto) and not _parece_gasto(texto):
        respondido = await responder_consulta_groq(
            texto, update.effective_user.id, update, context
        )
        if respondido:
            return ConversationHandler.END
```

---

## Paso 4 — Actualizar `registrar_via_shortcut()` (iOS/Siri)

En `registrar_via_shortcut` (~línea 867), reemplaza:
```python
gasto = parsear_mensaje(texto)
```

Por:
```python
gasto = None
if GROQ_API_KEY and not _parece_gasto_estricto(texto):
    gasto = parsear_mensaje_groq(texto)
if gasto is None:
    gasto = parsear_mensaje(texto)
```

Y después de `threading.Thread(target=guardar_historial_notion, ...)`, añade:
```python
    guardar_contexto(user_id, gasto_completo)
```

---

## Paso 5 — Reemplazar Google Vision con Llama 4 Scout (OCR de tickets)

### 5.1 — Nueva función `analizar_ticket_groq()` (insertar después de `parsear_ticket()`, ~línea 518)

```python
def analizar_ticket_groq(image_bytes: bytes) -> dict | None:
    """
    Analiza una foto de ticket con Llama 4 Scout y extrae concepto, monto y fecha.
    Reemplaza el flujo ocr_ticket() + parsear_ticket().
    Retorna dict con las mismas claves que parsear_ticket(), o None si falla.
    """
    if not GROQ_API_KEY:
        return None

    hoy = datetime.datetime.now(zoneinfo.ZoneInfo("America/Mexico_City")).date()

    prompt = f"""Analiza este ticket o recibo de compra y extrae los datos principales. Hoy es {hoy.strftime('%d/%m/%Y')}.

Responde SOLO con JSON válido, sin texto adicional, sin markdown:
{{
  "concepto": "nombre del comercio en Title Case (ej: Walmart, Oxxo, Starbucks)",
  "monto": número con decimales (el TOTAL A PAGAR final, no subtotal ni total de artículos),
  "fecha": "YYYY-MM-DD"
}}

Reglas:
- El monto debe ser el total final que se pagó, incluyendo IVA.
- Si hay varios totales, elige el mayor que sea claramente el total de la compra.
- Si no puedes leer la fecha, usa {hoy.strftime('%Y-%m-%d')}.
- Si no reconoces el comercio, describe brevemente qué tipo de negocio es."""

    raw = groq_vision(image_bytes, prompt, max_tokens=150)
    if not raw:
        return None

    try:
        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)
        data = json.loads(raw)

        concepto = data.get("concepto", "").strip()
        monto = data.get("monto")
        fecha_str = data.get("fecha", hoy.strftime("%Y-%m-%d"))

        if not concepto or monto is None:
            return None

        try:
            fecha = datetime.date.fromisoformat(fecha_str)
        except (ValueError, TypeError):
            fecha = hoy

        return {"concepto": concepto.title(), "monto": float(monto), "fecha": fecha}
    except Exception as e:
        logger.warning(f"Groq ticket fallido: {e}")
        return None
```

### 5.2 — Modificar `handle_foto()` para usar Llama 4 Scout con fallback a Google Vision

Busca la función `handle_foto` (~línea 910). Localiza el bloque donde se llaman `ocr_ticket()` y `parsear_ticket()`. Actualmente luce así:

```python
texto_ocr = ocr_ticket(image_bytes)
if not texto_ocr:
    await msg_espera.edit_text("❌ No pude leer el ticket.")
    return ConversationHandler.END
datos = parsear_ticket(texto_ocr)
```

Reemplázalo por este bloque:

```python
# Intentar con Llama 4 Scout primero (más preciso, sin regex)
datos = analizar_ticket_groq(bytes(image_bytes))

# Fallback a Google Vision si Groq no está disponible o falla
if datos is None:
    texto_ocr = ocr_ticket(bytes(image_bytes))
    if not texto_ocr:
        await msg_espera.edit_text("❌ No pude leer el ticket. Intenta con mejor iluminación.")
        return ConversationHandler.END
    datos = parsear_ticket(texto_ocr)

if not datos or datos.get("monto") is None:
    await msg_espera.edit_text("❌ No encontré el monto en el ticket.")
    return ConversationHandler.END
```

> **Nota:** `image_bytes` viene de `await file.download_as_bytearray()` — es un `bytearray`. La conversión `bytes(image_bytes)` es necesaria para `base64.b64encode`.

---

## Paso 6 — Deploy

1. Abrir en browser antes de subir:  
   `https://api.telegram.org/bot{TOKEN}/deleteWebhook?drop_pending_updates=true`
2. Subir `bot.py` y `requirements.txt` a GitHub arrastrando (nunca copy-paste)
3. En Render → Environment: añadir `GROQ_API_KEY` con la key del usuario
4. Render → Manual Deploy → Restart service
5. Verificar en logs de Render que aparezca: `"Groq (Llama 3.3 70B) inicializado correctamente"`

---

## Comportamiento esperado tras la integración

| Entrada | Modelo | Comportamiento |
|---------|--------|----------------|
| `"Oxxo 45"` | — | Parser original (formato estricto, sin llamada a Groq) |
| `"fui al super, unos 350"` | Llama 3.3 70B | Parsea → guarda Super $350.00 |
| `"ayer comí con Nane, 800 BBVA05"` | Llama 3.3 70B | Parsea → fecha ayer, tarjeta BBVA05 |
| `"¿cuánto llevamos en restaurantes?"` | Llama 3.3 70B | Consulta Notion → responde con datos reales |
| Después de guardar gasto | Llama 3.3 70B | Posible: `"💡 Ya llevas $8,200 en Despensa este mes"` |
| 📸 Foto de ticket | Llama 4 Scout | Extrae concepto + monto + fecha directo de la imagen |
| 📸 Foto (si Groq falla) | Google Vision | Fallback al flujo original de OCR + `parsear_ticket()` |
| Shortcut iOS / Siri | Llama 3.3 70B | Mismo flujo de texto — beneficio automático sin cambios en el iPhone |

---

## Notas importantes

- **Fallback silencioso:** si Groq falla (timeout, cuota, red), el bot usa el comportamiento original sin avisar al usuario.
- **Mensajes estrictos no llaman a Groq:** `_parece_gasto_estricto()` detecta "Oxxo 45" y lo manda directo al parser regex, ahorrando latencia y cuota de API.
- **Groq es síncrono:** `groq_completar()` y `groq_vision()` son bloqueantes. Para parseo de texto es aceptable (~200-400ms). Para insights se usa `asyncio.to_thread`.
- **`base64` ya importado:** el proyecto ya tiene `import base64` en la línea 1 — no hace falta añadirlo.
- **Google Vision sigue en el código:** no se elimina `ocr_ticket()` ni `parsear_ticket()` — quedan como fallback. Solo se añade `analizar_ticket_groq()` y se modifica `handle_foto()`.
- **`GOOGLE_VISION_API_KEY` en Render:** puede dejarse configurada o eliminarse según preferencia. Con Groq activo, no se usará salvo fallo.
- **`asyncio.create_task` para insights:** si el loop no está disponible, envuelve la llamada con `threading.Thread` igual que `guardar_historial_notion`.
- **Edición contextual ("cámbialo a X"):** el contexto se guarda en `_ultimo_gasto_usuario` pero aplicar correcciones automáticas queda como mejora futura.
