# Bot Gastos — Contexto para Claude Code

## Resumen del proyecto
Bot de Telegram personal para registro de gastos familiares conectado a Notion.
Usuarios: Jordi y Nane. Corre en Render.com con Docker (plan gratuito).
UptimeRobot hace ping cada 5 min para evitar que Render duerma el servicio.

---

## Stack técnico
- **Lenguaje:** Python 3.11
- **Librería Telegram:** python-telegram-bot==21.3
- **Servidor:** Render.com — https://bot-gastos-socj.onrender.com
- **Modo:** Webhook (no polling) — más estable en Render free tier
- **Base de datos:** Notion API (gastos, aprendizaje, historial, balance)
- **APIs externas:** Google Maps Places API, Google Vision API (OCR tickets)
- **Repositorio:** github.com/jordissan/Bot-gastos (branch: main)

---

## Variables de entorno (configuradas en Render)
```
TELEGRAM_TOKEN
NOTION_TOKEN
NOTION_DATABASE_ID    = 9c66972a98e74d5b80df8a7e6569e3ca
NOTION_BALANCE_ID     (meses dinamicos — via env var)
GOOGLE_MAPS_API_KEY
GOOGLE_VISION_API_KEY (misma key que Maps, Vision API habilitada en GCloud)
WEBHOOK_SECRET        (opcional)
RENDER_EXTERNAL_URL   = https://bot-gastos-socj.onrender.com
SHORTCUT_SECRET       (para iOS Shortcut)
```

---

## Usuarios autorizados
| Nombre | Telegram ID | Notifica a     |
|--------|-------------|----------------|
| Jordi  | 8663298433  | Nane           |
| Nane   | 8093171397  | Jordi          |

---

## Bases de datos Notion
| BD              | ID                                   | Propósito                            |
|-----------------|--------------------------------------|--------------------------------------|
| Gastos          | `9c66972a98e74d5b80df8a7e6569e3ca`  | Registro principal                   |
| Aprendizaje Bot | `3ba6f37c717948a1a6aeac3b384ff33c`  | Diccionario de categorías aprendidas |
| Historial Bot   | `35f7eb0cbb9280ae8f02f69b4f242298`  | Últimos 5 gastos por usuario         |
| Balance         | via `NOTION_BALANCE_ID` env var      | Meses dinámicos (ENE26, FEB26...)    |

---

## Versión actual: v_final17

### Funcionalidades implementadas ✅
- Registro de gastos por texto: `Concepto Monto [Tarjeta] [Fecha]`
- Fecha acepta: `ayer`, `hoy`, `15-may`, `15/05`
- Zona horaria: America/Mexico_City
- Tarjetas: BBVA05, BBVA12, HEYB25, BMEX04, EFVO
- Alerta y confirmación si monto >= $5,000
- Categorización automática (reglas → aprendizaje → similitud → Maps)
- Sistema de aprendizaje en Notion con limpieza automática
- Historial persistente en Notion (últimos 5 por usuario)
- `/corregir` con navegación completa (Regresar/Cancelar en cada paso)
- `/corregir` ahora incluye opción para corregir el monto (💵 Monto)
- `/prueba` — simula parseo sin guardar, muestra origen de inferencia
- `/resumen` — resumen del mes activo con porcentajes, monoespaciado
- `/resumen MAY26` — resumen de un mes específico
- `/estadisticas` — comparación mes anterior vs mes activo
- `/eliminar` — elimina el último gasto (archiva en Notion)
- Múltiples gastos en un solo mensaje separados por coma
- `confirmar_cat` ahora pregunta subcategoría específica cuando el grupo tiene varias
- Notificaciones cruzadas con botón inline ✏️ Corregir
- iOS Shortcut + Siri via endpoint POST `/log`
- Reintentos automáticos a Notion (3 intentos, 2s entre cada uno)
- Precargar meses al arranque (evita timeouts en `buscar_mes_id`)
- Deep link a Notion en cada confirmación (`[🔗 Ver en Notion](https://...)`)
- OCR de tickets via Google Vision API con preview Confirmar/Cancelar
- Notificaciones cruzadas en gastos múltiples por coma
- `limpiar_aprendizaje` usa PATCH+archived en vez de DELETE (fix Notion API)
- `cmd_estadisticas` usa `asyncio.to_thread` para no bloquear el event loop
- brüm/brum solo en regla Treat (quitado de Restaurantes)
- uber/didi/cabify sin espacio en regla Automovil (fix match exacto)

---

## Formato del mensaje de gasto
```
✅ Gasto guardado

📌 Starbucks
💵 $150.00
🗓️ 17 may 2026
💳 BBVA05
🧾 JUN26
🏷️ Treat
🗂️ Diversión
[🔗 Ver en Notion](https://www.notion.so/...)
```

## Formato del resumen
```
📊 Resumen JUN26

[bloque monoespaciado con emoji + nombre + monto + porcentaje]
🏠 Renta         $9,300  29%
🏦 Deuda         $5,453  17%
...

💵 Total  $31,561
```
Nota: emojis estrechos (⚡ ⛪ 💊) llevan espacio extra para alinear columnas.

---

## Lógica de tarjetas y meses
| Tarjeta | Corte        |
|---------|--------------|
| BBVA05  | día >= 5 → mes+1  |
| BBVA12  | día >= 12 → mes+1 |
| HEYB25  | día >= 25 → mes+2, resto → mes+1 |
| BMEX04  | día >= 4 → mes+1  |
| EFVO    | mes actual        |

**Asignación automática:** días 5-11 → BBVA05, resto → BBVA12

**Mes activo para /resumen:** si hoy >= día 5, mes activo = mes siguiente.
Si hoy < día 5, mes activo = mes actual. (misma lógica que BBVA05)

---

## Arquitectura del código (bot.py)

### Funciones clave
- `precargar_meses()` — carga BD Balance al cache al arrancar. **Llamar ANTES de `app.initialize()`**
- `buscar_mes_id(mes)` — usa cache; si no está, consulta Notion con timeout=15s
- `mes_activo_str()` — calcula el mes de ciclo activo (lógica día 5)
- `inferir_categoria(concepto)` — orden: reglas → aprendizaje → similitud >80% → Maps
- `guardar_notion(gasto)` — guarda en BD Gastos con todas las relaciones
- `registrar_y_notificar(update, context, gasto)` — guarda + confirma + notifica
- `registrar_via_shortcut(texto, user_id)` — mismo flujo sin update/context (iOS/Siri)
- `ocr_ticket(image_bytes)` — llama a Vision API y regresa texto del ticket
- `parsear_ticket(texto)` — extrae concepto, monto y fecha del texto OCR
- `msg_gasto(g, nombre, notion_id)` — genera mensaje con deep link incluido
- `notion_deep_link(page_id)` — genera `https://www.notion.so/{id_sin_guiones}`
- `cmd_resumen(update, context)` — /resumen con paginación y tabla monoespaciada

### ConversationHandlers (orden de registro importante)
1. `conv_prueba` — entry: `/prueba`
2. `conv_foto` — entry: `filters.PHOTO` ← debe ir ANTES que conv_gasto
3. `conv_corregir` — entry: `/corregir` + CallbackQuery `^cor:`
4. `conv_eliminar` — entry: `/eliminar`
5. `conv_gasto` — entry: `filters.TEXT`

### Estados de conversación
```python
CONFIRMAR_MONTO  = 1   # monto >= 5000
CONFIRMAR_CAT    = 2   # concepto desconocido
CONFIRMAR_SUBCAT = 3   # subcategoría cuando grupo tiene varias
CORREGIR_ELEGIR  = 10
CORREGIR_QUE     = 11
CORREGIR_CAT_GRP = 12
CORREGIR_SUBCAT  = 13
CORREGIR_PRESU   = 14
CORREGIR_MONTO   = 15
PRUEBA_GASTO     = 20
FOTO_CONFIRMAR   = 30
ELIMINAR_CONFIRM = 50
```

### Endpoints HTTP
- `GET /` — health check (responde "OK", para UptimeRobot)
- `POST /webhook` — recibe updates de Telegram
- `POST /log` — recibe gastos del iOS Shortcut/Siri (JSON: `{text, user_id, secret}`)

---

## Deploy — procedimiento obligatorio
1. **Antes de cada deploy:** abrir en browser:
   `https://api.telegram.org/bot{TOKEN}/deleteWebhook?drop_pending_updates=true`
2. Subir archivos a GitHub **arrastrando** (nunca copy-paste — evita comillas tipográficas)
3. Render → Manual Deploy → Restart service

---

## Notas técnicas críticas
1. **`precargar_meses()`** se llama en `main()` antes de `app.initialize()`. El cache evita timeouts de Notion durante el registro de gastos.
2. **Loop async:** `app.update_processor._loop = loop` es necesario para que `/log` pueda despachar corrutinas desde el thread del HTTP server.
3. **Historial en Notion, no en RAM:** garantiza persistencia entre reinicios de Render.
4. **Conceptos únicos:** Netflix, Spotify, Walmart, etc. NO se guardan en Aprendizaje.
5. **parse_mode="Markdown":** usar siempre que el mensaje incluya el deep link `[🔗 Ver en Notion](...)`.
6. **conv_foto antes que conv_gasto:** si se invierte el orden, las fotos caen en el handler de texto.
7. **IDs de relación Notion:** llegan con guiones — siempre hacer `.replace("-", "")` antes de comparar con los dicts `SC` y `PR`.
8. **Emojis estrechos en resumen:** ⚡ ⛪ 💊 necesitan un espacio extra después para alinear la tabla monoespaciada. Están definidos en `EMOJI_ESTRECHO`.
9. **Vision API:** necesita `GOOGLE_VISION_API_KEY` en Render, Cloud Vision API habilitada en GCloud, y la key sin restricciones de API (o con Vision API en la lista).

---

## Pendientes futuros 🔲
| Feature              | Descripción                                                       | Complejidad |
|----------------------|-------------------------------------------------------------------|-------------|
| Alertas presupuesto  | Avisar al acercarse al límite mensual por categoría               | Media       |

---

## Comandos BotFather
```
resumen - 📊 Resumen del mes activo
corregir - ✏️ Corregir categoría de un gasto reciente
estadisticas - 📊 Comparar este mes vs el anterior
eliminar - 🗑️ Eliminar el último gasto
cancelar - ❌ Cancelar acción en curso
start - 👋 Ver instrucciones
prueba - 🧪 Simular un gasto sin registrar
```
