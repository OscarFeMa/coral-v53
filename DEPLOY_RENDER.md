# Deploy CORAL v5.3 a Render.com

## 🚀 Instrucciones Paso a Paso

### 1. Preparar Archivos

Asegúrate de tener estos archivos en tu proyecto:
```
coral_unified_app.py      # App principal
requirements.txt          # Dependencias
render.yaml              # Configuración Render
.env                     # Variables de entorno (NO subir a git)
```

### 2. Crear Repositorio Git (si no existe)

```bash
cd C:\Users\usuario\.gemini\antigravity\brain\b1b550cf-92ba-4dab-a688-2526c91112cf\.system_generated\CORAL_v52_optimized
git init
git add coral_unified_app.py requirements.txt render.yaml README_v53_UNIFIED.md
git commit -m "CORAL v5.3 ready for Render deploy"
```

### 3. Subir a GitHub (necesario para Render)

Crea un repo nuevo en GitHub y:
```bash
git remote add origin https://github.com/tu-usuario/coral-v53.git
git push -u origin main
```

### 4. Deploy en Render

1. Ve a tu dashboard: https://dashboard.render.com/
2. Click "New +" → "Web Service"
3. Conecta tu repositorio GitHub
4. Configuración:
   - **Name:** coral-v53-webserver
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn coral_unified_app:app`
   - **Plan:** Free

5. Añade Environment Variables:
   - `SUPABASE_URL` = tu_url
   - `SUPABASE_ANON_KEY` = tu_key
   - `OPENROUTER_API_KEY` = tu_key

6. Click "Create Web Service"

### 5. Esperar Deploy

Render automáticamente:
- Instalará dependencias
- Iniciará gunicorn
- Asignará URL: `https://coral-v53-webserver.onrender.com`

⏱️ Tiempo: ~2-3 minutos

### 6. Verificar

Abre tu navegador en:
```
https://coral-v53-webserver.onrender.com/
```

Deberías ver el Dashboard de CORAL v5.3 online!

---

## ⚠️ Limitaciones del Plan Gratuito

- **Sleep:** Se apaga tras 15 min sin tráfico (30s para arrancar)
- **Disk:** SQLite se reinicia (no persiste entre sleeps)
- **Bandwith:** 100 GB/mes

**Solución para persistencia:** Usar Supabase como memoria principal, SQLite como caché local.

---

## 🔧 Solución de Problemas

### "Build failed"
Verificar `requirements.txt` tenga todas las dependencias.

### "Cannot connect to SQLite"
En Render (ephemeral), usar Supabase para persistencia real.

### "App crashed"
Revisar logs en Render Dashboard → Logs.

---

## 🌐 URL de tu App

Una vez deployado, tu app estará en:
```
https://coral-v53-webserver.onrender.com
```

**Accesible desde cualquier dispositivo con internet!**

---

## 📱 Probar API Online

```bash
curl https://coral-v53-webserver.onrender.com/api/status
```

Respuesta:
```json
{
  "status": "online",
  "version": "5.3.0",
  "supabase_connected": true
}
```

---

## 🎉 ¡Listo!

CORAL v5.3 ahora está **online en internet**.

Dashboard: https://coral-v53-webserver.onrender.com
