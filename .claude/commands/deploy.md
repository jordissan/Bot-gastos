# /deploy — Deploy completo a producción

Ejecuta el flujo de deploy en orden. No saltarse ningún paso.

## Pasos

### 1. Leer el TOKEN de .env
```bash
grep TELEGRAM_TOKEN /Users/jordi/Documents/Claude/Projects/Bot-gastos/.env
```

### 2. Borrar el webhook de Telegram
Reemplaza `{TOKEN}` con el valor leído en el paso anterior:
```bash
curl -s "https://api.telegram.org/bot{TOKEN}/deleteWebhook?drop_pending_updates=true"
```
Confirmar que la respuesta incluye `"ok":true`.

### 3. Verificar que no hay cambios sin commitear
```bash
git status
```
Si hay cambios sin commitear, preguntar a Jordi si commitearlos antes de hacer push.

### 4. Push a main
```bash
git push origin main
```
Render detecta el push automáticamente y dispara el deploy.

### 5. Confirmar al usuario
Informar que:
- El deploy se está procesando en Render (1-3 min aprox)
- Dashboard: https://dashboard.render.com
- Logs en vivo: https://dashboard.render.com/web/srv-cv4k2re3esus73ftnme0/logs
- Para verificar que arrancó correctamente, buscar en logs: `[APScheduler] Scheduler iniciado`

## Notas
- El webhook se registra automáticamente cuando el bot arranca en Render — no hace falta registrarlo manualmente.
- Si el deploy falla, Render hace rollback automático al commit anterior.
- Para rollback manual: revertir el commit en GitHub → Render lo detecta.
