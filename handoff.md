# handoff.md — Estado operativo

> Se sobreescribe al final de cada sesión. Responde: ¿dónde quedó el proyecto?
> Para arquitectura técnica: `CLAUDE.md`. Para decisiones y lecciones: `memoria.md`.
>
> **Al cerrar la sesión:** actualizar este archivo + los demás `.md` que correspondan según
> lo que se hizo. Ver tabla en `CLAUDE.md → Protocolo de Cierre`. Luego commit + push.
> Jordi no debería tener que pedir esto.

---

## Sesión cerrada: 2026-05-26

### Objetivo
Corregir 3 bugs reportados por Jordi via screenshots del chat con el bot.

---

### Estado del código

| Item | Estado |
|------|--------|
| Último commit | pendiente — ver abajo |
| GitHub | pendiente push |
| Ruta local | `/Users/jordi/Documents/Claude/Projects/Bot-gastos/` |
| Deploy en Render | ✅ **AUTO** — Render despliega automáticamente en cada push a `main` |
| Bot en producción | pendiente deploy de esta sesión |

---

### Qué cambió en esta sesión

**3 bugs corregidos en bot.py (v26.1.0 → v26.3.0):**

**Bug 1 — Edición contextual no actualizaba presupuesto al cambiar subcategoría**
- Síntoma: "Este último gasto tiene que ir en Treat y diversión" solo cambiaba la subcategoría (Treat) pero dejaba el presupuesto intacto.
- Causa: `aplicar_edicion_contextual` manejaba `subcategoria` y `presupuesto` de forma independiente. Si Groq solo devolvía `subcategoria` sin `presupuesto`, el presupuesto nunca se actualizaba.
- Fix: Cuando se cambia subcategoría sin presupuesto explícito, se auto-deriva desde `SUBCAT_PRESUPUESTO` y se aplica en el mismo PATCH a Notion.

**Bug 2 — Filas MEM_ aparecían en la lista de /corregir**
- Síntoma: Al usar /corregir, aparecían "MEM_8093171397 · $0.00" y "MEM_8663298433 · $0.00" ocupando 2 de los 5 slots.
- Causa: `cargar_historial_compartido()` consultaba Historial Bot sin filtro, y las filas MEM_ (UsuarioID=0) aparecían si eran las más recientes por `created_time`.
- Fix: Agregado `{"property": "UsuarioID", "number": {"greater_than": 0}}` al query de `cargar_historial_compartido()`.

**Bug 3 — ID incorrecto para presupuesto "Personal"**
- Síntoma: Gastos de "Corte de pelo" vinculaban el presupuesto a la página equivocada en Notion.
- Causa: `PR["Personal"]` apuntaba a `3c42302c396c4f4abffa38bff79ccac6` (una página en "Categorias de Gastos", NO en la BD Presupuesto). El ID correcto es `829161723b0b49bf8787663a89c7248d` (la página que Jordi renombró de "Cuidado personal" a "Personal" en la BD Presupuesto).
- Fix:
  - `PR["Personal"]` → `829161723b0b49bf8787663a89c7248d`
  - Eliminada entrada `"Cuidado personal"` del dict PR (ya no existe ese nombre en Notion)
  - `SUBCAT_PRESUPUESTO["Cuidado personal"]` → `"Personal"` (antes era `"Cuidado personal"`)
  - Regla hard-coded de sephora/perfumería actualizada: presupuesto `"Cuidado personal"` → `"Personal"`
  - `PR_EMOJI`: eliminada entrada `"Cuidado personal":"💆"` (ya no hay clave con ese nombre)
  - Actualizado en `NOTION_SCHEMA.md` y `REGLAS_NEGOCIO.md`

---

### Pendiente de verificación (después del deploy)

- [ ] Bug 1: Decirle al bot "Este gasto ponlo en Treat y Diversión" justo después de registrar → debe cambiar AMBOS campos
- [ ] Bug 2: Usar /corregir → la lista debe mostrar solo gastos reales (sin MEM_*)
- [ ] Bug 3: Registrar un gasto de "Corte de pelo" o "Sephora" → verificar en Notion que el presupuesto apunta a la página correcta (Personal en BD Presupuesto)

---

### Próximos pasos

1. Verificar los 3 puntos de arriba en producción
2. **Backlog** (sin urgencia):
   - Reconciliación email BBVA — postergado indefinidamente
   - Evaluar búsqueda híbrida ciclo+calendario para casos genuinamente ambiguos
