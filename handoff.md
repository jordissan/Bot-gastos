# handoff.md — Estado operativo

> Se sobreescribe al final de cada sesión. Responde: ¿dónde quedó el proyecto?
> Para arquitectura técnica: `CLAUDE.md`. Para decisiones y lecciones: `docs/MEMORIA.md`.

---

## Sesión en curso: 2026-11-25 (v28.3.3) — mantenimiento, Fase 1

Sigue el «Plan de mantenimiento del bot de gastos» (fases 1–4).

| Item | Estado |
|------|--------|
| Versión | 28.3.3 (v28.3.2 mergeada en #4) |
| Branch | `claude/project-thread-rdyeht` → PR a main (sin mergear) |
| Tests | ✅ 63/63 |

### Hallazgos
- **Balance no tiene ENE27 en adelante.** Desde el 25-nov el ciclo activo es ENE27: todo gasto HEYB25 se guarda sin relación de Mes y `/resumen` responde "No encontré el mes ENE27". Falta crear ENE27…DIC27 en Notion (pendiente de OK de Jordi).
- **Cache de meses sin paginar:** Balance tiene 51 filas y el bot solo leía 50. Arreglado en v28.3.2 (`_cargar_meses_balance`).
- PR #3 (visión qwen3.8, v28.3.1) sigue sin mergear ni probar.
- Fotos de tickets claros fallan (8:26 y 9:38 del 25-nov): falla el modelo de visión y el respaldo de Google Vision, no la foto.
- v28.3.3: `/diagnostico` lista el catálogo de Groq cuando visión o audio están muertos, para elegir reemplazo y fijarlo en Render sin adivinar.
- ENE27…DIC27 ya creados en Balance (opción 2027 en «Año»).

### Pendiente
- [ ] Jordi: variables y logs de Render, `/diagnostico`, pruebas de humo.
- [ ] Con el catálogo de `/diagnostico`, fijar `GROQ_MODELO_VISION` en Render y cerrar o ajustar el PR #3.

---

## Sesión cerrada: 2026-11-25 (v28.3.0)

### Objetivo
Cambio de reglas de Jordi: tarjeta por defecto **HEYB25** y ciclo activo desde el **día 25**.

| Item | Estado |
|------|--------|
| Versión | 28.3.0 |
| Branch | `claude/project-thread-h4w211` → PR a main (sin mergear) |
| Deploy | ⏳ pendiente: al mergear, seguir el flujo de deploy de abajo |
| Tests | ✅ 61/61 |

### Qué cambió
- `calcular_tarjeta`: sin tarjeta explícita → `TARJETA_DEFAULT = "HEYB25"` (config.py).
- `mes_activo_str()` = `calcular_mes(hoy, "HEYB25")`: hoy ≥ 25 → mes+2, hoy < 25 → mes+1. El 25-nov-2026 el ciclo activo es ENE27.
- `_dias_en_ciclo()` ancla en `DIA_INICIO_CICLO = 25` (proyección de `/resumen`).
- `job_reporte_mensual` pasa del día 5 al día 25 (2pm MX): reporta el ciclo que acaba de cerrar.
- Docs: CLAUDE.md, REGLAS_NEGOCIO.md, MEMORIA.md, DEBUGGING.md, TESTING.md. Se descartan las fechas de pago 15/30.

### Pendiente
- [ ] Mergear el PR y desplegar (borrar webhook → push a main).
- [ ] `/diagnostico`: confirmar que los modelos de Groq siguen vivos (el bot estuvo sin uso desde ~sep-2026). Si murieron, cambiar la env var en Render o hacer bypass.
- [ ] Probar: "Oxxo 45" sin tarjeta → HEYB25 y Mes correcto; `/resumen` muestra el ciclo activo nuevo.
- [ ] Log de Render: `Bot corriendo 28.3.0` y `reporte_mensual (día 25 2pm MX)`.

Contexto financiero (no técnico): Notion › Finanzas › 🤖 Contexto Claude — https://app.notion.com/p/4237eb0cbb928181880ec5cac649beb1

---

## Sesión anterior: 2026-08-17

### Objetivo
El bot no respondía a consultas en lenguaje natural. Resultaron **dos bugs
independientes y superpuestos**, uno tapando al otro.

---

### Estado del código

| Item | Estado |
|------|--------|
| Versión | 28.2.0 |
| Branch | main |
| GitHub | ✅ pushed |
| Deploy en Render | ✅ AUTO |
| Tests | ✅ 55/55 — `.venv/bin/pytest tests/ -q` |

---

### 🔴 Bug 1 (v28.1.0) — `_meses_cache` indefinido

Regresión propia de v28.0.0: la modularización usó `from X import *`, que **no trae
nombres con `_` inicial**. `_meses_cache` quedó indefinido y toda consulta moría con
`NameError`. Sin error handler global, PTB se lo tragaba → **silencio total**.
`py_compile` no lo ve porque `NameError` es de runtime.

### 🔴 Bug 2 (v28.2.0) — Groq retiró los modelos

**Groq eliminó `llama-3.3-70b-versatile` y `meta-llama/llama-4-scout`.** La API
devolvía `404 model_not_found` en cada llamada. Con Bug 1 arreglado el síntoma cambió
de silencio a *"No pude registrar ese gasto"*: al fallar la clasificación, el bot caía
al parser clásico y trataba la pregunta como un gasto.

Verificado contra la API real: el catálogo entero cambió. Ya no hay ningún modelo Llama.

---

### Qué cambió (v28.2.0)

**Modelos nuevos** — elegidos midiendo contra la API real, no por intuición:

| Uso | Modelo | Nota |
|-----|--------|------|
| Texto | `openai/gpt-oss-20b` | 5/5 aciertos de clasificación · ~0.6 s |
| Visión | `qwen/qwen3.6-27b` | único multimodal del catálogo |
| Audio | `whisper-large-v3-turbo` | sin cambios, sigue vivo |

Descartados con datos: `compound-mini` (rate limit 429 inmediato),
`gpt-oss-120b` (16 s/llamada), `qwen` para texto (contamina con `<think>`).

**`reasoning_effort` — el hallazgo que hace esto viable**
Los modelos nuevos razonan antes de responder. Sin limitarlo tardan **~16 s** y con
`max_tokens` bajo devuelven **cadena vacía** (el razonamiento agota el presupuesto).
Con `reasoning_effort=low`: **0.6 s**. Cada familia acepta valores distintos
(gpt-oss: low/medium/high · qwen: none/default) y uno inválido da HTTP 400, así que
`_groq_chat()` **reintenta sin el parámetro** en vez de dejar al bot sin LLM.
`GROQ_MIN_TOKENS=700` es el piso que protege la respuesta del razonamiento.

**Modelos configurables sin re-deploy**
Viven en `config.py` y se leen de env: si Groq vuelve a retirar uno, se cambia desde
el panel de Render sin tocar código.

**`/diagnostico` (nuevo)** — el comando que rompe el ciclo "captura → mandar → arreglar":
verifica que el modelo de texto responda, que visión y audio existan en el catálogo,
que Notion conteste y qué ciclos hay en cache. Con esto el fallo se ve en 5 segundos.

**Otros**
- `_extraer_json` limpia bloques `<think>` (incluidos los truncados sin cerrar).
- `VERSION` en config.py: una sola fuente para el log de arranque y `/diagnostico`.

**Tests 47 → 55:** modelos retirados no pueden reaparecer (busca en literales de
código, ignora comentarios), los modelos vienen de config y no hardcodeados,
`GROQ_MIN_TOKENS` suficiente, efforts distintos por familia, `_extraer_json` con
`<think>`. **Verificado que el test falla** al inyectar un modelo muerto.

---

### Pendiente de verificación (después del deploy)

- [ ] `/diagnostico` → todo 🟢 (si algo sale 🔴, ahí está el problema)
- [ ] **"En promedio cuánto gasto de Ezra al mes?"** → responde con la cifra real
- [ ] Se ve `🔍 promedio mensual · Ezra…` antes de la respuesta
- [ ] Foto de ticket → extrae comercio y monto (visión con qwen, **sin verificar aún
      contra una foto real** — qwen dio 503 por sobrecarga durante las pruebas)
- [ ] Nota de voz → transcribe
- [ ] Log de Render: `Bot corriendo 28.2.0`

---

### Flujo de deploy

1. `.venv/bin/pytest tests/ -q` ← obligatorio
2. Borrar webhook: `https://api.telegram.org/bot{TOKEN}/deleteWebhook?drop_pending_updates=true`
3. Push a main → Render Auto Deploy
4. `/diagnostico` en Telegram para confirmar que todo quedó 🟢

---

### Próximos pasos

1. Verificar la lista de arriba, sobre todo **fotos de ticket** (visión sin probar en real)
2. **Nivel 2 (pendiente de decisión):** sustituir los 39 modos hardcodeados por tool
   calling — 4-5 herramientas genéricas que el LLM combina. Hoy cada pregunta fuera
   de esos modos exige una sesión de desarrollo. Estimado 2-3 sesiones.
3. **Backlog:** bot proactivo (avisos de metas), reconciliación email BBVA (postergado)

---

### Lecciones

1. **Un proveedor de LLM puede retirar un modelo y dejar la app muerta.** No había
   ninguna alerta: el bot se degradaba en silencio al parser clásico. De ahí
   `/diagnostico` y los modelos por env var.
2. **Dos bugs pueden taparse mutuamente.** Al arreglar el `NameError`, el síntoma
   cambió y reveló el 404 que estaba debajo. Arreglar el primero no "no sirvió" —
   fue lo que permitió ver el segundo.
3. **Medir antes de elegir.** El candidato obvio (`compound-mini`, que respondía
   perfecto en la primera prueba) era inservible por rate limit; el que parecía
   lento (`gpt-oss`) resultó el bueno al descubrir `reasoning_effort`.
