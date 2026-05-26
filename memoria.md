# memoria.md — Memoria institucional del proyecto

> Acumula decisiones de diseño, conceptos clave del dominio y lecciones aprendidas.
> **Nunca se borra** — se agrega al inicio de cada entrada nueva.
> Para el estado operativo de la última sesión, ver `handoff.md`.
>
> **Actualizar al cierre de sesión** cuando: se tomó una decisión de diseño, se aclaró
> un concepto del dominio, se descartó algo con razonamiento, o se aprendió una lección
> que evita repetir un error. No esperar a que Jordi lo pida.

---

## Conceptos del dominio — verdades permanentes

### Ciclo de pago vs mes calendario
`JUN26` en Notion = **"gastos que se pagan en junio 2026"** (mes de pago), NO "gastos comprados en junio".
Una compra del 26 de junio queda en:
- **EFVO** → JUN26 (siempre mes actual)
- **BBVA05** → JUL26 (corte día 5, 26 ≥ 5)
- **BBVA12** → JUL26 (corte día 12, 26 ≥ 12)
- **BMEX04** → JUL26 (corte día 4, 26 ≥ 4)
- **HEYB25** → AGO26 (corte día 25, 26 ≥ 25 → mes+2)

Cuando el usuario dice "dame los gastos de JUN26", quiere exactamente `Mes = JUN26` en Notion — filtrado por subcategoría o lo que pida. Es determinístico, no ambiguo. Si no hay resultados, decirlo claro.

### Finanzas conjuntas
Jordi y Nane manejan finanzas como unidad familiar. **Nunca separar gastos por usuario en consultas.** El ingreso estimado también es conjunto — se guarda y se lee en ambos UIDs.

### Subcategoría vs Categoría (presupuesto)
"Restaurantes" existe en SC (subcategoría) Y en PR (presupuesto). El planner debe usar `subcategoria=Restaurantes` por default cuando hay ambigüedad — es más preciso. **Nunca poner `subcategoria` y `categoria` simultáneamente en el plan.**

### Semántica de "JUN26" en consultas
El usuario entiende `JUN26` como ciclo de pago. Nunca intentar "ayudar" traduciendo automáticamente a fechas calendario — rompe la semántica del sistema. Si JUN26 está vacío en Notion, es porque los gastos de esas fechas quedaron en otro ciclo. El bot debe informarlo, no inventar.

---

## Decisiones de diseño

### Query en 2 pasos (plan → datos → redacción)
El LLM nunca toca los datos directamente — primero genera un plan JSON, luego `ejecutar_consulta_finanzas` hace la query determinística, y solo entonces el LLM redacta con esos datos. Esto elimina alucinaciones de cifras. Aprendido desde el inicio del Hub Financiero.

### `prompt_resp` con REGLA CRÍTICA
La instrucción débil "usa SOLO estos datos" no fue suficiente — Groq usaba el historial de la conversación cuando los datos estaban vacíos. Se cambió a una REGLA CRÍTICA explícita: "PROHIBIDO usar información de mensajes anteriores, inventar cifras o mencionar meses/gastos que no aparezcan en los datos." Si los datos están vacíos, el bot debe decirlo directamente.

### APScheduler dentro del bot (no rutinas externas)
Las rutinas remotas de Claude Code (CCR) no pueden hacer llamadas HTTP salientes desde el entorno de Render. Por eso los reportes se movieron a APScheduler dentro del propio bot. El bot ya corre 24/7 y tiene toda la lógica — es el lugar correcto.

### Ingreso estimado en Metas Bot con presupuesto="INGRESO"
Jordi y Nane son freelancers con ingresos variables. No hay forma de saber el ingreso real antes de que llegue. Se usa `guardar_meta(uid, "INGRESO", monto, ciclo)` para declarar el ingreso esperado. Metas Bot ya existía — se reusó con una clave especial en lugar de crear una nueva BD.

### Tarjeta como `rich_text` en Notion (no select)
El campo Tarjeta en Notion es `rich_text`, no `select`. Leer con `.get("Tarjeta", {}).get("rich_text", [])`. Confundir esto causa que el filtro de tarjeta no funcione silenciosamente.

### `conv_foto` antes que `conv_gasto`
Si se invierte el orden de registro de los ConversationHandlers, las fotos caen en el handler de texto y se rompe el OCR. El orden en `main()` es crítico.

---

## Cosas intentadas y descartadas — con razonamiento

### Auto-retry por mes calendario (descartado)
**Qué era:** cuando `Mes=JUN26` devolvía 0 resultados, se reintentaba la query con `fecha_desde/fecha_hasta` del mes calendario equivalente.
**Por qué se descartó:** el usuario aclaró que `JUN26` = ciclo de pago, no mes calendario. El auto-retry "ayudaba" de forma que contradecía la semántica del sistema. Si JUN26 está vacío, es la respuesta correcta.
**Qué quedó:** el helper `_ciclo_a_rango_calendario(ciclo)` se mantiene en el código — puede ser útil en el futuro para algo más explícito.

### Rutinas remotas CCR para reportes (reemplazadas)
**Qué era:** reportes semanal y mensual disparados desde rutinas de Claude Code remoto.
**Por qué se reemplazó:** las rutinas CCR no pueden hacer llamadas HTTP salientes desde Render. Los reportes nunca llegaban.
**Solución:** APScheduler dentro del bot (ver arriba).

### Rutina "Nuevo mes" con notificación al bot (simplificada)
**Qué era:** la rutina de Claude Code "Nuevo mes" terminaba con un POST al bot notificando el nuevo ciclo.
**Por qué se eliminó:** el endpoint `POST /propuesta_mes` existe en el bot, pero la notificación al bot no agrega valor — solo creaba una dependencia frágil. La rutina ahora solo crea recurrentes en Notion y termina.

---

## Backlog — features explorados, postergados indefinidamente

| Feature | Motivo de postergación |
|---------|------------------------|
| Reconciliación email BBVA (Gmail API + PDF) | Alta complejidad; requiere parsear PDFs de banco, cruzar con Notion. Versión futura. |
| Búsqueda híbrida ciclo+calendario | Evaluar si tiene sentido cuando la pregunta es genuinamente ambigua — pero NO como comportamiento default. |
