# handoff.md — Estado operativo

> Se sobreescribe al final de cada sesión. Responde: ¿dónde quedó el proyecto?
> Para arquitectura técnica: `CLAUDE.md`. Para decisiones y lecciones: `memoria.md`.
>
> **Al cerrar la sesión:** actualizar este archivo + los demás `.md` que correspondan según
> lo que se hizo. Ver tabla en `CLAUDE.md → Protocolo de Cierre`. Luego commit + push.
> Jordi no debería tener que pedir esto.

---

## Sesión cerrada: 2026-05-20 → 2026-05-26

### Objetivo
Expandir el bot a un hub financiero completo (Hub v2) y corregir bugs de subcategoría y alucinación de Groq.

---

### Estado del código

| Item | Estado |
|------|--------|
| Último commit | `a2249e7` — "agrega handoff.md y refina protocolo de inicio" |
| GitHub | ✅ Pusheado — branch `main` |
| Deploy en Render | ⚠️ **PENDIENTE** — Manual Deploy no realizado aún |
| Bot en producción | Corriendo con código pre-sesión hasta que se haga el deploy |

---

### Qué cambió en esta sesión

**bot.py:**
- Filtro por `subcategoria_id` en `ejecutar_consulta_finanzas` y todos los modos de `_datos_consulta_especial`
- Filtro por `tarjeta` (campo `rich_text`) en todas las queries
- Plan carryover: `last_query` se inyecta al planner para mantener filtros entre preguntas
- Ingresos estimados: nuevo intent `ingreso` en el clasificador + handler completo
- 4 nuevos modos de consulta: `msi_tracker`, `oportunidades_ahorro`, `posicion_financiera`, `tendencia_ingresos`
- Desglose por tarjeta en reportes semanal y mensual (`por_tarjeta` en `_agg_ciclo`)
- `gastos_raw` limit: 10 → 20
- Helper `_ciclo_a_rango_calendario(ciclo)` agregado (aún sin uso activo)
- `prompt_resp` reforzado con REGLA CRÍTICA anti-alucinación
- APScheduler: `job_reporte_semanal` (lun 9am MX) y `job_reporte_mensual` (día 5 2pm MX)

**Documentación:**
- `CLAUDE.md` — restructurado y actualizado a v26.2.0
- `memoria.md` — creado
- `handoff.md` — creado (este archivo)

### Qué se intentó y se revirtió

- **Auto-retry calendario**: cuando un ciclo devolvía vacío, se reintentaba con fechas del mes calendario. Revertido — contradecía la semántica del sistema. Ver `memoria.md` para el razonamiento completo.

---

### Pendiente de verificación (después del deploy)

- [ ] Anti-alucinación: preguntar por un ciclo sin gastos → el bot debe decir "no hay" sin mencionar otros meses
- [ ] `msi_tracker`: confirmar que parsea bien el formato "Concepto X/Total" con datos reales
- [ ] `posicion_financiera`: declarar un ingreso y consultar "¿cómo voy este mes?"
- [ ] Logs de Render: verificar línea `[APScheduler] Scheduler iniciado. Jobs: reporte_semanal (lun 9am), reporte_mensual (día 5 2pm)`

---

### Próximos pasos

1. **Jordi hace deploy en Render** (manual, no puede hacerlo Claude):
   - Borrar webhook: `https://api.telegram.org/bot{TOKEN}/deleteWebhook?drop_pending_updates=true`
   - Render → Bot-gastos → Manual Deploy → Restart service

2. **Verificar los 4 puntos de arriba** en producción

3. **Backlog** (sin urgencia):
   - Reconciliación email BBVA — postergado indefinidamente (ver `memoria.md`)
   - Evaluar búsqueda híbrida ciclo+calendario para preguntas genuinamente ambiguas
