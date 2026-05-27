# handoff.md — Estado operativo

> Se sobreescribe al final de cada sesión. Responde: ¿dónde quedó el proyecto?
> Para arquitectura técnica: `CLAUDE.md`. Para decisiones y lecciones: `memoria.md`.

---

## Sesión cerrada: 2026-05-26

### Objetivo
Corregir 3 bugs + sandbox multi-turno en /prueba + confirmación de edición contextual.

---

### Estado del código

| Item | Estado |
|------|--------|
| Último commit | pendiente |
| GitHub | pendiente push |
| Ruta local | `/Users/jordi/Documents/Claude/Projects/Bot-gastos/` |
| Deploy en Render | ✅ AUTO — push a main dispara deploy |

---

### Qué cambió en esta sesión (v26.1.0 → v26.5.0)

**Bug 1 — Edición no actualizaba presupuesto al cambiar subcategoría**
- `aplicar_edicion_contextual`: auto-deriva presupuesto desde `SUBCAT_PRESUPUESTO` si no viene explícito.

**Bug 2 — MEM_ aparecían en /corregir**
- `cargar_historial_compartido()`: filtro `UsuarioID > 0`.

**Bug 3 — ID incorrecto para presupuesto "Personal"**
- `PR["Personal"]` corregido a `829161723b0b49bf8787663a89c7248d`.
- Eliminada clave `"Cuidado personal"` de PR; SUBCAT_PRESUPUESTO y reglas hard-coded actualizadas.

**Feature — Sandbox multi-turno en /prueba**
- Loop persistente: registra y edita gastos sin guardar en Notion.
- Salida: `/cancelar`.
- Helpers: `_FOOTER_SB`, `_msg_sandbox()`, `_editar_gasto_local()`.

**Feature — Confirmación antes de aplicar edición contextual**
- Edición conversacional ya NO aplica a Notion inmediatamente.
- Flujo nuevo: propuesta con botones inline [✅ Confirmar] [❌ Cancelar].
- Múltiples rondas de corrección se ACUMULAN en `_staged_edits[uid]` antes de confirmar.
- Solo al confirmar: PATCH a Notion + notificación a la pareja.
- Si registran un gasto nuevo entre ediciones, el staged edit anterior se descarta.
- Nuevos componentes:
  - `_staged_edits: dict` — staging area por uid
  - `_construir_props_edicion(base, g)` — construye props Notion del diff
  - `callback_edicion(update, context)` — callback de confirm/cancel
  - Registro: `CallbackQueryHandler(callback_edicion, pattern="^edicion_")`

---

### Pendiente de verificación

- [ ] Bug 1: "ponlo en Treat" → debe cambiar subcategoría Y presupuesto
- [ ] Bug 2: /corregir → sin MEM_*
- [ ] Bug 3: "Corte de pelo 150" → presupuesto correcto en Notion
- [ ] Sandbox: /prueba → gasto → editar → /cancelar
- [ ] Confirmación edición: mensaje → corrección → ver propuesta con botones → confirmar → solo entonces llega notificación a pareja
- [ ] Múltiples rondas: corrección 1 → corrección 2 → confirmar → solo UN mensaje a pareja con cambios acumulados
