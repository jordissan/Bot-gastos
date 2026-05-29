# handoff.md — Estado operativo

> Se sobreescribe al final de cada sesión. Responde: ¿dónde quedó el proyecto?
> Para arquitectura técnica: `CLAUDE.md`. Para decisiones y lecciones: `docs/MEMORIA.md`.

---

## Sesión cerrada: 2026-05-29

### Objetivo
1. Fix Bug 3: tabla de productos de ticket (resuelto en sesión anterior, v26.10.0)
2. Feature: 20 nuevas capacidades de consulta y acción masiva (v27.0.0)
3. Continuación: fixes v27.1–v27.2, mejoras UX v27.3–v27.5, refactor Codex v27.6.0

---

### Estado del código

| Item | Estado |
|------|--------|
| Versión | 27.6.0 |
| Branch | main |
| GitHub | ✅ pushed |
| Deploy en Render | ✅ AUTO — push a main dispara deploy |
| Ruta local | `/Users/jordi/Documents/Claude/Projects/Bot-gastos/` |

---

### Qué cambió en esta sesión (v27.0.0 → v27.6.0)

**v27.1.0 — Fix `por_tarjeta` mostraba "Sin tarjeta" en todos los gastos**
- Causa: bot escribe tarjeta a `Pago` (select) + `Estado de Cuenta` (rich_text), pero código leía `Tarjeta` (campo distinto, vacío en gastos del bot).
- Fix: helper `_leer_tarjeta(props)` con cadena de prioridad: Pago → Estado de Cuenta → Tarjeta. Aplicado en las 6 ubicaciones de lectura.

**v27.2.0 — Dos fixes de prompt**
- "último gasto de autolavado" usaba `modo:"ultimo"` en lugar de `ultima_visita` + comercio. Fix: regla explícita en prompt — `"ultimo"` nunca cuando se menciona un comercio específico.
- "efectivo" no se mapeaba a `tarjeta: "EFVO"`. Fix: regla en secciones registro y edición del prompt.

**v27.3.0 — Shortcuts: campo `resumen` en respuesta `/log`**
- `registrar_via_shortcut` ahora devuelve 3-tuple `(ok, msg, resumen)`.
- `resumen` = línea compacta `"Concepto $monto · Tarjeta · Subcategoría"` lista para mostrar en iOS.
- El endpoint `/log` incluye `"resumen"` en el JSON de respuesta.
- iOS: añadir acción "Obtener valor del diccionario" con clave `resumen` + "Mostrar notificación" para confirmación nativa.

**v27.4.0 — Emojis en menú de presupuesto (`/corregir`)**
- Botones del sub-menú "Elige el presupuesto" usan `PR_EMOJI` (ej: `🛒 Despensa`).

**v27.5.0 — Emojis en todos los menús de `/corregir`**
- `TARJETA_EMOJI`: 🔵 BBVA05/12, 🟣 HEYB25, 🔴 BMEX04, 💵 EFVO.
- `SC_EMOJI`: emoji único para cada una de las ~35 subcategorías.
- Menú tarjeta: layout 2 columnas + emoji.
- Submenú subcategoría nivel 2: layout 2 columnas + emoji.

**v27.6.0 — Refactor Codex: deduplicación de notificación y ruta de edición**
- `notificar_pareja(context, uid, texto, **kw)`: helper único que reemplaza 6 bloques idénticos de notificación al cónyuge.
- `_aplicar_edicion_notion(base, campos)`: unifica la ruta de PATCH que estaba duplicada entre `aplicar_edicion_contextual` (texto/voz) y `callback_edicion` (botones inline). Ahora ambas usan la misma función.
- `_edicion_cambio_categoria(props)`: `guardar_aprendizaje` solo se llama cuando de verdad cambia subcategoría o presupuesto (antes se llamaba siempre, incluso al editar monto).
- Eliminada línea muerta `.__class__` en `_accion_ejecutar`.
- Comportamiento externo idéntico; solo refactor interno.

---

### Pendiente de verificación (después del deploy)

- [ ] Enviar foto de ticket con productos → tabla de productos aparece en la página de Notion
- [ ] "¿Cuáles son mis 5 gastos más grandes de mayo?" → ranking_monto
- [ ] "¿Hay duplicados este mes?" → duplicados
- [ ] "¿Cuánto me falta en cada presupuesto?" → margen_presupuesto
- [ ] "¿A cuánto voy a llegar este mes?" → proyeccion_ciclo
- [ ] "¿Cuánto gasté en cada tarjeta?" → por_tarjeta (fix v27.1)
- [ ] "Compara mayo con abril" → comparar_ciclos
- [ ] "¿Qué aliases tengo?" → listar_aliases
- [ ] "Olvida el alias X" → borrar_alias
- [ ] "Genera el reporte semanal" → reporte on demand
- [ ] "Cambia todos los gastos de Uber a Transporte" → accion reclasificar + confirmación
- [ ] "Muéstrame los gastos sin categoría" → sin_categoria
- [ ] "Último gasto de autolavado" → ultima_visita (fix v27.2)
- [ ] Pagar en efectivo → tarjeta EFVO, no aparece "efectivo" en concepto (fix v27.2)
- [ ] iOS Shortcut: respuesta `/log` incluye campo `resumen` para confirmación nativa (v27.3)
- [ ] `/corregir` → todos los menús muestran emojis (tarjeta, subcategoría, presupuesto) (v27.4–v27.5)

---

### Flujo de deploy

1. Borrar webhook: `https://api.telegram.org/bot{TOKEN}/deleteWebhook?drop_pending_updates=true`
2. Push a main → Render hace Auto Deploy automáticamente
3. Verificar en logs: `[APScheduler] Scheduler iniciado.`

---

### Próximos pasos

1. Verificar los puntos de arriba en producción
2. **Backlog** (sin urgencia):
   - Reconciliación email BBVA — postergado indefinidamente
   - Evaluar búsqueda híbrida ciclo+calendario
   - iOS Shortcuts: añadir "Obtener valor del diccionario" (`resumen`) + "Mostrar notificación" tras el POST `/log`
