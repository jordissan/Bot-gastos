# DEBUGGING.md — Guía de diagnóstico y troubleshooting

> Cuando algo falla, empezar aquí. Síntomas → causa probable → cómo verificar → solución.

---

## Checklist rápido post-deploy

Antes de investigar cualquier fallo, verificar estas 4 cosas en los logs de Render:

```
✅ [APScheduler] Scheduler iniciado. Jobs: reporte_semanal (lun 9am), reporte_mensual (día 5 2pm)
✅ Webhook set successfully
✅ Application started
✅ (sin líneas de ERROR o Traceback al arrancar)
```

---

## Problemas de deploy / arranque

### El bot no responde a ningún mensaje

**Causas posibles (en orden de probabilidad):**
1. Webhook no configurado o apuntando a URL antigua
2. Render no terminó el deploy (sigue corriendo la versión anterior)
3. `TELEGRAM_TOKEN` incorrecto o vacío en env vars de Render

**Diagnóstico:**
```
# Verificar webhook activo:
https://api.telegram.org/bot{TOKEN}/getWebhookInfo
# Debe mostrar: "url": "https://bot-gastos-socj.onrender.com/webhook"
# pending_update_count alto = mensajes acumulados sin procesar
```

**Solución:**
1. Borrar webhook: `https://api.telegram.org/bot{TOKEN}/deleteWebhook?drop_pending_updates=true`
2. Push cualquier cambio a `main` en GitHub → Render hace **Auto Deploy** automáticamente.
3. El bot se autoconfigura el webhook al arrancar.

> ⚠️ Render tiene Auto Deploy activado — nunca se hace deploy manual desde la UI de Render.

### Render "dormido" — primer mensaje tarda 30-60s

El plan gratuito de Render hiberna el servicio si no hay tráfico. UptimeRobot hace ping cada 5 min al endpoint `GET /` para mantenerlo vivo. Si UptimeRobot está caído o el intervalo cambió, el bot puede dormirse.

**Verificar:** https://uptimerobot.com → monitor "Bot Gastos" → debe estar UP con intervalo 5 min.

### `[APScheduler] Scheduler iniciado` no aparece en logs

El scheduler no arrancó. Causas:
- Error de importación de APScheduler (verificar `requirements.txt` tiene `APScheduler==3.10.4`)
- Error en `main()` antes de que llegue a `scheduler.start()`
- Conflicto de event loop con python-telegram-bot

**Solución:** revisar el traceback completo en logs de Render desde el inicio del deploy.

---

## Problemas con Groq

### El bot no entiende mensajes en lenguaje natural (responde "🤔 No entendí")

**Causa 1:** `GROQ_API_KEY` vacía o inválida → cae al parser clásico que es estricto.
**Verificar:** Render → Environment → buscar `GROQ_API_KEY`

**Causa 2:** Quota de Groq agotada (~1,000 req/día en free tier).
**Verificar:** https://console.groq.com → Usage → ver si hay errores 429.
**Solución temporal:** el bot funciona con parser clásico mientras se espera reset (00:00 UTC).

**Causa 3:** El clasificador devolvió `otro` para el mensaje.
**Verificar:** activar logging DEBUG y buscar el raw JSON que devolvió `clasificar_mensaje_groq`.

### Groq alucina datos en consultas (inventa cifras o meses)

El `prompt_resp` tiene una REGLA CRÍTICA que prohíbe esto. Si ocurre:
1. Verificar que el deploy más reciente está activo (el fix se hizo en sesión 2026-05-26)
2. Si persiste, puede ser que `datos` llegue con contenido de un ciclo diferente al esperado
3. Agregar logging del valor de `datos` justo antes de `prompt_resp` para verificar

### El plan de consulta (JSON) llega malformado o vacío

**Síntoma:** logs muestran `Plan de consulta inválido — raw: ...`
**Causa:** Groq devolvió texto en lugar de JSON, o el JSON tiene formato incorrecto.
**Solución:** `_extraer_json` intenta parsear el raw — el raw en el log muestra qué devolvió Groq.
Si el modelo está teniendo problemas, puede ser quota o context window lleno.

---

## Problemas con Notion

### Subcategoría no filtra correctamente (devuelve todos los gastos)

**Causa más probable:** el ID de relación llega con guiones pero se compara sin guiones (o viceversa).
**Verificar en código:**
```python
sc_id = SC.get(subcategoria, "").replace("-", "")  # SC no tiene guiones
rel_sc = props.get("Subcategoria", {}).get("relation", [])
if not any(r.get("id", "").replace("-", "") == sc_id for r in rel_sc):
```
Ambos lados deben tener `.replace("-", "")`.

### El campo Tarjeta no filtra (devuelve gastos de todas las tarjetas)

**Causa:** el campo `Tarjeta` es `rich_text`, no `select`. Si se lee como select, devuelve vacío y el filtro falla silenciosamente.
**Verificar:**
```python
# CORRECTO:
t = "".join(rt.get("plain_text", "") for rt in props.get("Tarjeta", {}).get("rich_text", []))
# INCORRECTO (falla silencioso):
t = props.get("Tarjeta", {}).get("select", {}).get("name", "")
```

### Queries de Notion devuelven 0 resultados inesperadamente

**Verificar en orden:**
1. ¿El filtro `Archivado=False` está presente? (si no, los gastos archivados se excluyen por defecto en algunos modos pero no en otros)
2. ¿El campo `Mes` tiene el formato exacto? (`"JUN26"` no `"Jun26"` ni `"jun26"`)
3. ¿Los IDs de relación tienen guiones removidos?
4. ¿El timeout es suficiente? Queries históricas necesitan `NOTION_T_LONG = 15`

### Error 401 en Notion API

`NOTION_TOKEN` inválido o expirado. Regenerar en https://www.notion.so/my-integrations.

### Error 400 / propiedad no encontrada

El nombre del campo en el filtro no coincide exactamente con el nombre en Notion (case-sensitive).
Usar los nombres exactos de `NOTION_SCHEMA.md`.

### Ticket con productos → "Error al guardar en Notion."

**Causa:** La API `POST /pages` de Notion **no admite** children anidados (tabla → filas). Al incluir la tabla de productos en el mismo `create_page`, Notion devuelve 400.  
**Solución (v26.7.0):** `guardar_notion` ahora crea la página sin children y luego agrega la tabla con `PATCH /blocks/{page_id}/children` (que sí soporta tabla+filas en una sola llamada). Si la tabla falla, el gasto igual queda guardado — solo se pierde el desglose; queda un `logger.warning` con el error real.

### Memoria persistente (`MEM_{uid}`) no carga entre sesiones

**Síntoma:** el bot olvida contexto en cada conversación.
**Causa 1:** La fila `MEM_{uid}` no existe en Historial Bot — `mem_cargar` no encontró nada.
**Verificar:** en Notion → Historial Bot → buscar filas con `Concepto = "MEM_8663298433"` y `UsuarioID = 0`.
**Causa 2:** El JSON en `NotionID` está corrupto o truncado.
**Solución:** si la fila no existe, `mem_guardar` la crea en la próxima acción relevante.

---

## Problemas con Telegram

### Fotos de tickets no se procesan (caen como texto)

**Causa:** `conv_foto` no está registrado ANTES que `conv_gasto` en `main()`.
El orden correcto: conv_prueba → conv_foto → conv_corregir → conv_eliminar → conv_gasto.

### Botón Confirmar/Cancelar de foto queda en "Cargando..." infinito

**Causa:** El bot se reinició (deploy, Render sleeping, crash) DESPUÉS de mostrar el preview. El `ConversationHandler` perdió el estado `FOTO_CONFIRMAR` en memoria. El callback `foto_confirmar` / `foto_cancelar` no tiene ningún handler que lo capture → Telegram muestra el spinner para siempre. `/cancelar` también queda mudo porque era solo fallback del ConversationHandler.

**Solución (v26.8.0):**
- Registrado `CallbackQueryHandler(callback_foto, pattern="^foto_")` como handler global DESPUÉS de `conv_foto`. Cuando el conv está activo, `conv_foto` lo reclama primero; cuando el estado está perdido, el global lo captura y muestra "⚠️ El bot se reinició. Vuelve a enviar la foto."
- Registrado `CommandHandler("cancelar", cancelar)` globalmente. Funciona igual: el conv tiene prioridad si está activo, el global actúa si no.
- `guardar_notion` ahora se llama con `asyncio.to_thread` en `callback_foto` para no bloquear el event loop (dos llamadas síncronas a Notion podían congelar el bot ~16s).

### Botones inline no responden (callback timeout)

Telegram cancela callbacks después de ~60s. Si el bot tardó mucho en responder al mensaje inicial, el botón ya expiró. No hay forma de evitarlo — el usuario debe reenviar el mensaje.

### El bot responde a mensajes duplicados

Webhook recibiendo el mismo update dos veces (Telegram reintenta si no recibe 200 OK a tiempo).
**Solución:** verificar que el endpoint `/webhook` responde 200 rápido. El procesamiento pesado debe ser `asyncio.create_task` o `run_in_executor`.

---

## Problemas de categorización

### El bot siempre pregunta la categoría (nunca aprende)

**Causa 1:** Google Maps API devuelve categoría vacía para ese comercio.
**Causa 2:** El concepto no tiene suficiente similitud (< 80%) con entradas aprendidas.
**Solución:** decirle al bot la categoría una vez → se guarda en BD Aprendizaje con `Usos=1`. La segunda vez con el mismo concepto lo aprende automáticamente.

### El bot categoriza mal un comercio conocido

**Causa:** hay una entrada en BD Aprendizaje con la categoría incorrecta.
**Solución:** registrar el gasto corrigiendo la categoría → el bot actualiza la entrada existente.
Si persiste, ir directamente a Notion → Aprendizaje Bot → buscar el concepto y corregirlo.

### "Restaurantes" se categoriza como Despensa (o viceversa)

Ver `REGLAS_NEGOCIO.md` — "Restaurantes" existe en SC y en PR. El planner debe usar `subcategoria=Restaurantes`. Si el código usa `categoria=Restaurantes`, filtra por el PR (presupuesto) que agrupa todo lo de ese bolsillo, no por la subcategoría específica.

---

## Logs útiles para debugging

```bash
# En Render → Logs, buscar:
"[APScheduler]"          # estado del scheduler
"Plan de consulta"       # queries de consulta NL
"Error"                  # cualquier excepción
"Webhook"                # estado del webhook
"notion_request"         # si se agrega logging de Notion

# Para debugging local:
LOG_LEVEL=DEBUG python bot.py
```

---

## Procedimiento de rollback

Render tiene Auto Deploy — basta con revertir el commit en GitHub:

```bash
git revert HEAD        # crea un commit que deshace el último
git push origin main   # Render lo detecta y despliega automáticamente
```

O si el problema es de varios commits:
```bash
git revert <SHA_BUENO>..HEAD   # revierte el rango
git push origin main
```

No se necesita tocar Render — el Auto Deploy lo maneja.
