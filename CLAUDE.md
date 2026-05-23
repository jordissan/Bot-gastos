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
GROQ_API_KEY          (Llama 3.3 70B texto + Llama 4 Scout visión; .env local en .gitignore)
RESEND_API_KEY        (envío del reporte mensual por correo; .env local en .gitignore)
REPORTE_EMAIL         (destino del reporte mensual; default jor.jorwww@gmail.com)
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

## Versión actual: v_final21

> Novedades v18: voz (Whisper), desglose de productos en tickets, respaldo de presupuesto por
> Subcategoría, consultas de agregación (por año / primer-último-mayor gasto / promedio / día de
> semana / desviación / gasto hormiga), reglas de categorización ampliadas, presupuestos
> `Educación` y `Emergencias` creados en Notion + alias `Deudas`→`Deuda`.

> Novedades v19: filtro de categoría y meses en modos especiales (hormiga, dia_semana, desviacion,
> promedio_mensual). Asterisco `*` en concepto cuando el ticket tiene desglose. Desglose como tabla
> Notion (Producto | Precio). Consultas por fecha real: "¿cuánto gasté ayer?", "¿cuánto gasté la
> semana pasada?" — filtra por Fecha de Notion, suma todos los gastos del período exacto.

> Novedades v20: campo `historico: true` en el plan de consulta. Para preguntas de toda la historia
> ("en total", "desde siempre", "cuánto llevo pagado del Polo", mensualidades del coche), una rama
> nueva en `ejecutar_consulta_finanzas` consulta TODOS los registros desde 2020-01-01 hasta hoy
> (filtro `Fecha` con `and` de on_or_after/on_or_before), ignora el ciclo de mes, y agrega por año.
> `responder_consulta_groq` avisa "🔍 Buscando en toda la historia…" antes de la consulta lenta (15-30s).
> `_formatear_datos_consulta` muestra "Consulta histórica completa" + desglose por año.

> Novedades v21: `/corregir` rediseñado a **panel inline multi-campo híbrido**. Tras elegir el gasto,
> se abre un panel (teclado en línea) con los 6 campos editables (monto, fecha, tarjeta, categoría,
> presupuesto, concepto). Se apilan varios cambios y se aplican TODOS en un solo PATCH al tocar
> "✅ Aplicar". Híbrido: también se acepta una frase ("monto 95 y tarjeta BBVA05") que apila igual.
> Consolidación: se eliminaron `actualizar_notion`, `aplicar_correccion`, `corregir_monto` y los
> estados `CORREGIR_QUE/CAT_GRP/SUBCAT/PRESU/MONTO`; toda escritura pasa por `aplicar_edicion_contextual`
> (única ruta, recalcula Mes al cambiar fecha/tarjeta). Helper único `notificar_pareja` para avisos al
> cónyuge. Menús muertos `menu_que_corregir`/`menu_presupuesto`/`presu_limpio` eliminados.

### Funcionalidades implementadas ✅
- Registro de gastos por texto: `Concepto Monto [Tarjeta] [Fecha]`
- Fecha acepta: `ayer`, `hoy`, `15-may`, `15/05`
- Zona horaria: America/Mexico_City
- Tarjetas: BBVA05, BBVA12, HEYB25, BMEX04, EFVO
- Alerta y confirmación si monto >= $5,000
- Categorización automática (reglas → aprendizaje → similitud → Maps)
- Sistema de aprendizaje en Notion con limpieza automática
- Historial persistente en Notion (últimos 5 por usuario)
- `/corregir` con **panel inline multi-campo** (monto/fecha/tarjeta/categoría/presupuesto/concepto):
  apila varios cambios y aplica todo de una vez en un solo PATCH; acepta también frases de texto
- `/prueba` — simula parseo sin guardar, muestra origen de inferencia
- `/resumen` — resumen del mes activo con porcentajes, monoespaciado
- `/resumen MAY26` — resumen de un mes específico
- `/estadisticas` — comparación mes anterior vs mes activo
- `/top` — top 5 gastos más caros del mes activo (o `/top MAY26`)
- `/buscar <texto>` — busca gastos por concepto (filtro Notion `contains`), últimos 12
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
- OCR `parsear_ticket` reescrito: detecta TOTAL real (último, no subtotal ni "total artículos"),
  reconoce comercios conocidos (`COMERCIOS_OCR`) para el concepto, ignora folios/RFC en encabezado
- Nombres unificados en `USUARIOS_NOMBRES` (Jordi/Nani) — eliminado `_NOMBRES_START` duplicado
- `corregir_elegir` ya no usa `except:` desnudo; reintenta en vez de abortar la conversación
- Servicios usa 🧾 (full-width) en vez de ⚡ para alineación perfecta en code blocks

### Integración Groq (LLM) — capa adicional con fallback total
- **Clasificación + parseo** (`clasificar_mensaje_groq`, Llama 3.3 70B): para mensajes sin formato estricto,
  Groq decide la intención y devuelve `(tipo, payload)` con tipo ∈ {gasto, consulta, edicion, otro, None}.
  Evita registrar gastos por accidente al preguntar. `handle_gasto` clasifica ANTES de registrar.
  (Reemplazó la heurística frágil `_parece_gasto`, ya eliminada.)
- **Consultas en lenguaje natural** (`responder_consulta_groq`): flujo de 2 pasos —
  (1) Groq genera un *plan de consulta* JSON `{modo, meses, categoria, comercio, fecha_desde, fecha_hasta}`,
  (2) según el `modo` se traen los datos de Notion de forma determinística,
  (3) Groq redacta la respuesta con esos datos. Soporta otros meses, comercios, comparaciones y
  **rangos de fecha exactos** ("¿cuánto gasté ayer?", "¿y la semana pasada?", "¿el martes cuánto gasté?").
  - `fecha_desde`/`fecha_hasta` (YYYY-MM-DD): cuando están presentes, `ejecutar_consulta_finanzas`
    filtra directamente por la propiedad `Fecha` de Notion (no por ciclo de mes). Las fechas de
    referencia (ayer, semana pasada, esta semana) se pre-calculan en Python antes de pasar al LLM,
    para que el planner solo necesite copiarlas. `_formatear_datos_consulta` muestra el período
    consultado y el desglose por día cuando hay varios días.
- **Modos de agregación del plan de consulta** (`_datos_consulta_especial`): además de `detalle`:
  - `por_anio` (`_agg_por_anio`): gasto por año desde los rollups de Balance ("¿qué año gasté más?", "cuánto llevo este año").
  - `primero`/`ultimo`/`mayor` (`_gasto_extremo`): gasto más antiguo/reciente/caro (1 query con sort+limit).
  - `ranking_categorias`: top categorías últimos 3 meses ("¿en qué se me va el dinero?").
  - `promedio_mensual` (`_promedio_mensual`): promedio de gasto por mes global (rollups de Balance). **Con `categoria`**: promedio mensual de esa categoría específica (12 meses atrás).
  - `dia_semana` (`_es_finde`): entre semana vs fin de semana. **Acepta `categoria` y `meses`** para filtrar.
  - `desviacion` (`_totales_por_ciclo`): mes activo vs promedio histórico. **Con `categoria`**: compara esa categoría en el mes activo vs su promedio histórico (últimos 7 meses).
  - `hormiga`: suma de gastos < $150. **Acepta `categoria` y `meses`**.
  - `dia_mas_caro`: el día del mes con más gasto. Acepta `categoria` y `meses`.
  - `semana_mes`: gasto por semana del mes (sem1=días 1-7…). Acepta `categoria` y `meses`.
  - `ultima_visita`: última vez en un comercio + histórico del año. Requiere `comercio`. Filtra por `Fecha` directo en Notion (último año).
  - `tendencia`: sube/baja el gasto en los últimos 6 meses. Acepta `categoria`. Calcula pendiente primera vs segunda mitad del período.
  - `mes_mas_caro`: mes más caro de un año. Usa campo `anio` del plan + opcional `categoria`. Consulta todos los meses del año en un solo `ejecutar_consulta_finanzas`.
  - `recurrentes`: gastos que aparecen en 3+ de los últimos 6 meses. Agrupa por concepto normalizado (primeros 18 chars).
  - `dias_sin_gasto`: días desde el último gasto en una categoría. Requiere `categoria`.
  - `promedio_dia`: gasto diario promedio. Para mes activo usa días transcurridos; para histórico usa 30 días/mes.
  - `ranking_frecuencia`: top categorías por número de compras (no por monto).
  - `proyeccion_ahorro`: total + visitas del último año en un comercio → ahorro proyectado anual. Usa filtro `Fecha` directo.
  - Frecuencia de comercio ("¿cuántas veces fui a Starbucks?") = `detalle` + `comercio`.
  - Helpers: `_meses_recientes(n)`, `_gastos_recientes(n, categoria, meses_especificos)`.
  - Plan JSON incluye nuevo campo `anio` (4 dígitos) para preguntas de año específico.
- **Voz unificada** (`handle_voice`, `groq_transcribir` con `whisper-large-v3-turbo`): los mensajes de voz se
  transcriben y pasan por el MISMO clasificador que el texto (gasto/consulta/edición). Registrado como
  entry_point extra de `conv_gasto` (`filters.VOICE | filters.AUDIO`).
- **Respaldo de presupuesto por Subcategoría** (`_presupuesto_desde_subcat`, `SUBCAT_PRESUPUESTO`):
  el usuario borra la columna `Presupuesto` cada mes para resetear su tabla dinámica; `Subcategoria`
  permanece. Si un gasto no tiene `Presupuesto`, el bot deriva la categoría desde la `Subcategoria`.
  Así las consultas por categoría funcionan en cualquier mes histórico.
- **Edición contextual** (`aplicar_edicion_contextual`): tras registrar, frases como "cámbialo a 400",
  "ponlo en restaurantes", "fue con BBVA05" editan el último gasto (de `_ultimo_gasto_usuario`, en RAM).
  Recalcula mes si cambia tarjeta/fecha; aprende si cambia categoría; notifica al otro usuario.
- **Reportes proactivos** (`enviar_reporte`, `_datos_reporte`):
  - **Telegram (simple):** semanal = últimos 7 días; mensual = ciclo recién cerrado (`_mes_anterior(mes_activo)`).
    Lenguaje natural (Groq) con fallback a texto.
  - **Correo (detallado, solo mensual):** `enviar_reporte_email_mensual` → HTML bonito vía Resend
    (`_html_reporte_mensual`): total, barras por categoría con Δ, top gastos, MSI activos (regex `n/total`),
    + sección de recomendaciones y "a tener en cuenta" generada por Groq. Datos en `_datos_mensual_detallado`.
  - Disparo: `/reporte [mensual]` (Telegram a quien pide; mensual además manda el correo) o
    `GET /reporte?secret=<SHORTCUT_SECRET>&tipo=semanal|mensual` (a ambos; mensual también el correo).
  - **Calendario en producción:** semanal lunes 9am, mensual día 5 (ciclo ya cerrado) — vía rutina externa que pega el endpoint.
- **`_extraer_json`**: extrae JSON de respuestas del LLM tolerando fences y prosa alrededor (usado por los 3 parsers).
- **Memoria de contexto** (`_ultimo_gasto_usuario`): guarda último gasto por usuario (en RAM).
- **Insights post-guardado** (`generar_insight_groq`): si una categoría supera $3,000, comenta. Corre en background vía `asyncio.create_task`.
- **OCR de tickets + desglose** (`analizar_ticket_groq`, Llama 4 Scout): la foto va directo al LLM multimodal.
  Extrae comercio, monto, fecha **y la lista de productos** (`productos:[{nombre,precio}]`). El desglose se
  guarda en el CUERPO de la página de Notion (`_bloques_productos` → heading + lista) y se muestra en Telegram
  (`_texto_desglose`). El concepto pasa por `normalizar_comercio` (usa `COMERCIOS_OCR`) en ambos flujos.
  **Si el ticket tiene productos, el concepto lleva `*` al final** (ej: `Walmart*`) — señal visual en Notion de que
  esa página tiene desglose interno. Sin productos, el nombre queda limpio.
  El desglose se guarda como **tabla Notion** (`_bloques_productos` → `table` + `table_row`): columna *Producto* (bold)
  y columna *Precio* (bold), una fila por ítem. Reemplazó la lista de bullets anterior.
  Fallback a Google Vision (`ocr_ticket`+`parsear_ticket`) si Groq falla. Tras registrar por foto, `callback_foto`
  guarda el contexto → habilita edición conversacional sobre ese gasto.
- **Fallback silencioso:** sin `GROQ_API_KEY` o ante cualquier fallo, el bot usa el comportamiento original. Cero regresiones.
- Modelos: `llama-3.3-70b-versatile` (texto), `meta-llama/llama-4-scout-17b-16e-instruct` (visión) y `whisper-large-v3-turbo` (voz). Free tier: 1,000 req/día.

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
3. `conv_corregir` — entry: `/corregir` + CallbackQuery `^cor:`; estado `CORREGIR_PANEL` maneja
   CallbackQuery `^edit:` (botones del panel) y texto (valor de campo o frase híbrida)
4. `conv_eliminar` — entry: `/eliminar`
5. `conv_gasto` — entry: `filters.TEXT`

### Estados de conversación
```python
CONFIRMAR_MONTO  = 1   # monto >= 5000
CONFIRMAR_CAT    = 2   # concepto desconocido
CONFIRMAR_SUBCAT = 3   # subcategoría cuando grupo tiene varias
CORREGIR_ELEGIR  = 10
CORREGIR_PANEL   = 11   # panel inline multi-campo (botones ^edit: + texto híbrido)
PRUEBA_GASTO     = 20
FOTO_CONFIRMAR   = 30
ELIMINAR_CONFIRM = 50
```

### Endpoints HTTP
- `GET /` — health check (responde "OK", para UptimeRobot)
- `POST /webhook` — recibe updates de Telegram
- `POST /log` — recibe gastos del iOS Shortcut/Siri (JSON: `{text, user_id, secret}`)
- `GET /reporte?secret=<SHORTCUT_SECRET>&tipo=semanal|mensual` — dispara el reporte proactivo a ambos
  usuarios (fire-and-forget). Para programar: una rutina externa (cron/Claude Code schedule) que haga GET semanal.

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
| Feature                  | Descripción                                                       | Complejidad |
|--------------------------|-------------------------------------------------------------------|-------------|
| Alertas presupuesto      | Avisar al acercarse al límite mensual por categoría               | Media       |

### Review de optimización — estado (v21)
- **A — Notificación a la pareja duplicada** → ✅ resuelto con helper único `notificar_pareja(context, uid, texto)`
  (aplicado en `aplicar_edicion_contextual`; otros call-sites pueden migrarse después).
- **B — Tres rutas de edición** → ✅ consolidado: `actualizar_notion`, `aplicar_correccion` y `corregir_monto`
  eliminados; toda escritura pasa por `aplicar_edicion_contextual` (recalcula Mes; arregla el bug latente
  de que corregir el monto no recalculaba el ciclo de mes).
- **C — `conv_corregir` con 6 estados** → ✅ reducido a 2 (`CORREGIR_ELEGIR`, `CORREGIR_PANEL`); lógica "Ambas"/"Regresar" eliminada.
- **D — `menu_presupuesto()` hardcodeado** → ✅ eliminado; el panel inline deriva los presupuestos de `PR.keys()`.

---

## Comandos BotFather
```
start        - 👋 Ver instrucciones
resumen      - 📊 Resumen del mes activo
estadisticas - 📈 Comparar este mes vs el anterior
reporte      - 📰 Reporte semanal (o /reporte mensual)
top          - 🏆 Top 5 gastos del mes
buscar       - 🔍 Buscar gastos por concepto
corregir     - ✏️ Corregir un gasto reciente
eliminar     - 🗑️ Eliminar el último gasto
prueba       - 🧪 Simular un gasto sin registrar
cancelar     - ❌ Cancelar acción en curso
```
