# NOTION_SCHEMA.md — Esquema completo de las bases de datos Notion

> Referencia exacta de campos, tipos y IDs. Leer antes de tocar cualquier código que interactúe con Notion.
> Los IDs de relación llegan de Notion **con guiones** → siempre `.replace("-", "")` antes de comparar con SC/PR.

---

## BD Gastos — `9c66972a98e74d5b80df8a7e6569e3ca`

Fuente de verdad. Cada registro = un gasto.

| Campo | Tipo Notion | Notas |
|-------|-------------|-------|
| `Concepto` | `title` | Nombre del gasto. MSI formato: `"Concepto X/Total"` ej. `"MacBook Pro 4/18"` |
| `Monto` | `number` | En pesos MXN. Nunca negativo. |
| `Fecha` | `date` | Fecha real de la compra (no del pago). ISO 8601. |
| `Mes` | `select` | Ciclo de pago: `MAY26`, `JUN26`, etc. **No es el mes calendario de la compra.** |
| `Tarjeta` | `rich_text` ⚠️ | **NO es select.** Leer: `props.get("Tarjeta", {}).get("rich_text", [])`. Valores: `BBVA05`, `BBVA12`, `HEYB25`, `BMEX04`, `EFVO` |
| `Subcategoria` | `relation` | Relación a una página de subcategorías. ID en dict `SC`. |
| `Presupuesto` | `relation` | Relación a una página de presupuesto. ID en dict `PR`. Puede estar vacío — derivar vía `SUBCAT_PRESUPUESTO`. |
| `UsuarioID` | `number` | Telegram ID de quien registró (8663298433 = Jordi, 8093171397 = Nane). |
| `Archivado` | `checkbox` | `True` = eliminado (soft delete). Excluir siempre en queries: `{"property":"Archivado","checkbox":{"equals":false}}` |

### Cómo leer cada campo desde la API

```python
props = page["properties"]

concepto = props["Concepto"]["title"][0]["text"]["content"]  # o ["plain_text"]
monto    = props["Monto"]["number"]
fecha    = props["Fecha"]["date"]["start"]                   # "2026-05-26"
mes_sel  = props["Mes"]["select"]
mes      = mes_sel["name"] if mes_sel else ""                # "JUN26"
tarjeta  = "".join(rt["plain_text"] for rt in props.get("Tarjeta", {}).get("rich_text", []))
sc_rel   = props.get("Subcategoria", {}).get("relation", [])
sc_id    = sc_rel[0]["id"].replace("-", "") if sc_rel else ""
pr_rel   = props.get("Presupuesto", {}).get("relation", [])
pr_id    = pr_rel[0]["id"].replace("-", "") if pr_rel else ""
uid      = props.get("UsuarioID", {}).get("number")
```

### Filtros Notion API más usados

```python
# Excluir archivados (SIEMPRE incluir esto)
{"property": "Archivado", "checkbox": {"equals": False}}

# Por ciclo de pago
{"property": "Mes", "select": {"equals": "JUN26"}}

# Por rango de fecha real
{"property": "Fecha", "date": {"on_or_after": "2026-06-01"}}
{"property": "Fecha", "date": {"on_or_before": "2026-06-30"}}

# Por concepto (búsqueda parcial)
{"property": "Concepto", "title": {"contains": "starbucks"}}
```

---

## BD Metas Bot — `cf7906bcccfd4690b7ef8c1e996a8e17`

Metas de gasto por ciclo/presupuesto. También almacena ingresos estimados.

| Campo | Tipo | Notas |
|-------|------|-------|
| `Concepto` | `title` | Nombre identificador (ej. `"Despensa JUN26"`) |
| `Monto` | `number` | Límite de gasto o ingreso estimado |
| `Mes` | `rich_text` | Ciclo al que aplica: `"JUN26"` |
| `Presupuesto` | `rich_text` | Categoría o `"INGRESO"` para ingreso estimado |
| `UsuarioID` | `number` | Telegram ID de quien la creó |

**Lectura de ingreso estimado:**
```python
# Se busca en AMBOS UIDs (finanzas conjuntas)
filter = {"and": [
    {"property": "Presupuesto", "rich_text": {"equals": "INGRESO"}},
    {"property": "Mes", "rich_text": {"equals": ciclo}},
]}
```

---

## BD Historial Bot — `35f7eb0cbb9280ae8f02f69b4f242298`

Dos usos distintos en la misma BD:

### Uso 1: Snapshot de últimos gastos (para `/corregir`)

| Campo | Tipo | Notas |
|-------|------|-------|
| `Concepto` | `title` | Nombre del gasto |
| `Monto` | `number` | Monto |
| `Fecha` | `date` | Fecha |
| `UsuarioID` | `number` | ID del usuario |
| `NotionID` | `rich_text` | ID de la página en BD Gastos |

### Uso 2: Memoria persistente (filas `MEM_{uid}`)

| Campo | Tipo | Valor |
|-------|------|-------|
| `Concepto` | `title` | `"MEM_8663298433"` o `"MEM_8093171397"` |
| `UsuarioID` | `number` | **Siempre 0** (distingue del uso 1) |
| `NotionID` | `rich_text` | JSON serializado: `{"turns":[...], "last_results":[...], "last_query":{...}}` |

**Filtro para encontrar la fila de memoria:**
```python
{"and": [
    {"property": "Concepto", "title": {"equals": f"MEM_{uid}"}},
    {"property": "UsuarioID", "number": {"equals": 0}},
]}
```

---

## BD Aprendizaje Bot — `3ba6f37c717948a1a6aeac3b384ff33c`

Diccionario de categorías aprendidas por `inferir_categoria`.

| Campo | Tipo | Notas |
|-------|------|-------|
| `Concepto` | `title` | Texto normalizado del concepto aprendido |
| `Subcategoria` | `rich_text` | Nombre de la subcategoría |
| `Presupuesto` | `rich_text` | Nombre del presupuesto |
| `Usos` | `number` | Contador; entradas con `Usos=1` se limpian automáticamente |

---

## BD Balance — via `NOTION_BALANCE_ID` (env var)

Meses dinámicos con rollups de gastos por ciclo.

| Campo | Tipo | Notas |
|-------|------|-------|
| `Nombre` | `title` | Código del ciclo: `"ENE26"`, `"FEB26"`, etc. |
| `Año` | `select` | Año del ciclo: `"2026"` |
| `Gasto` | `rollup` o `number` | Total de gastos del ciclo (rollup preferido, fallback a number) |

```python
# Leer total:
g = props.get("Gasto", {})
total = (g.get("rollup", {}) or {}).get("number") or g.get("number")
```

---

## BD Alias Bot — `9000583a97204e6db41994ec96bf5a71`

Alias personales aprendidos por conversación.

| Campo | Tipo | Notas |
|-------|------|-------|
| `Concepto` | `title` | Trigger (lo que el usuario escribe) |
| `Alias` | `rich_text` | Expansión (cómo se guarda en Notion) |
| `UsuarioID` | `number` | Alias son personales — no se comparten entre usuarios |

---

## Dicts de relaciones (en bot.py)

### `SC` — Subcategoría → ID de relación Notion

```python
SC = {
    # Despensa
    "Super":          "bf7d4b7d0445441ab89b53eec946d028",
    "Abarrotes":      "3587eb0cbb9280c58919c55b065c1e19",
    "Carniceria":     "6a734da3d457465db419f195de13909b",
    "Mercado":        "3587eb0cbb9280c58919c55b065c1e19",
    "Comida":         "3587eb0cbb9280c58919c55b065c1e19",
    # Restaurantes
    "Restaurantes":   "1cf748f0639e41469ae2cc73aa86e10a",
    # Automovil
    "Gasolina":       "8382b85617f342afa50ed56ca48ed9d3",
    "Estacionamento": "31ce3fef973e47bb95259d253817a417",
    "Mantenimiento":  "50eae9bd7c3f4cf78f02eae174dedc25",
    "VW POLO":        "1fa7eb0cbb928068a523f7a0b9cbb0a3",
    "Seguro Auto":    "cf81abcd84824b82b71455913fefdd2a",
    # Servicios
    "Servicios":          "b4d2856cb9a44fd584904aabcc007008",
    "Streaming":          "1d87eb0cbb9280a186f9f369501da604",
    "Internet":           "8351d13e3b2e4bdcbfa0bcc97c0392bc",
    "Telefonia Celular":  "7a0ff69980f14b22b1767b7e826d33e3",
    "Luz":                "bf545e8169f840eda0ca126164e105b8",
    "Agua":               "80ff78e25af04952a90ffbc6e452c84f",
    # Vivienda
    "Renta":        "31382e5d307f455aa540b5ee422d5046",
    "Muebles":      "cb6257b088fc443ea512b14a8a4d9a95",
    "Decoracion":   "cee5039a07bf45fe941ea71f0e570335",
    # Diversión
    "Treat":              "1d87eb0cbb9280d5b5b0e9efd29e46bf",
    "Salidas":            "1d87eb0cbb9280c1b4b7d3beeb2b1ebc",
    "Cine":               "1fa484da9e2d4777ab1521d9c34abb60",
    "Conciertos":         "b8581fd6ac0d48cbad91890377ab642d",
    "Tiempo de calidad":  "ee047ce5151d4300a02c08cf44c273c8",
    # Personal
    "Ropa":            "6447d4fe109a431abc217d04f54ba91d",
    "Calzado":         "77e1d9b686054539a2d052cbcbf6f341",
    "Gimnasio":        "f0bba54f0eca44f2a9ddca61d1218e57",
    "Corte de pelo":   "20e58a92053f4084b149d158c217ff96",
    "Cuidado personal":"7287cad9f27040dca2149a1da0e9d03c",
    "Gasto personal":  "1d87eb0cbb928065a2fcddcc3de0cdd8",
    # Salud
    "Doctor":   "59148339aab54dd0a1f3b315bfc6a521",
    "Medicina": "d495413562a848cc89710e90a32219e0",
    # Educación
    "Libros":  "931ebc757b6d4b60908a113684546862",
    "Cursos":  "5acc85e7ac924174a21f0b93e44ec0ed",
    # Especiales
    "Ezra":        "2457eb0cbb92806eaff7c989e5ccfe34",
    "Emergencias": "980640dd649642f5bdd9c8a11ba2ea03",
    "Regalos":     "ced98b7c20b74ada88bc087489c4e7bd",
    "Ofrenda":     "3e2ae6fbd5024e4f9bb44acc35167eda",
    "Diezmo":      "e9517e40830f45eaa46a1f6f1b496daf",
    "Vacaciones":  "82c84acd15304f50a33deefad78ec711",
    "Impuestos":   "56681551d6044dddbf918ced2761b465",
    "Otros":       "fd99fde0fa724f41a0ffeb7ee9425ec8",
    # Deudas / MSI
    "MSI":    "1fa7eb0cbb928050a619e2105a4b77e4",
    "Deudas": "583b7dd3eb694921ac327e66821dd715",
    "EFI":    "3597eb0cbb9280d79e1bf0e8f7de7f6d",
    "DBMEX":  "3597eb0cbb92803f8a8bd99d09450717",
    "PDHB25": "3597eb0cbb9281b3a935f46cdba3333c",
    "PRP":    "1fb7eb0cbb9280198a32ec4395b6de35",
}
```

### `PR` — Presupuesto → ID de relación Notion

```python
PR = {
    "Despensa":        "0e4bbd6e13b34972b39f14f76eb61d7d",
    "Diversión":       "a1d0605a28694b0baefdc43ac75a798a",
    "Servicios":       "0a9ef564f8944cc088e302e64ad702b6",
    "Automovil":       "20f5ab24f9ca4185af6a34254ab3a630",
    "Restaurantes":    "3547eb0cbb9281e08ef5f3666e091a44",
    "Salud":           "3547eb0cbb9281a1ba5dfea0791b8d36",
    "Deuda":           "91ab43856d1e4ae69f21f4203eeb3c54",
    "MSI":             "1fc7eb0cbb92802ba323cfc943dc0f2c",
    "Renta":           "eeb6e04137c248468f641a5044b16545",
    "Ezra":            "3547eb0cbb92817baaa9f6681e6bbabc",
    "Personal":        "829161723b0b49bf8787663a89c7248d",  # ⚠️ fue "Cuidado personal" — Jordi renombró el presupuesto el 26-may-2026
    "Vacaciones":      "545753674d4e4d0ca0fd8be7d33db21e",
    "Impuestos":       "224cdb40f1f749c7b5d6e165ad31110d",
    "Entretenimiento": "3547eb0cbb92815d8248db75a759646b",
    "Generosidad":     "f4cac9f4b95e4508942ad02ae69ddffe",
    "Iglesia":         "89b897bd6fa24b8d897adf380491130e",
    "Departamento":    "1af955c917f54a2da39e9bbb8e4032ff",
    "Otros":           "1ea7eb0cbb9280cbbe43c1bd54396691",
    "Educación":       "3677eb0cbb9281c4b82cc803cb114d65",
    "Emergencias":     "3677eb0cbb9281598e2fe19be3db3d74",
    "Deudas":          "91ab43856d1e4ae69f21f4203eeb3c54",  # alias de Deuda
}
```

### `SUBCAT_PRESUPUESTO` — Subcategoría → Presupuesto (fallback)

Cuando un gasto no tiene relación `Presupuesto` en Notion (puede pasar si se borra la columna al iniciar mes), se deriva desde la subcategoría:

```
Super, Abarrotes, Carniceria, Mercado, Comida → Despensa
Restaurantes → Restaurantes
Gasolina, Estacionamento, Mantenimiento, VW POLO, Seguro Auto → Automovil
Servicios, Streaming, Internet, Telefonia Celular, Luz, Agua → Servicios
Renta → Renta
Muebles, Decoracion → Departamento
Treat, Salidas, Cine, Conciertos, Tiempo de calidad → Diversión
Ropa, Calzado, Gimnasio, Corte de pelo, Gasto personal → Personal
Cuidado personal → Personal
Doctor, Medicina → Salud
Libros, Cursos → Educación
Emergencias → Emergencias
Ezra → Ezra
Regalos, Ofrenda, Diezmo → Generosidad
MSI → MSI
Deudas, EFI, DBMEX, PDHB25, PRP → Deuda
Impuestos → Impuestos
Vacaciones → Vacaciones
Otros → Otros
```

---

## Timeouts de la API Notion

```python
NOTION_T_SHORT   = 5   # queries simples
NOTION_T_DEFAULT = 8   # queries normales
NOTION_T_LONG    = 15  # queries históricas o paginadas
```
