import os
import json
import logging
import httpx
from datetime import datetime
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

# ─── CONFIGURACIÓN ────────────────────────────────────────────────
TELEGRAM_TOKEN    = os.environ["TELEGRAM_TOKEN"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
NOTION_TOKEN      = os.environ["NOTION_TOKEN"]
NOTION_DATABASE_ID = os.environ["NOTION_DATABASE_ID"]
# ──────────────────────────────────────────────────────────────────

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Eres un asistente para registrar gastos personales en Notion.

El usuario te mandará un mensaje describiendo un gasto. Tu trabajo es extraer los datos y devolver un JSON.

REGLAS DE TARJETA:
- Si no se menciona tarjeta, inferirla por la fecha:
  - Días 1-11 del mes → BBVA05
  - Días 12-31 del mes → BBVA12

REGLAS DE MES (a qué mes se carga el gasto):
- BBVA12 (corte día 12): compra entre 12-mes y 11-mes+1 → Mes = mes+2
  Ejemplo: compra 16-abr → MAY26
- BBVA05 (corte día 5): compra entre 5-mes y 4-mes+1 → Mes = mes+1
  Ejemplo: compra 16-abr → MAY26

SUBCATEGORÍAS según el concepto:
- Netflix, Spotify, Disney, HBO, Apple, Google One, iCloud → Streaming
- Uber, Didi, gasolina, OXXO Gas → Transporte
- Restaurantes, cafeterías, Starbucks, comida → Diversión
- Farmacias, médico, salud → Salud
- Supermercado, Soriana, Costco, abarrotes → Super
- Amazon, tiendas, ropa → Compras
- CFE, agua, internet, Izzi, teléfono → Servicios
- Otros → General

PRESUPUESTO según subcategoría:
- Streaming → Servicios
- Transporte → Transporte
- Diversión → Diversión
- Salud → Salud
- Super → Despensa
- Compras → Personal
- Servicios → Servicios
- General → General

Devuelve ÚNICAMENTE un JSON con esta estructura, sin texto adicional:
{
  "concepto": "nombre del gasto",
  "monto": 150.00,
  "fecha": "2026-04-16",
  "tarjeta": "BBVA12",
  "subcategoria": "Diversión",
  "presupuesto": "Diversión",
  "mes": "MAY26"
}

Si el mensaje no parece un gasto, devuelve:
{"error": "No entendí el gasto. Ejemplo: 'Starbucks 150' o 'gasolina 500 BBVA05'"}
"""

async def parse_gasto_con_claude(texto: str, fecha_hoy: str) -> dict:
    """Usa Claude para parsear el mensaje del usuario."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 500,
                "system": SYSTEM_PROMPT,
                "messages": [
                    {"role": "user", "content": f"Fecha de hoy: {fecha_hoy}\nGasto: {texto}"}
                ],
            },
            timeout=30,
        )
        data = response.json()
        raw = data["content"][0]["text"].strip()
        return json.loads(raw)

async def guardar_en_notion(gasto: dict) -> bool:
    """Crea una entrada en la base de datos de Notion."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.notion.com/v1/pages",
            headers={
                "Authorization": f"Bearer {NOTION_TOKEN}",
                "Notion-Version": "2022-06-28",
                "Content-Type": "application/json",
            },
            json={
                "parent": {"database_id": NOTION_DATABASE_ID},
                "properties": {
                    "Concepto": {
                        "title": [{"text": {"content": gasto["concepto"]}}]
                    },
                    "Monto": {
                        "number": gasto["monto"]
                    },
                    "Fecha": {
                        "date": {"start": gasto["fecha"]}
                    },
                    "Estado de Cuenta": {
                        "select": {"name": gasto["tarjeta"]}
                    },
                    "Subcategoría": {
                        "select": {"name": gasto["subcategoria"]}
                    },
                    "Presupuesto": {
                        "select": {"name": gasto["presupuesto"]}
                    },
                    "Mes": {
                        "select": {"name": gasto["mes"]}
                    },
                },
            },
            timeout=30,
        )
        return response.status_code == 200

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja los mensajes entrantes de Telegram."""
    texto = update.message.text
    fecha_hoy = datetime.now().strftime("%Y-%m-%d")

    await update.message.reply_text("⏳ Procesando tu gasto...")

    try:
        gasto = await parse_gasto_con_claude(texto, fecha_hoy)

        if "error" in gasto:
            await update.message.reply_text(f"❌ {gasto['error']}")
            return

        exito = await guardar_en_notion(gasto)

        if exito:
            respuesta = (
                f"✅ *Gasto guardado*\n\n"
                f"📌 {gasto['concepto']}\n"
                f"💰 ${gasto['monto']:,.2f}\n"
                f"🏷️ {gasto['subcategoria']} → {gasto['presupuesto']}\n"
                f"💳 {gasto['tarjeta']} → {gasto['mes']}\n"
                f"📅 {gasto['fecha']}"
            )
            await update.message.reply_text(respuesta, parse_mode="Markdown")
        else:
            await update.message.reply_text("❌ Error al guardar en Notion. Revisa la conexión.")

    except json.JSONDecodeError:
        await update.message.reply_text("❌ No pude interpretar el gasto. Intenta de nuevo.")
    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text(f"❌ Error inesperado: {str(e)}")

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("Bot iniciado...")
    app.run_polling()

if __name__ == "__main__":
    main()
