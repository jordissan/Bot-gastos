# Bot Gastos — Contexto para Claude Code

> **⚠️ PROTOCOLO DE INICIO DE SESIÓN — leer en este orden:**
> 1. `handoff.md` — qué quedó pendiente, qué cambió, qué sigue.
> 2. `memoria.md` — decisiones de diseño, conceptos del dominio, lecciones aprendidas.
> 3. Este archivo — arquitectura técnica y referencia del bot.
> 4. `NOTION_SCHEMA.md` — solo si vas a tocar código de Notion (schema, IDs, tipos de campos).
> 5. `REGLAS_NEGOCIO.md` — solo si vas a tocar categorización, tarjetas o ciclos.
> 6. `DEBUGGING.md` — solo si algo está fallando.
> 7. `TESTING.md` — solo después de un deploy.

---

## Resumen del proyecto

Bot de Telegram personal de Jordi y Nane para registrar gastos, conectado a Notion como fuente de verdad. Entiende lenguaje natural (texto y voz), lee tickets por foto, responde preguntas sobre finanzas y manda reportes automáticos. Corre 24/7 en Render.com con Docker.

**Versión actual:** 26.2.0  
**Esquema:** `MAJOR` = nuevo dominio/capacidad estructural · `MINOR` = feature individual · `PATCH` = fix o ajuste

---

## Stack técnico

| Componente | Detalle |
|------------|---------|
| Lenguaje | Python 3.11 |
| Telegram | python-telegram-bot==21.3, modo **webhook** (no polling) |
| Servidor | Render.com free tier — https://bot-gastos-socj.onrender.com |
| Keep-alive | UptimeRobot ping cada 5 min |
| Base de datos | Notion API (6 BDs) |
| IA texto | Groq — Llama 3.3 70B (`llama-3.3-70b-versatile`) |
| IA visión | Groq — Llama 4 Scout (`meta-llama/llama-4-scout-17b-16e-instruct`) |
| IA voz | Groq — Whisper (`whisper-large-v3-turbo`) |
| Categorización | Google Maps Places API |
| OCR fallback | Google Vision API |
| Correo | Resend API |
| Scheduler | APScheduler==3.10.4 (`AsyncIOScheduler`) |
| Repositorio | github.com/jordissan/Bot-gastos (branch: main) |

Groq free tier: ~1,000 req/día. **Si falta `GROQ_API_KEY` o falla, el bot cae al parser clásico sin romperse.**

---

## Variables de entorno (configuradas en Render)

```
TELEGRAM_TOKEN
NOTION_TOKEN
NOTION_DATABASE_ID      = 9c66972a98e74d5b80df8a7e6569e3ca
NOTION_BALANCE_ID       (meses dinámicos — via env var)
GOOGLE_MAPS_API_KEY
GOOGLE_VISION_API_KEY   (misma key que Maps; Vision API habilitada en GCloud)
WEBHOOK_SECRET          (opcional)
RENDER_EXTERNAL_URL     = https://bot-gastos-socj.onrender.com
SHORTCUT_SECRET         (para iOS Shortcut y el endpoint /reporte)
GROQ_API_KEY            (.env local, en .gitignore)
RESEND_API_KEY
REPORTE_EMAIL           (destino del reporte mensual; default jor.jorwww@gmail.com)
```

---

## Usuarios

| Nombre | Telegram ID | Notifica a |
|--------|-------------|------------|
| Jordi  | 8663298433  | Nane       |
| Nane   | 8093171397  | Jordi      |

Cada gasto/edición que hace uno se notifica al otro. **Finanzas conjuntas — nunca separar por usuario en consultas.**

---

## Bases de datos Notion

| BD | ID | Propósito |
|----|-----|-----------|
| Gastos | `9c66972a98e74d5b80df8a7e6569e3ca` | Registro principal — fuente de verdad |
| Aprendizaje Bot | `3ba6f37c717948a1a6aeac3b384ff33c` | Diccionario de categorías aprendidas |
| Historial Bot | `35f7eb0cbb9280ae8f02f69b4f242298` | Snapshot últimos 5 gastos + filas `MEM_{uid}` para memoria persistente |
| Balance | via `NOTION_BALANCE_ID` | Meses dinámicos (ENE26, FEB26…) con rollups |
| Metas Bot | `cf7906bcccfd4690b7ef8c1e996a8e17` | Metas por ciclo/presupuesto + `presupuesto="INGRESO"` para ingreso estimado |
| Alias Bot | `9000583a97204e6db41994ec96bf5a71` | Alias personales aprendidos en conversación |

---

## Lógica de tarjetas y ciclos de pago

El campo **Mes** en Notion = mes de *pago*, no de compra. Formato: `MAY26`, `JUN26`.

| Tarjeta | Corte | Regla |
|---------|-------|-------|
| BBVA05 | día 5 | día ≥ 5 → mes+1 |
| BBVA12 | día 12 | día ≥ 12 → mes+1 |
| HEYB25 | día 25 | día ≥ 25 → mes+2; resto → mes+1 |
| BMEX04 | día 4 | día ≥ 4 → mes+1 |
| EFVO | — | mes actual siempre |

- **Asignación automática** (sin tarjeta explícita): días 5–11 → BBVA05, resto → BBVA12.
- **Mes activo** (para `/resumen`): hoy ≥ día 5 → mes siguiente; hoy < 5 → mes actual.

---

## Qué puede hacer el bot

### 1. Registrar un gasto — 5 vías de entrada

1. **Texto libre** — "gasté 200 en el súper", "pagué 350 de gasolina ayer"
2. **Formato estricto** — `Concepto Monto [Tarjeta] [Fecha]` (ej. `Starbucks 150 BBVA05 ayer`) — salta Groq, más rápido
3. **Voz** — transcripción Whisper → mismo flujo que texto
4. **Foto de ticket** — Llama 4 Scout extrae comercio, monto, fecha y lista de productos
5. **iOS Shortcut / Siri** — endpoint `POST /log`

Detalles:
- Fechas: `ayer`, `hoy`, `15-may`, `15/05`. Sin fecha = hoy. Zona: America/Mexico_City.
- Monto ≥ $5,000 → pide confirmación con botones inline ✅ / ❌.
- Concepto desconocido → abre menú grupo → subcategoría.
- Varios gastos en un mensaje: por coma (`super 350, gasolina 500`) o lenguaje natural (`multi_gasto`).
- Cada confirmación incluye `🔗 Ver en Notion`.

**Alertas en background (solo al que registró):**
- `generar_insight_groq`: si la categoría supera ~$3,000 acumulado, comenta.
- `verificar_hormiga`: gasto < $150 en Treat/Abarrotes/Restaurantes/Gasolina con 3+ en esa cat esta semana.
- `detectar_anomalia`: monto > max(2.5·media, media+2·std) sobre 5+ registros del mismo concepto.

### 2. El cerebro — cómo entiende cada mensaje

`_procesar_conversacion` decide qué hacer:
1. Si **no** es formato estricto y hay Groq, `clasificar_mensaje_groq` clasifica en: `gasto / multi_gasto / consulta / edición / meta / ingreso / alias / otro`.
2. Según intención: consulta → `responder_consulta_groq`; edición → `aplicar_edicion_contextual`; meta → `guardar_meta`; ingreso → `guardar_meta(..., "INGRESO", ...)` + muestra posición financiera.
3. Sin Groq → parser clásico `parsear_mensaje`.

`_parece_gasto_estricto`: devuelve `True` (salta Groq) solo si ≤ 9 tokens y alguno de los últimos 3 es número.

**Memoria conversacional persistente:**
- **RAM** (`_memoria_ram`): `turns` (últimos 8), `last_results`, `last_query`, `last_gasto`.
- **Notion** (Historial Bot): filas `MEM_8663298433` y `MEM_8093171397` (UsuarioID=0), JSON en campo `NotionID`. Sobrevive reinicios.
- `mem_cargar(uid)`: cold-start, carga Notion → RAM una vez por sesión.
- `mem_guardar(uid)`: persiste RAM → Notion en background. TTL 2h para `last_results`.
- `_manejar_referencia()`: intercepta "dame el link", "el más caro", "elimínalo" antes de Groq.
- **Plan carryover**: `last_query` se inyecta al planner para resolver "¿y la semana pasada?".

### 3. Consultas en lenguaje natural (Hub Financiero)

Flujo de 2 pasos — el LLM nunca inventa cifras:
1. Groq genera **plan JSON**: `{modo, meses, categoria, subcategoria, tarjeta, comercio, fecha_desde, fecha_hasta, anio, historico}`.
2. `ejecutar_consulta_finanzas` / `_datos_consulta_especial` traen datos **determinísticos** de Notion.
3. Groq redacta la respuesta solo con esos datos.

**Filtros disponibles:**
- `categoria` — bolsa de presupuesto (Despensa, Restaurantes, Automovil…)
- `subcategoria` — tipo específico (Abarrotes, Gasolina, Treat…)
- `tarjeta` — BBVA05 / BBVA12 / HEYB25 / BMEX04 / EFVO
- `comercio` — búsqueda de texto en concepto
- `meses` — códigos de ciclo de pago (JUN26, MAY26…)
- `fecha_desde` / `fecha_hasta` — rango exacto (ignora `meses`)
- `historico: true` — toda la historia desde 2020

**Modos disponibles:**

| Pregunta | modo |
|----------|------|
| "¿cuánto gasté ayer / la semana pasada?" | `detalle` + `fecha_desde/hasta` |
| "¿cuánto gasté este mes en Abarrotes?" | `detalle` + `subcategoria` |
| "¿cuánto gasté con BBVA12?" | `detalle` + `tarjeta` |
| "¿cuánto llevo pagado del Polo?" | `historico: true` |
| "¿qué año gasté más?" | `por_anio` |
| "el gasto más caro / más antiguo" | `mayor` / `primero` |
| "¿en qué se me va el dinero?" | `ranking_categorias` |
| "¿dónde compro más seguido?" | `ranking_frecuencia` |
| "¿cuánto gasto al mes / día en promedio?" | `promedio_mensual` / `promedio_dia` |
| "¿gasto más entre semana o fin de semana?" | `dia_semana` |
| "¿qué día del mes gasto más?" | `dia_mas_caro` |
| "¿cómo se reparte por semana del mes?" | `semana_mes` |
| "¿voy por encima de mi promedio?" | `desviacion` |
| "¿está subiendo mi gasto en Abarrotes?" | `tendencia` |
| "¿qué mes de 2025 fue el más caro?" | `mes_mas_caro` |
| "¿cuáles son mis gastos fijos?" | `recurrentes` |
| "¿cuánto llevo sin gastar en X?" | `dias_sin_gasto` |
| "¿cuál es mi gasto hormiga?" | `hormiga` |
| "¿cuándo fui por última vez a Costco?" | `ultima_visita` |
| "¿cuánto ahorraría si dejo Starbucks?" | `proyeccion_ahorro` |
| "¿qué MSIs tengo activos?" | `msi_tracker` |
| "¿dónde puedo ahorrar?" | `oportunidades_ahorro` |
| "¿cómo voy este mes?" | `posicion_financiera` |
| "¿cuánto hemos ganado vs gastado?" | `tendencia_ingresos` |

Consulta histórica avisa "🔍 Buscando en toda la historia…" (puede tardar 15-30 s).

### 4. Ingresos estimados (freelance)

Jordi y Nane tienen ingresos variables. El bot maneja esto con ingresos estimados por ciclo:
- "Este mes esperamos ganar $45,000" → `guardar_meta(uid, "INGRESO", monto, ciclo)` en Metas Bot.
- Cualquier usuario puede declararlo; se lee de ambos UIDs (finanzas conjuntas).
- Modos `posicion_financiera` y `tendencia_ingresos` lo consumen.
- Si no hay ingreso declarado, lo indica y pide que se declare.

### 5. MSI Tracker

MSIs con formato `"Concepto X/Total"` (ej. `"MacBook Pro 4/18"`).
`msi_tracker` detecta todos los MSIs históricos, encuentra el pago más reciente de cada uno, calcula restantes y compromiso mensual total.

### 6. Tickets por foto (OCR)

- Llama 4 Scout extrae comercio, monto, fecha y lista de productos `[{nombre, precio}]`.
- Desglose se guarda como tabla Notion (Producto | Precio) dentro de la página del gasto.
- Concepto lleva `*` al final si hay productos (ej. `Walmart*`).
- Preview con botones Confirmar / Cancelar antes de guardar.
- Fallback a Google Vision si Groq falla.

### 7. Editar y borrar

- **`/corregir`**: muestra últimos 5 gastos combinados (ambos usuarios). Eliges número → panel inline con 6 campos editables (monto, fecha, tarjeta, categoría, presupuesto, concepto). Todos los cambios en un solo PATCH.
- **Edición contextual**: justo después de registrar, "cámbialo a 400" / "ponlo en restaurantes" edita el `last_gasto` en RAM.
- Ambas rutas usan `aplicar_edicion_contextual` — única función de escritura.
- **`/eliminar`**: archiva el último gasto (pide confirmación).

### 8. Reportes automáticos

- **Semanal** (Telegram): últimos 7 días — lunes 9am MX (`job_reporte_semanal`).
- **Mensual** (Telegram + correo HTML): ciclo recién cerrado — día 5 2pm MX (`job_reporte_mensual`).
- Ambos incluyen desglose por tarjeta. Redactados por Groq con fallback a texto.
- Disparo manual: `/reporte [mensual]` o `GET /reporte?secret=...&tipo=semanal|mensual`.

### 9. Voz

Whisper transcribe → `_procesar_conversacion`. Todo lo que se puede hacer escribiendo se puede hacer hablando.

### 10. Categorización y aprendizaje

`inferir_categoria(concepto)`: reglas → aprendizaje (BD) → similitud >80% → Google Maps.
Lo aprendido se guarda en Aprendizaje Bot (con limpieza automática de entradas de 1 solo uso).

---

## Comandos disponibles

| Comando | Qué hace |
|---------|----------|
| `/start` | Bienvenida e instrucciones |
| `/resumen [MES]` | Tabla por categoría + proyección de cierre + narrativa (Groq) |
| `/estadisticas` | Mes anterior vs mes activo |
| `/top [MES]` | Top 5 gastos más caros del mes |
| `/buscar <texto>` | Busca por concepto (últimos 12, con suma) |
| `/corregir` | Panel inline para editar gasto reciente |
| `/eliminar` | Archiva el último gasto |
| `/reporte [mensual]` | Dispara reporte semanal o mensual |
| `/prueba` | Simula parseo sin guardar |
| `/cancelar` | Cancela acción en curso |

```
# BotFather
start        - 👋 Ver instrucciones
resumen      - 📊 Resumen del mes activo
estadisticas - 📈 Comparar este mes vs el anterior
reporte      - 📰 Reporte semanal (o /reporte mensual)
top          - 🏆 Top 5 gastos del mes
buscar       - 🔍 Buscar gasto
corregir     - ✏️ Corregir un gasto reciente
eliminar     - 🗑️ Eliminar el último gasto
prueba       - 🧪 Simular un gasto
cancelar     - ❌ Cancelar acción en curso
```

---

## Formatos de mensaje

**Confirmación de gasto:**
```
✅ Gasto guardado

📌 Starbucks
💵 $150.00
🗓️ 17/MAY/26
💳 BBVA05
🧾 JUN26
🏷️ Treat
🗂️ Diversión
🔗 Ver en Notion
```

**Fechas:** `_fecha_compacta` → `18/MAY/26` (estándar). `_fecha_larga` → `18 de mayo, 2026` (solo correo mensual).

---

## Arquitectura del código (bot.py)

### Funciones clave

| Función | Rol |
|---------|-----|
| `_procesar_conversacion(update, context, texto, uid)` | Cerebro compartido de texto y voz |
| `clasificar_mensaje_groq(texto, ultimo, historial)` | Clasifica intención (gasto / consulta / edición / meta / ingreso / alias / otro) |
| `responder_consulta_groq(...)` | Consultas NL: plan JSON → datos Notion → redacción |
| `ejecutar_consulta_finanzas(plan)` | **Única función que trae datos para consultas.** Filtros: categoria, subcategoria (SC dict), tarjeta (rich_text), comercio, fecha, historico |
| `_datos_consulta_especial(modo, plan)` | Modos de agregación; propaga subcategoria_id a todos los modos |
| `_gastos_recientes(n, categoria, meses, subcategoria_id)` | Lista de gastos con filtro de subcategoría |
| `_agg_ciclo(mes)` | Agrega gastos de un ciclo; devuelve `por_tarjeta` |
| `aplicar_edicion_contextual(...)` | **Única ruta de escritura** para editar gastos |
| `guardar_meta(uid, presupuesto, limite, ciclo)` | Upsert en Metas Bot (`presupuesto="INGRESO"` para ingreso estimado) |
| `cargar_meta(uid, presupuesto, ciclo)` | Lee límite o ingreso específico |
| `mem_cargar(uid)` / `mem_guardar(uid)` | Memoria persistente Notion |
| `_manejar_referencia()` | Intercepta referencias contextuales antes de Groq |
| `enviar_reporte(tipo)` | Reporte Telegram + correo; incluye desglose por tarjeta |
| `_ciclo_a_rango_calendario(ciclo)` | Helper: "JUN26" → (date(2026,6,1), date(2026,6,30)) |

### ConversationHandlers (el orden importa)

1. `conv_prueba` — `/prueba`
2. `conv_foto` — `filters.PHOTO` ← **debe ir ANTES que conv_gasto**
3. `conv_corregir` — `/corregir`
4. `conv_eliminar` — `/eliminar`
5. `conv_gasto` — `filters.TEXT` + `filters.VOICE | filters.AUDIO`

### Endpoints HTTP

| Endpoint | Uso |
|----------|-----|
| `GET /` | Health check (UptimeRobot) |
| `POST /webhook` | Updates de Telegram |
| `POST /log` | Gastos desde iOS Shortcut/Siri |
| `GET /reporte?secret=...&tipo=semanal\|mensual` | Dispara reporte a ambos usuarios |
| `POST /propuesta_mes` | Apertura de ciclo con botones inline |

---

## Notas técnicas críticas

1. **IDs de relación Notion:** llegan con guiones → `.replace("-", "")` antes de comparar con `SC`/`PR`.
2. **Tarjeta en Notion:** campo `rich_text` (no select) → `props.get("Tarjeta", {}).get("rich_text", [])`.
3. **Restaurantes en SC y PR:** existe en ambos dicts. El planner usa `subcategoria=Restaurantes` por default. Nunca poner `subcategoria` + `categoria` simultáneamente.
4. **Ingreso estimado:** `presupuesto="INGRESO"` en Metas Bot. Se busca en ambos UIDs (finanzas conjuntas).
5. **MSI formato:** regex `^(.+?)\s+(\d{1,2})\s*/\s*(\d{1,2})\s*$` sobre el concepto.
6. **gastos_raw:** máximo 20 resultados, ordenados por monto desc.
7. **parse_mode="Markdown":** usar solo cuando el mensaje incluya deep links o negritas.
8. **conv_foto antes que conv_gasto:** si se invierte, las fotos caen en el handler de texto.
9. **Fallback silencioso:** sin `GROQ_API_KEY` el bot usa el parser clásico — nunca se rompe.
10. **Anti-alucinación en `prompt_resp`:** incluye REGLA CRÍTICA explícita prohibiendo usar datos de turnos anteriores o inventar meses.

---

## Deploy — procedimiento obligatorio

1. Borrar webhook: `https://api.telegram.org/bot{TOKEN}/deleteWebhook?drop_pending_updates=true`
2. Subir a GitHub **arrastrando** el archivo (nunca copy-paste — evita comillas tipográficas).
3. Render → Manual Deploy → Restart service.
4. Verificar en logs: `[APScheduler] Scheduler iniciado.`

---

## Archivos del proyecto

| Archivo | Cuándo leer | Propósito |
|---------|------------|-----------|
| `handoff.md` | Siempre al inicio | Estado operativo de la última sesión |
| `memoria.md` | Siempre al inicio | Decisiones, conceptos, lecciones |
| `CLAUDE.md` | Siempre al inicio | Arquitectura técnica (este archivo) |
| `NOTION_SCHEMA.md` | Al tocar código Notion | Schema completo, IDs, tipos de campos, dicts SC/PR |
| `REGLAS_NEGOCIO.md` | Al tocar categorización/tarjetas | Reglas de dominio, casos especiales, gastos fijos |
| `DEBUGGING.md` | Cuando algo falla | Síntomas → causas → soluciones |
| `TESTING.md` | Después de un deploy | Checklist de verificación manual |
| `bot.py` | Al escribir código | Código principal — todo el bot |
| `requirements.txt` | Al cambiar dependencias | Dependencias Python |
| `Dockerfile` | Al cambiar infra | Imagen Docker para Render |

Archivos externos relacionados:
- `/Users/jordi/Documents/Claude/Projects/Hub Financiero/CLAUDE.md` — instrucciones del hub financiero
- `/Users/jordi/Documents/Claude/Projects/Hub Financiero/plan_automatizacion_reportes.md` — referencia histórica

---

## Cómo trabajar en este proyecto

- Respuestas directas, sin postambles. Una sola pregunta si hay duda.
- No confirmar de más — si ya está documentado, actuar directamente.
- Cuando Jordi aclara su intención, escuchar primero antes de implementar lo que "parece más inteligente".
- Siempre verificar fecha real del sistema. "Ayer" = día anterior real.
- Deploy en orden: borrar webhook → push a GitHub → Manual Deploy en Render.
- GitHub: arrastrar archivos — nunca copy-paste (evita comillas tipográficas que rompen el código Python).

---

## ⚠️ PROTOCOLO DE CIERRE DE SESIÓN — ejecutar siempre, sin esperar que Jordi lo pida

Al terminar cualquier sesión en la que se haya tocado código o tomado decisiones, actualizar los
documentos antes del último commit. **Jordi no debería tener que pedir esto nunca.**

### Qué actualizar según lo que se hizo

| Si en esta sesión... | Actualizar |
|----------------------|------------|
| Cualquier cambio (siempre) | `handoff.md` — sobreescribir con estado actual |
| Se tomó una decisión de diseño, se aclaró un concepto, se descartó algo con razonamiento | `memoria.md` — agregar entrada nueva al inicio |
| Cambió una función clave, un endpoint, una capacidad del bot, la versión | `CLAUDE.md` — sección correspondiente |
| Se descubrió/corrigió un tipo de campo en Notion, cambió un ID, se agregó un dict | `NOTION_SCHEMA.md` |
| Cambió una regla de categorización, tarjeta, ciclo, o caso especial | `REGLAS_NEGOCIO.md` |
| Se encontró y resolvió un fallo nuevo no documentado antes | `DEBUGGING.md` — agregar síntoma + solución |
| Se agregó una feature que necesita verificación | `TESTING.md` — agregar caso de test |

### Cómo cerrar bien una sesión

1. Actualizar los archivos `.md` que correspondan (tabla arriba).
2. Actualizar `handoff.md` con el commit hash final, estado del deploy y próximos pasos.
3. Hacer commit de los docs junto con el código: `git add *.md && git commit`.
4. Push a GitHub.

### Qué va en cada archivo (resumen rápido)

- **`handoff.md`** — el "qué": commit, deploy, cambios de esta sesión, qué verificar, qué sigue.
- **`memoria.md`** — el "por qué": decisiones, conceptos, lecciones, cosas descartadas con razonamiento.
- **`CLAUDE.md`** — el "cómo es": arquitectura actual, capacidades, funciones clave. Sin historia.
- **`NOTION_SCHEMA.md`** — schema vivo de las BDs. Actualizar cuando cambia algún campo o ID.
- **`REGLAS_NEGOCIO.md`** — reglas del dominio. Actualizar cuando Jordi aclara o cambia una regla.
- **`DEBUGGING.md`** — base de conocimiento de fallos. Agregar cada problema nuevo resuelto.
- **`TESTING.md`** — checklist de verificación. Agregar tests para cada feature nueva.
