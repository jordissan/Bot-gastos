# handoff.md — Estado operativo

> Se sobreescribe al final de cada sesión. Responde: ¿dónde quedó el proyecto?
> Para arquitectura técnica: `CLAUDE.md`. Para decisiones y lecciones: `docs/MEMORIA.md`.

---

## Sesión cerrada: 2026-08-17

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
