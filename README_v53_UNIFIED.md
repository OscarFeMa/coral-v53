# CORAL v5.3 - Aplicación Unificada

## 🧠 Memoria Local SQLite + Web API + Dashboard + Sincronización Cloud

### Arquitectura
```
┌─────────────────────────────────────────────────────────┐
│                    CORAL v5.3                          │
├─────────────────────────────────────────────────────────┤
│  🖥️  Interfaz Web (Dashboard)                           │
│     ├── Panel de Control                                │
│     ├── Gestor de Memoria                               │
│     ├── Debates en Vivo                                 │
│     └── Sincronización                                  │
├─────────────────────────────────────────────────────────┤
│  🌐 Web API REST (Flask)                                 │
│     ├── /api/status - Estado del sistema              │
│     ├── /api/entries - CRUD de memoria                  │
│     ├── /api/debates - Gestión de debates               │
│     └── /api/sync - Sincronización cloud                │
├─────────────────────────────────────────────────────────┤
│  💾 Memoria Local (SQLite)                               │
│     ├── memory_entries - Entradas de memoria            │
│     ├── debates - Debates completos                     │
│     ├── response_cache - Caché de respuestas            │
│     └── sync_log - Historial de sincronización          │
├─────────────────────────────────────────────────────────┤
│  ☁️  Sincronización Supabase (Opcional)                    │
│     ├── Sync automática cada 5 minutos                  │
│     ├── Bidireccional (subir/bajar)                     │
│     └── Backup en cloud                                 │
└─────────────────────────────────────────────────────────┘
```

---

## 🚀 Cómo Usar

### 1. Iniciar el Servidor

**Opción A - Ejecutable (Recomendado):**
```bash
F:\Proyectos\CORAL_v53_WebServer.exe
```

**Opción B - Script Batch:**
```bash
F:\Proyectos\start_coral_server.bat
```

**Opción C - Python:**
```bash
python coral_unified_app.py
```

### 2. Abrir Dashboard

Abre tu navegador en:
- **Dashboard:** http://localhost:5000/
- **API:** http://localhost:5000/api/status

### 3. Acceso Remoto (opcional)

El servidor escucha en todas las interfaces:
- Local: http://127.0.0.1:5000
- Red local: http://192.168.1.39:5000 (tu IP)

---

## 📊 Funcionalidades del Dashboard

### Dashboard Principal (`/`)
- Estado del sistema en tiempo real
- Estadísticas de memoria local
- Controles de sincronización rápida
- Estado de conexiones

### Gestor de Memoria (`/memory`)
- **Crear entradas** manuales
- **Ver todas** las entradas locales
- **Filtrar** por tipo, estado de sync, contenido
- **Eliminar** entradas
- **Paginación** (20 entradas por página)

### Debates (`/debates`)
- **Crear nuevos debates**
- **Seleccionar participantes** IAs
- **Ver debates activos** con intervenciones
- **Status de consenso** en tiempo real

### Sincronización (`/sync`)
- **Subir a Supabase** (cloud)
- **Descargar de Supabase** (local)
- **Sync bidireccional** completa
- **Historial** de sincronizaciones
- **Estadísticas** de pendientes

---

## 🔌 API REST Endpoints

### Estado del Sistema
```bash
GET /api/status
```
Retorna: estado, versión, estadísticas de sync, configuración

### Entradas de Memoria
```bash
# Listar entradas
GET /api/entries?type=manual&limit=100

# Crear entrada
POST /api/entries
{
  "entry_id": "unico_id",
  "ia_author": "user",
  "entry_type": "manual",
  "field_key": "mi_clave",
  "field_value": "contenido",
  "confidence": 0.85
}

# Eliminar entrada
DELETE /api/entries/{entry_id}
```

### Debates
```bash
# Listar debates
GET /api/debates?limit=50

# Crear debate
POST /api/debates
{
  "tema": "¿Debe la IA priorizar...?",
  "descripcion": "Contexto",
  "participantes": ["nexus", "vector", "iris", "sigma", "coral"]
}
```

### Sincronización
```bash
# Estado de sync
GET /api/sync/status

# Sincronizar
POST /api/sync
{
  "direction": "to_cloud" | "from_cloud" | "both"
}
```

---

## ⚙️ Configuración

### Variables de Entorno (`.env`)
```ini
SUPABASE_URL=https://jdbzjapshomatwyasmig.supabase.co
SUPABASE_ANON_KEY=tu_clave_aqui
OPENROUTER_API_KEY=sk-or-v1-...
```

### Configuración en Código
```python
# Config.py
SQLITE_DB = "coral_memory.db"      # Base de datos local
SYNC_INTERVAL = 300               # Segundos (5 min)
API_PORT = 5000                   # Puerto del servidor
API_HOST = "0.0.0.0"              # Escuchar en todas las IPs
```

---

## 📁 Estructura de Archivos

```
CORAL_v52_optimized/
├── coral_unified_app.py         # Aplicación principal
├── coral_memory.db              # Base de datos SQLite (se crea automático)
├── coral_cache.json             # Caché de respuestas
├── start_coral_server.bat       # Script de inicio rápido
├── .env                         # Variables de entorno
├── dist_v53/
│   └── CORAL_v53_WebServer.exe  # Ejecutable standalone
└── README_v53_UNIFIED.md        # Este archivo
```

---

## 🔒 Seguridad

- **SQLite local**: Datos privados en tu máquina
- **Sincronización opcional**: Solo si configuras Supabase
- **API sin auth**: Para uso local (añadir JWT si expones a internet)
- **CORS habilitado**: Permite acceso desde otros orígenes

---

## 🛠️ Resolución de Problemas

### Puerto 5000 ocupado
Cambiar en `coral_unified_app.py`:
```python
API_PORT = 5001  # u otro puerto
```

### Error de sincronización
Verificar en `.env`:
- SUPABASE_URL correcta
- SUPABASE_ANON_KEY válida

### Base de datos bloqueada
Cerrar otras instancias de CORAL que estén ejecutándose.

---

## 📝 Changelog v5.3

### Nuevas Características
- ✅ **Memoria local SQLite** persistente
- ✅ **Web API REST** completa con Flask
- ✅ **Dashboard web** integrado (4 vistas)
- ✅ **Sincronización bidireccional** automática
- ✅ **Gestor de memoria** con filtros y paginación
- ✅ **Sistema de debates** con intervenciones
- ✅ **Historial de sincronización**
- ✅ **Ejecutable standalone** (.exe)

### Mejoras
- 🚀 Arquitectura modular y escalable
- 🚀 UI responsive y moderna
- 🚀 Sync automática cada 5 minutos
- 🚀 Soporte para acceso remoto
- 🚀 API documentada y testeable

---

## 🎯 Roadmap v5.4 (Futuro)

- [ ] Autenticación JWT para API
- [ ] WebSockets para actualizaciones en tiempo real
- [ ] Sistema de plugins para IAs adicionales
- [ ] Exportación a PDF/Excel desde dashboard
- [ ] Notificaciones Discord/Email
- [ ] Modo "headless" sin interfaz web
- [ ] Docker container

---

**Autor:** Oscar Fernandez + Claude (Anthropic)  
**Versión:** 5.3.0  
**Fecha:** 2026-04-16  
**Costo:** $0.00 (OpenRouter gratuito)
