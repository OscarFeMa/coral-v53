"""
CORAL v5.3 - Aplicación Unificada
Memoria Local SQLite + Web API + Dashboard + Sincronización Cloud

Arquitectura:
- SQLite local para memoria persistente
- Flask API REST completa
- Dashboard web integrado
- Sincronización bidireccional con Supabase
- Sistema de debates con auditoría ética
"""

import os
import sys
import json
import time
import hashlib
import threading
import requests
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path

# Flask para Web API
try:
    from flask import Flask, jsonify, request, render_template_string, send_file
    from flask_cors import CORS
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False
    print("[WARN] Flask no disponible. Instalando...")
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "flask", "flask-cors", "-q"], check=True)
    from flask import Flask, jsonify, request, render_template_string
    from flask_cors import CORS
    FLASK_AVAILABLE = True

# Cargar variables de entorno
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ==================== CONFIGURACIÓN ====================

class Config:
    """Configuración de la aplicación"""
    SQLITE_DB = "coral_memory.db"
    CACHE_FILE = "coral_cache.json"
    SYNC_INTERVAL = 300  # 5 minutos
    API_PORT = 5000
    API_HOST = "0.0.0.0"
    SUPABASE_URL = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY", "")
    OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY", "")

# ==================== MODELOS DE DATOS ====================

class TipoIntervencion(Enum):
    APERTURA = "apertura"
    ARGUMENTO = "argumento"
    CONTRAARGUMENTO = "contraargumento"
    REFUTACION = "refutacion"
    PREGUNTA = "pregunta"
    CONSENSO = "consenso"

class DebateStatus(Enum):
    EN_DEBATE = "en_debate"
    CONSENSO_ALCANZADO = "consenso_alcanzado"
    BLOQUEADO = "bloqueado"

@dataclass
class Intervencion:
    ia_author: str
    tipo: TipoIntervencion
    contenido: str
    timestamp: str
    confidence_score: float
    modelo_usado: str
    
    def to_dict(self):
        return {
            "ia_author": self.ia_author,
            "tipo": self.tipo.value,
            "contenido": self.contenido,
            "timestamp": self.timestamp,
            "confidence_score": self.confidence_score,
            "modelo_usado": self.modelo_usado
        }

@dataclass
class Debate:
    id: str
    tema: str
    descripcion: str
    participantes: List[str]
    status: DebateStatus
    intervenciones: List[Intervencion]
    created_at: str
    consenso_score: float
    conclusion: str
    
    def to_dict(self):
        return {
            "id": self.id,
            "tema": self.tema,
            "descripcion": self.descripcion,
            "participantes": self.participantes,
            "status": self.status.value,
            "intervenciones": [i.to_dict() for i in self.intervenciones],
            "created_at": self.created_at,
            "consenso_score": self.consenso_score,
            "conclusion": self.conclusion
        }

# ==================== MEMORIA LOCAL SQLITE ====================

class LocalMemoryManager:
    """Gestor de memoria local SQLite con sincronización cloud"""
    
    def __init__(self, db_path: str = Config.SQLITE_DB):
        self.db_path = db_path
        self._init_db()
        self.sync_lock = threading.Lock()
        self.last_sync = None
    
    def _init_db(self):
        """Inicializa la base de datos SQLite"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Tabla de entradas de memoria
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS memory_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_id TEXT UNIQUE,
                ia_author TEXT,
                entry_type TEXT,
                field_key TEXT,
                field_value TEXT,
                confidence_score REAL DEFAULT 0.85,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                synced_to_cloud BOOLEAN DEFAULT 0,
                cloud_id TEXT
            )
        ''')
        
        # Tabla de debates
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS debates (
                id TEXT PRIMARY KEY,
                tema TEXT,
                descripcion TEXT,
                participantes TEXT,
                status TEXT,
                intervenciones TEXT,
                consenso_score REAL,
                conclusion TEXT,
                created_at TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                synced_to_cloud BOOLEAN DEFAULT 0
            )
        ''')
        
        # Tabla de caché
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS response_cache (
                key TEXT PRIMARY KEY,
                response TEXT,
                model TEXT,
                timestamp REAL,
                ttl_hours REAL DEFAULT 24
            )
        ''')
        
        # Tabla de sincronización
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sync_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sync_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                direction TEXT,
                entries_count INTEGER,
                status TEXT
            )
        ''')
        
        conn.commit()
        conn.close()
        print(f"[DB] Base de datos inicializada: {self.db_path}")
    
    def save_entry(self, entry_id: str, ia_author: str, entry_type: str, 
                   field_key: str, field_value: str, confidence: float = 0.85) -> bool:
        """Guarda una entrada en la memoria local"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO memory_entries 
                (entry_id, ia_author, entry_type, field_key, field_value, 
                 confidence_score, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (entry_id, ia_author, entry_type, field_key, 
                  field_value, confidence))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"[DB ERROR] {e}")
            return False
    
    def save_debate(self, debate: Debate) -> bool:
        """Guarda un debate completo"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO debates 
                (id, tema, descripcion, participantes, status, intervenciones,
                 consenso_score, conclusion, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (
                debate.id, debate.tema, debate.descripcion,
                json.dumps(debate.participantes), debate.status.value,
                json.dumps([i.to_dict() for i in debate.intervenciones]),
                debate.consenso_score, debate.conclusion, debate.created_at
            ))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"[DB ERROR] {e}")
            return False
    
    def get_debates(self, limit: int = 100) -> List[Dict]:
        """Obtiene debates de la memoria local"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT * FROM debates ORDER BY created_at DESC LIMIT ?
            ''', (limit,))
            
            rows = cursor.fetchall()
            conn.close()
            
            return [dict(row) for row in rows]
        except Exception as e:
            print(f"[DB ERROR] {e}")
            return []
    
    def get_entries(self, entry_type: Optional[str] = None, 
                    limit: int = 100) -> List[Dict]:
        """Obtiene entradas de memoria"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            if entry_type:
                cursor.execute('''
                    SELECT * FROM memory_entries 
                    WHERE entry_type = ? 
                    ORDER BY created_at DESC LIMIT ?
                ''', (entry_type, limit))
            else:
                cursor.execute('''
                    SELECT * FROM memory_entries 
                    ORDER BY created_at DESC LIMIT ?
                ''', (limit,))
            
            rows = cursor.fetchall()
            conn.close()
            
            return [dict(row) for row in rows]
        except Exception as e:
            print(f"[DB ERROR] {e}")
            return []
    
    def delete_entry(self, entry_id: str) -> bool:
        """Elimina una entrada"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('DELETE FROM memory_entries WHERE entry_id = ?', (entry_id,))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"[DB ERROR] {e}")
            return False
    
    # ==================== SINCRONIZACIÓN CLOUD ====================
    
    def sync_to_cloud(self) -> Dict:
        """Sincroniza datos locales a Supabase"""
        if not Config.SUPABASE_URL or not Config.SUPABASE_KEY:
            return {"status": "skipped", "message": "Supabase no configurado - modo offline", "synced": 0}
        
        headers = {
            "apikey": Config.SUPABASE_KEY,
            "Authorization": f"Bearer {Config.SUPABASE_KEY}",
            "Content-Type": "application/json"
        }
        
        try:
            # Obtener entradas no sincronizadas
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM memory_entries 
                WHERE synced_to_cloud = 0 
                LIMIT 50
            ''')
            entries = cursor.fetchall()
            conn.close()
            
            if not entries:
                return {"status": "success", "synced": 0, "message": "Nada para sincronizar"}
            
            # Enviar a Supabase
            url = f"{Config.SUPABASE_URL}/rest/v1/memory_entries"
            
            synced_count = 0
            for entry in entries:
                payload = {
                    "ia_author": entry[2],
                    "entry_type": entry[3],
                    "field_key": entry[4],
                    "field_value": entry[5],
                    "confidence_score": entry[6]
                }
                
                response = requests.post(url, headers=headers, json=payload)
                if response.status_code == 201:
                    synced_count += 1
                    # Marcar como sincronizado
                    conn = sqlite3.connect(self.db_path)
                    cursor = conn.cursor()
                    cursor.execute('''
                        UPDATE memory_entries 
                        SET synced_to_cloud = 1, cloud_id = ?
                        WHERE id = ?
                    ''', (response.json().get('id', ''), entry[0]))
                    conn.commit()
                    conn.close()
            
            # Registrar sincronización
            self._log_sync("to_cloud", synced_count, "success")
            
            return {
                "status": "success", 
                "synced": synced_count,
                "message": f"{synced_count} entradas sincronizadas"
            }
            
        except Exception as e:
            self._log_sync("to_cloud", 0, f"error: {e}")
            return {"status": "error", "message": str(e)}
    
    def sync_from_cloud(self) -> Dict:
        """Descarga datos de Supabase a local"""
        if not Config.SUPABASE_URL or not Config.SUPABASE_KEY:
            return {"status": "skipped", "message": "Supabase no configurado - modo offline", "downloaded": 0}
        
        headers = {
            "apikey": Config.SUPABASE_KEY,
            "Authorization": f"Bearer {Config.SUPABASE_KEY}",
            "Content-Type": "application/json"
        }
        
        try:
            # Obtener última sincronización
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT MAX(sync_time) FROM sync_log 
                WHERE direction = 'from_cloud' AND status = 'success'
            ''')
            last_sync = cursor.fetchone()[0]
            conn.close()
            
            # Consultar Supabase
            url = f"{Config.SUPABASE_URL}/rest/v1/memory_entries?order=created_at.desc&limit=100"
            if last_sync:
                url += f"&created_at=gt.{last_sync}"
            
            response = requests.get(url, headers=headers)
            
            if response.status_code == 200:
                cloud_entries = response.json()
                
                # Guardar localmente
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                for entry in cloud_entries:
                    cursor.execute('''
                        INSERT OR IGNORE INTO memory_entries 
                        (entry_id, ia_author, entry_type, field_key, field_value,
                         confidence_score, created_at, synced_to_cloud, cloud_id)
                        VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
                    ''', (
                        entry.get('id'), entry.get('ia_author'),
                        entry.get('entry_type'), entry.get('field_key'),
                        entry.get('field_value'), entry.get('confidence_score', 0.85),
                        entry.get('created_at'), entry.get('id')
                    ))
                
                conn.commit()
                conn.close()
                
                self._log_sync("from_cloud", len(cloud_entries), "success")
                
                return {
                    "status": "success",
                    "downloaded": len(cloud_entries),
                    "message": f"{len(cloud_entries)} entradas descargadas"
                }
            else:
                return {"status": "error", "message": f"HTTP {response.status_code}"}
                
        except Exception as e:
            self._log_sync("from_cloud", 0, f"error: {e}")
            return {"status": "error", "message": str(e)}
    
    def _log_sync(self, direction: str, count: int, status: str):
        """Registra una sincronización"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO sync_log (direction, entries_count, status)
                VALUES (?, ?, ?)
            ''', (direction, count, status))
            conn.commit()
            conn.close()
        except:
            pass
    
    def get_sync_status(self) -> Dict:
        """Obtiene estado de sincronización"""
        # Si no hay Supabase, retornar estado offline
        if not Config.SUPABASE_URL or not Config.SUPABASE_KEY:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute('SELECT COUNT(*) FROM memory_entries')
                total_local = cursor.fetchone()[0]
                conn.close()
                return {
                    "pending_sync": 0,
                    "total_local": total_local,
                    "mode": "offline",
                    "last_sync": {"time": None, "direction": None, "count": 0, "status": "offline"}
                }
            except:
                return {"error": "offline", "total_local": 0}
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Entradas pendientes
            cursor.execute('SELECT COUNT(*) FROM memory_entries WHERE synced_to_cloud = 0')
            pending = cursor.fetchone()[0]
            
            # Total local
            cursor.execute('SELECT COUNT(*) FROM memory_entries')
            total_local = cursor.fetchone()[0]
            
            # Última sincronización
            cursor.execute('''
                SELECT sync_time, direction, entries_count, status
                FROM sync_log ORDER BY sync_time DESC LIMIT 1
            ''')
            last_sync = cursor.fetchone()
            
            conn.close()
            
            return {
                "pending_sync": pending,
                "total_local": total_local,
                "last_sync": {
                    "time": last_sync[0] if last_sync else None,
                    "direction": last_sync[1] if last_sync else None,
                    "count": last_sync[2] if last_sync else 0,
                    "status": last_sync[3] if last_sync else None
                }
            }
        except Exception as e:
            return {"error": str(e)}

# ==================== WEB API FLASK ====================

class CoralWebApp:
    """Aplicación Web Flask con API REST y Dashboard"""
    
    def __init__(self, memory_manager: LocalMemoryManager):
        self.memory = memory_manager
        self.app = Flask(__name__)
        CORS(self.app)
        self._setup_routes()
    
    def _setup_routes(self):
        """Configura las rutas de la API"""
        
        # ========== API REST ==========
        
        @self.app.route('/api/status')
        def api_status():
            """Estado de la API"""
            sync_status = self.memory.get_sync_status()
            return jsonify({
                "status": "online",
                "version": "5.3.0",
                "timestamp": datetime.now().isoformat(),
                "sync": sync_status,
                "database": Config.SQLITE_DB,
                "supabase_connected": bool(Config.SUPABASE_URL)
            })
        
        @self.app.route('/api/entries', methods=['GET', 'POST'])
        def api_entries():
            """CRUD para entradas de memoria"""
            if request.method == 'GET':
                entry_type = request.args.get('type')
                limit = request.args.get('limit', 100, type=int)
                entries = self.memory.get_entries(entry_type, limit)
                return jsonify({
                    "count": len(entries),
                    "entries": entries
                })
            
            elif request.method == 'POST':
                data = request.json
                success = self.memory.save_entry(
                    entry_id=data.get('entry_id', f"local_{datetime.now().timestamp()}"),
                    ia_author=data.get('ia_author', 'user'),
                    entry_type=data.get('entry_type', 'manual'),
                    field_key=data.get('field_key', ''),
                    field_value=data.get('field_value', ''),
                    confidence=data.get('confidence', 0.85)
                )
                return jsonify({"success": success}), 201 if success else 400
        
        @self.app.route('/api/entries/<entry_id>', methods=['DELETE'])
        def api_delete_entry(entry_id):
            """Elimina una entrada"""
            success = self.memory.delete_entry(entry_id)
            return jsonify({"success": success})
        
        @self.app.route('/api/debates', methods=['GET', 'POST'])
        def api_debates():
            """Gestión de debates"""
            if request.method == 'GET':
                limit = request.args.get('limit', 100, type=int)
                debates = self.memory.get_debates(limit)
                return jsonify({
                    "count": len(debates),
                    "debates": debates
                })
            
            elif request.method == 'POST':
                data = request.json
                # Crear debate
                debate = Debate(
                    id=f"debate_v53_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                    tema=data.get('tema', 'Sin tema'),
                    descripcion=data.get('descripcion', ''),
                    participantes=data.get('participantes', ['nexus', 'vector', 'iris', 'sigma', 'coral']),
                    status=DebateStatus.EN_DEBATE,
                    intervenciones=[],
                    created_at=datetime.now().isoformat(),
                    consenso_score=0,
                    conclusion=''
                )
                success = self.memory.save_debate(debate)
                return jsonify({"success": success, "debate": debate.to_dict()}), 201
        
        @self.app.route('/api/sync', methods=['POST'])
        def api_sync():
            """Sincronización manual"""
            direction = request.json.get('direction', 'both')
            
            results = {}
            if direction in ['to_cloud', 'both']:
                results['to_cloud'] = self.memory.sync_to_cloud()
            if direction in ['from_cloud', 'both']:
                results['from_cloud'] = self.memory.sync_from_cloud()
            
            return jsonify(results)
        
        @self.app.route('/api/sync/status')
        def api_sync_status():
            """Estado de sincronización"""
            return jsonify(self.memory.get_sync_status())
        
        # ========== DASHBOARD WEB ==========
        
        @self.app.route('/')
        def dashboard():
            """Dashboard principal"""
            return render_template_string(DASHBOARD_HTML, version="5.3.0")
        
        @self.app.route('/memory')
        def memory_view():
            """Vista de memoria"""
            return render_template_string(MEMORY_HTML)
        
        @self.app.route('/debates')
        def debates_view():
            """Vista de debates"""
            return render_template_string(DEBATES_HTML)
        
        @self.app.route('/sync')
        def sync_view():
            """Vista de sincronización"""
            return render_template_string(SYNC_HTML)
    
    def run(self, host: str = Config.API_HOST, port: int = Config.API_PORT, debug: bool = False):
        """Inicia el servidor web"""
        print(f"[WEB] Iniciando servidor en http://{host}:{port}")
        print(f"[WEB] Dashboard: http://localhost:{port}/")
        print(f"[WEB] API: http://localhost:{port}/api/")
        self.app.run(host=host, port=port, debug=debug)

# ==================== TEMPLATES HTML ====================

DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CORAL v5.3 - Dashboard</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: 'Segoe UI', system-ui, sans-serif; 
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #eee; min-height: 100vh;
        }
        .navbar { 
            background: rgba(102, 126, 234, 0.2); 
            padding: 15px 30px; 
            backdrop-filter: blur(10px);
            border-bottom: 1px solid rgba(102, 126, 234, 0.3);
        }
        .navbar h1 { display: inline; font-size: 1.5em; }
        .nav-links { float: right; margin-top: 5px; }
        .nav-links a { 
            color: #fff; text-decoration: none; margin-left: 20px; 
            padding: 8px 16px; border-radius: 6px;
            transition: all 0.3s;
        }
        .nav-links a:hover { background: rgba(102, 126, 234, 0.3); }
        .container { max-width: 1400px; margin: 0 auto; padding: 30px; }
        .grid { 
            display: grid; 
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); 
            gap: 20px; margin-bottom: 30px;
        }
        .card { 
            background: rgba(22, 33, 62, 0.8); 
            padding: 25px; border-radius: 12px;
            border: 1px solid rgba(102, 126, 234, 0.2);
            transition: transform 0.3s;
        }
        .card:hover { transform: translateY(-5px); }
        .card h3 { 
            color: #667eea; font-size: 0.9em; text-transform: uppercase; 
            margin-bottom: 10px; letter-spacing: 1px;
        }
        .card .value { font-size: 2.8em; font-weight: bold; }
        .card .subtitle { opacity: 0.7; font-size: 0.9em; margin-top: 5px; }
        .section { 
            background: rgba(22, 33, 62, 0.6); 
            padding: 25px; border-radius: 12px; 
            margin-bottom: 20px;
        }
        .section h2 { 
            color: #667eea; margin-bottom: 20px; 
            border-bottom: 2px solid #667eea; padding-bottom: 10px;
        }
        .btn { 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white; border: none; padding: 12px 24px;
            border-radius: 8px; cursor: pointer; font-size: 1em;
            transition: all 0.3s;
        }
        .btn:hover { transform: scale(1.05); box-shadow: 0 5px 20px rgba(102, 126, 234, 0.4); }
        table { width: 100%; border-collapse: collapse; margin-top: 15px; }
        th, td { 
            padding: 12px; text-align: left; 
            border-bottom: 1px solid rgba(102, 126, 234, 0.2);
        }
        th { color: #667eea; font-weight: 600; }
        tr:hover { background: rgba(102, 126, 234, 0.1); }
        .status-online { color: #10b981; }
        .status-offline { color: #ef4444; }
        .sync-btn { 
            background: linear-gradient(135deg, #10b981 0%, #059669 100%); 
            margin-right: 10px;
        }
        #loading { display: none; text-align: center; padding: 20px; }
        .spinner { 
            border: 3px solid rgba(255,255,255,0.1); 
            border-top: 3px solid #667eea; 
            border-radius: 50%; width: 30px; height: 30px;
            animation: spin 1s linear infinite; margin: 0 auto 10px;
        }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
    </style>
</head>
<body>
    <nav class="navbar">
        <h1>🧠 CORAL v{{ version }}</h1>
        <div class="nav-links">
            <a href="/">Dashboard</a>
            <a href="/memory">Memoria</a>
            <a href="/debates">Debates</a>
            <a href="/sync">Sincronización</a>
        </div>
    </nav>
    
    <div class="container">
        <div id="loading">
            <div class="spinner"></div>
            <p>Cargando datos...</p>
        </div>
        
        <div class="grid" id="stats-grid">
            <div class="card">
                <h3>Estado del Sistema</h3>
                <div class="value" id="system-status">...</div>
                <div class="subtitle">CORAL v5.3 Unificado</div>
            </div>
            <div class="card">
                <h3>Entradas Locales</h3>
                <div class="value" id="local-count">...</div>
                <div class="subtitle">En base de datos SQLite</div>
            </div>
            <div class="card">
                <h3>Pendientes Sync</h3>
                <div class="value" id="pending-count">...</div>
                <div class="subtitle">Para subir a Supabase</div>
            </div>
            <div class="card">
                <h3>Última Sincronización</h3>
                <div class="value" id="last-sync">...</div>
                <div class="subtitle" id="last-sync-detail">...</div>
            </div>
        </div>
        
        <div class="section">
            <h2>Acciones Rápidas</h2>
            <button class="btn sync-btn" onclick="syncToCloud()">☁️ Sincronizar a Cloud</button>
            <button class="btn sync-btn" onclick="syncFromCloud()">📥 Descargar de Cloud</button>
            <button class="btn" onclick="location.href='/debates'">💬 Nuevo Debate</button>
            <button class="btn" onclick="location.href='/memory'">📝 Ver Memoria</button>
        </div>
        
        <div class="section">
            <h2>Estado de Conexiones</h2>
            <table>
                <tr>
                    <th>Servicio</th>
                    <th>Estado</th>
                    <th>Detalles</th>
                </tr>
                <tr>
                    <td>SQLite Local</td>
                    <td class="status-online">● Online</td>
                    <td>coral_memory.db</td>
                </tr>
                <tr>
                    <td>Supabase Cloud</td>
                    <td id="supabase-status">...</td>
                    <td id="supabase-detail">...</td>
                </tr>
                <tr>
                    <td>Web API</td>
                    <td class="status-online">● Online</td>
                    <td>Activa en puerto 5000</td>
                </tr>
            </table>
        </div>
    </div>
    
    <script>
        async function loadStatus() {
            document.getElementById('loading').style.display = 'block';
            try {
                const response = await fetch('/api/status');
                const data = await response.json();
                
                document.getElementById('system-status').innerHTML = 
                    '<span class="status-online">● Online</span>';
                document.getElementById('local-count').textContent = data.sync.total_local || 0;
                document.getElementById('pending-count').textContent = data.sync.pending_sync || 0;
                
                if (data.sync.last_sync.time) {
                    const date = new Date(data.sync.last_sync.time);
                    document.getElementById('last-sync').textContent = 
                        date.toLocaleTimeString();
                    document.getElementById('last-sync-detail').textContent = 
                        data.sync.last_sync.direction + ' - ' + data.sync.last_sync.status;
                } else {
                    document.getElementById('last-sync').textContent = 'Nunca';
                    document.getElementById('last-sync-detail').textContent = 
                        'Sin sincronizaciones previas';
                }
                
                if (data.supabase_connected) {
                    document.getElementById('supabase-status').innerHTML = 
                        '<span class="status-online">● Connected</span>';
                    document.getElementById('supabase-detail').textContent = 
                        data.sync.pending_sync + ' entradas pendientes';
                } else {
                    document.getElementById('supabase-status').innerHTML = 
                        '<span class="status-offline">● Disconnected</span>';
                    document.getElementById('supabase-detail').textContent = 
                        'Sin claves API configuradas';
                }
                
            } catch (e) {
                console.error('Error loading status:', e);
            }
            document.getElementById('loading').style.display = 'none';
        }
        
        async function syncToCloud() {
            if (!confirm('¿Sincronizar datos locales a Supabase?')) return;
            document.getElementById('loading').style.display = 'block';
            try {
                const response = await fetch('/api/sync', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({direction: 'to_cloud'})
                });
                const data = await response.json();
                alert(data.to_cloud.message || 'Sincronización completada');
                loadStatus();
            } catch (e) {
                alert('Error: ' + e.message);
            }
            document.getElementById('loading').style.display = 'none';
        }
        
        async function syncFromCloud() {
            if (!confirm('¿Descargar datos de Supabase? Esto puede sobrescribir datos locales.')) return;
            document.getElementById('loading').style.display = 'block';
            try {
                const response = await fetch('/api/sync', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({direction: 'from_cloud'})
                });
                const data = await response.json();
                alert(data.from_cloud.message || 'Descarga completada');
                loadStatus();
            } catch (e) {
                alert('Error: ' + e.message);
            }
            document.getElementById('loading').style.display = 'none';
        }
        
        // Cargar al iniciar
        loadStatus();
        // Actualizar cada 30 segundos
        setInterval(loadStatus, 30000);
    </script>
</body>
</html>
"""

MEMORY_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Memoria - CORAL v5.3</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: 'Segoe UI', system-ui, sans-serif; 
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #eee; min-height: 100vh;
        }
        .navbar { 
            background: rgba(102, 126, 234, 0.2); 
            padding: 15px 30px; 
            backdrop-filter: blur(10px);
            border-bottom: 1px solid rgba(102, 126, 234, 0.3);
        }
        .navbar h1 { display: inline; font-size: 1.5em; }
        .nav-links { float: right; margin-top: 5px; }
        .nav-links a { 
            color: #fff; text-decoration: none; margin-left: 20px; 
            padding: 8px 16px; border-radius: 6px;
            transition: all 0.3s;
        }
        .nav-links a:hover { background: rgba(102, 126, 234, 0.3); }
        .container { max-width: 1400px; margin: 0 auto; padding: 30px; }
        .section { 
            background: rgba(22, 33, 62, 0.6); 
            padding: 25px; border-radius: 12px; 
            margin-bottom: 20px;
        }
        .section h2 { 
            color: #667eea; margin-bottom: 20px; 
            border-bottom: 2px solid #667eea; padding-bottom: 10px;
        }
        .form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-bottom: 20px; }
        .form-group { display: flex; flex-direction: column; }
        .form-group label { margin-bottom: 5px; color: #667eea; font-size: 0.9em; }
        .form-group input, .form-group textarea, .form-group select {
            padding: 10px; border-radius: 6px; border: 1px solid rgba(102, 126, 234, 0.3);
            background: rgba(0,0,0,0.2); color: #fff; font-size: 1em;
        }
        .form-group textarea { min-height: 100px; resize: vertical; }
        .btn { 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white; border: none; padding: 12px 24px;
            border-radius: 8px; cursor: pointer; font-size: 1em;
            transition: all 0.3s;
        }
        .btn:hover { transform: scale(1.05); }
        .btn-danger { background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%); }
        table { width: 100%; border-collapse: collapse; margin-top: 15px; }
        th, td { 
            padding: 12px; text-align: left; 
            border-bottom: 1px solid rgba(102, 126, 234, 0.2);
            max-width: 300px; overflow: hidden; text-overflow: ellipsis;
        }
        th { color: #667eea; font-weight: 600; }
        tr:hover { background: rgba(102, 126, 234, 0.1); }
        .badge { 
            display: inline-block; padding: 4px 8px; border-radius: 4px; 
            font-size: 0.8em; background: rgba(102, 126, 234, 0.3);
        }
        .synced { background: rgba(16, 185, 129, 0.3); color: #10b981; }
        .pending { background: rgba(245, 158, 11, 0.3); color: #f59e0b; }
        .filters { display: flex; gap: 10px; margin-bottom: 20px; }
        .filters input, .filters select {
            padding: 8px 12px; border-radius: 6px;
            border: 1px solid rgba(102, 126, 234, 0.3);
            background: rgba(0,0,0,0.2); color: #fff;
        }
        .pagination { display: flex; justify-content: center; gap: 10px; margin-top: 20px; }
        .pagination button {
            padding: 8px 16px; border-radius: 6px;
            border: 1px solid rgba(102, 126, 234, 0.3);
            background: rgba(0,0,0,0.2); color: #fff; cursor: pointer;
        }
        .pagination button:hover { background: rgba(102, 126, 234, 0.3); }
        .pagination button:disabled { opacity: 0.5; cursor: not-allowed; }
    </style>
</head>
<body>
    <nav class="navbar">
        <h1>🧠 CORAL v5.3</h1>
        <div class="nav-links">
            <a href="/">Dashboard</a>
            <a href="/memory">Memoria</a>
            <a href="/debates">Debates</a>
            <a href="/sync">Sincronización</a>
        </div>
    </nav>
    
    <div class="container">
        <div class="section">
            <h2>➕ Nueva Entrada</h2>
            <form id="entry-form">
                <div class="form-grid">
                    <div class="form-group">
                        <label>ID de Entrada</label>
                        <input type="text" id="entry-id" placeholder="auto-generado si vacío">
                    </div>
                    <div class="form-group">
                        <label>Autor IA</label>
                        <select id="ia-author">
                            <option value="user">Usuario</option>
                            <option value="nexus">NEXUS</option>
                            <option value="vector">VECTOR</option>
                            <option value="iris">IRIS</option>
                            <option value="sigma">SIGMA</option>
                            <option value="coral">CORAL</option>
                            <option value="system">Sistema</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label>Tipo de Entrada</label>
                        <select id="entry-type">
                            <option value="manual">Manual</option>
                            <option value="debate">Debate</option>
                            <option value="assertion">Aserción</option>
                            <option value="question">Pregunta</option>
                            <option value="cache">Caché</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label>Clave (field_key)</label>
                        <input type="text" id="field-key" placeholder="ej: debate_001_nexus">
                    </div>
                </div>
                <div class="form-group" style="margin-bottom: 15px;">
                    <label>Valor (field_value)</label>
                    <textarea id="field-value" placeholder="Contenido de la entrada..."></textarea>
                </div>
                <div class="form-group" style="margin-bottom: 15px;">
                    <label>Score de Confianza</label>
                    <input type="range" id="confidence" min="0" max="1" step="0.01" value="0.85" 
                           style="width: 200px;" oninput="document.getElementById('conf-val').textContent=this.value">
                    <span id="conf-val" style="margin-left: 10px;">0.85</span>
                </div>
                <button type="submit" class="btn">💾 Guardar Entrada</button>
            </form>
        </div>
        
        <div class="section">
            <h2>📋 Entradas de Memoria</h2>
            <div class="filters">
                <input type="text" id="search-filter" placeholder="Buscar..." onkeyup="loadEntries()">
                <select id="type-filter" onchange="loadEntries()">
                    <option value="">Todos los tipos</option>
                    <option value="manual">Manual</option>
                    <option value="debate">Debate</option>
                    <option value="assertion">Aserción</option>
                    <option value="cache">Caché</option>
                </select>
                <select id="sync-filter" onchange="loadEntries()">
                    <option value="">Todos</option>
                    <option value="0">Pendientes sync</option>
                    <option value="1">Sincronizados</option>
                </select>
                <button class="btn" onclick="loadEntries()">🔄 Actualizar</button>
            </div>
            <table>
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Autor</th>
                        <th>Tipo</th>
                        <th>Clave</th>
                        <th>Valor</th>
                        <th>Score</th>
                        <th>Sync</th>
                        <th>Acciones</th>
                    </tr>
                </thead>
                <tbody id="entries-table">
                    <tr><td colspan="8" style="text-align:center;">Cargando...</td></tr>
                </tbody>
            </table>
            <div class="pagination" id="pagination"></div>
        </div>
    </div>
    
    <script>
        let currentPage = 1;
        const pageSize = 20;
        let allEntries = [];
        
        async function loadEntries() {
            try {
                const response = await fetch('/api/entries?limit=200');
                const data = await response.json();
                allEntries = data.entries || [];
                
                // Aplicar filtros
                const searchTerm = document.getElementById('search-filter').value.toLowerCase();
                const typeFilter = document.getElementById('type-filter').value;
                const syncFilter = document.getElementById('sync-filter').value;
                
                let filtered = allEntries.filter(e => {
                    if (searchTerm && !JSON.stringify(e).toLowerCase().includes(searchTerm)) return false;
                    if (typeFilter && e.entry_type !== typeFilter) return false;
                    if (syncFilter && e.synced_to_cloud !== parseInt(syncFilter)) return false;
                    return true;
                });
                
                renderTable(filtered);
                renderPagination(filtered.length);
            } catch (e) {
                console.error('Error:', e);
            }
        }
        
        function renderTable(entries) {
            const tbody = document.getElementById('entries-table');
            const start = (currentPage - 1) * pageSize;
            const page = entries.slice(start, start + pageSize);
            
            if (page.length === 0) {
                tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;">No hay entradas</td></tr>';
                return;
            }
            
            tbody.innerHTML = page.map(e => `
                <tr>
                    <td title="${e.entry_id}">${e.entry_id ? e.entry_id.substring(0, 15) + '...' : 'N/A'}</td>
                    <td><span class="badge">${e.ia_author}</span></td>
                    <td>${e.entry_type}</td>
                    <td title="${e.field_key}">${e.field_key ? e.field_key.substring(0, 20) + '...' : ''}</td>
                    <td title="${e.field_value}">${e.field_value ? e.field_value.substring(0, 40) + '...' : ''}</td>
                    <td>${e.confidence_score ? e.confidence_score.toFixed(2) : '0.00'}</td>
                    <td><span class="badge ${e.synced_to_cloud ? 'synced' : 'pending'}">${e.synced_to_cloud ? '✓' : '⏳'}</span></td>
                    <td>
                        <button class="btn btn-danger" onclick="deleteEntry('${e.entry_id}')" style="padding: 4px 8px; font-size: 0.8em;">🗑️</button>
                    </td>
                </tr>
            `).join('');
        }
        
        function renderPagination(total) {
            const totalPages = Math.ceil(total / pageSize);
            const pagination = document.getElementById('pagination');
            
            let html = `
                <button onclick="changePage(${currentPage - 1})" ${currentPage === 1 ? 'disabled' : ''}>← Anterior</button>
                <span style="padding: 8px;">Página ${currentPage} de ${totalPages}</span>
                <button onclick="changePage(${currentPage + 1})" ${currentPage >= totalPages ? 'disabled' : ''}>Siguiente →</button>
            `;
            pagination.innerHTML = html;
        }
        
        function changePage(page) {
            currentPage = page;
            loadEntries();
        }
        
        async function deleteEntry(entryId) {
            if (!confirm('¿Eliminar esta entrada permanentemente?')) return;
            try {
                await fetch(`/api/entries/${entryId}`, { method: 'DELETE' });
                loadEntries();
            } catch (e) {
                alert('Error al eliminar: ' + e.message);
            }
        }
        
        document.getElementById('entry-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const data = {
                entry_id: document.getElementById('entry-id').value || undefined,
                ia_author: document.getElementById('ia-author').value,
                entry_type: document.getElementById('entry-type').value,
                field_key: document.getElementById('field-key').value,
                field_value: document.getElementById('field-value').value,
                confidence: parseFloat(document.getElementById('confidence').value)
            };
            
            try {
                const response = await fetch('/api/entries', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(data)
                });
                
                if (response.ok) {
                    alert('✅ Entrada guardada');
                    document.getElementById('entry-form').reset();
                    document.getElementById('conf-val').textContent = '0.85';
                    loadEntries();
                } else {
                    alert('❌ Error al guardar');
                }
            } catch (e) {
                alert('Error: ' + e.message);
            }
        });
        
        // Cargar al iniciar
        loadEntries();
    </script>
</body>
</html>
"""

DEBATES_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Debates - CORAL v5.3</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: 'Segoe UI', system-ui, sans-serif; 
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #eee; min-height: 100vh;
        }
        .navbar { 
            background: rgba(102, 126, 234, 0.2); 
            padding: 15px 30px; 
            backdrop-filter: blur(10px);
        }
        .navbar h1 { display: inline; font-size: 1.5em; }
        .nav-links { float: right; margin-top: 5px; }
        .nav-links a { 
            color: #fff; text-decoration: none; margin-left: 20px; 
            padding: 8px 16px; border-radius: 6px;
        }
        .nav-links a:hover { background: rgba(102, 126, 234, 0.3); }
        .container { max-width: 1400px; margin: 0 auto; padding: 30px; }
        .section { 
            background: rgba(22, 33, 62, 0.6); 
            padding: 25px; border-radius: 12px; 
            margin-bottom: 20px;
        }
        .section h2 { 
            color: #667eea; margin-bottom: 20px; 
            border-bottom: 2px solid #667eea; padding-bottom: 10px;
        }
        .btn { 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white; border: none; padding: 12px 24px;
            border-radius: 8px; cursor: pointer; font-size: 1em;
        }
        .btn:hover { transform: scale(1.05); }
        .form-group { margin-bottom: 15px; }
        .form-group label { display: block; margin-bottom: 5px; color: #667eea; }
        .form-group input, .form-group textarea, .form-group select {
            width: 100%; padding: 10px; border-radius: 6px;
            border: 1px solid rgba(102, 126, 234, 0.3);
            background: rgba(0,0,0,0.2); color: #fff;
        }
        .form-group textarea { min-height: 80px; }
        .checkbox-group { display: flex; gap: 15px; flex-wrap: wrap; }
        .checkbox-group label { display: flex; align-items: center; gap: 5px; }
        .debate-card {
            background: rgba(102, 126, 234, 0.1);
            padding: 20px; border-radius: 10px;
            margin-bottom: 15px; border: 1px solid rgba(102, 126, 234, 0.2);
        }
        .debate-card h3 { color: #667eea; margin-bottom: 10px; }
        .debate-meta { display: flex; gap: 20px; font-size: 0.9em; opacity: 0.8; }
        .status-badge {
            display: inline-block; padding: 4px 12px; border-radius: 20px;
            font-size: 0.8em; font-weight: bold;
        }
        .status-consenso { background: rgba(16, 185, 129, 0.3); color: #10b981; }
        .status-debate { background: rgba(245, 158, 11, 0.3); color: #f59e0b; }
        .intervencion {
            background: rgba(0,0,0,0.2); padding: 10px; border-radius: 6px;
            margin: 10px 0; border-left: 3px solid #667eea;
        }
        .intervencion-header { display: flex; justify-content: space-between; margin-bottom: 5px; }
        .ia-badge { background: #667eea; padding: 2px 8px; border-radius: 4px; font-size: 0.8em; }
        .score-badge { background: rgba(255,255,255,0.1); padding: 2px 8px; border-radius: 4px; font-size: 0.8em; }
    </style>
</head>
<body>
    <nav class="navbar">
        <h1>🧠 CORAL v5.3</h1>
        <div class="nav-links">
            <a href="/">Dashboard</a>
            <a href="/memory">Memoria</a>
            <a href="/debates">Debates</a>
            <a href="/sync">Sincronización</a>
        </div>
    </nav>
    
    <div class="container">
        <div class="section">
            <h2>➕ Nuevo Debate</h2>
            <form id="debate-form">
                <div class="form-group">
                    <label>Tema del Debate</label>
                    <input type="text" id="tema" placeholder="¿Debe la IA priorizar...?" required>
                </div>
                <div class="form-group">
                    <label>Descripción</label>
                    <textarea id="descripcion" placeholder="Contexto adicional del debate..."></textarea>
                </div>
                <div class="form-group">
                    <label>Participantes IAs</label>
                    <div class="checkbox-group">
                        <label><input type="checkbox" value="nexus" checked> NEXUS (Analista)</label>
                        <label><input type="checkbox" value="vector" checked> VECTOR (Crítico)</label>
                        <label><input type="checkbox" value="iris" checked> IRIS (Ética)</label>
                        <label><input type="checkbox" value="sigma" checked> SIGMA (Lógica)</label>
                        <label><input type="checkbox" value="coral" checked> CORAL (Moderador)</label>
                    </div>
                </div>
                <button type="submit" class="btn">🚀 Crear Debate</button>
            </form>
        </div>
        
        <div class="section">
            <h2>💬 Debates Activos</h2>
            <div id="debates-list">
                <p style="text-align:center; opacity:0.7;">Cargando debates...</p>
            </div>
        </div>
    </div>
    
    <script>
        async function loadDebates() {
            try {
                const response = await fetch('/api/debates?limit=50');
                const data = await response.json();
                
                const container = document.getElementById('debates-list');
                if (data.debates.length === 0) {
                    container.innerHTML = '<p style="text-align:center; opacity:0.7;">No hay debates</p>';
                    return;
                }
                
                container.innerHTML = data.debates.map(d => {
                    const intervenciones = JSON.parse(d.intervenciones || '[]');
                    const statusClass = d.status === 'consenso_alcanzado' ? 'status-consenso' : 'status-debate';
                    const statusText = d.status === 'consenso_alcanzado' ? '✓ Consenso' : '○ En debate';
                    
                    return `
                        <div class="debate-card">
                            <h3>${d.tema}</h3>
                            <div class="debate-meta">
                                <span>ID: ${d.id.substring(0, 20)}...</span>
                                <span class="status-badge ${statusClass}">${statusText}</span>
                                <span>Score: ${(d.consenso_score || 0).toFixed(2)}</span>
                                <span>${new Date(d.created_at).toLocaleDateString()}</span>
                            </div>
                            <p style="margin: 10px 0; opacity: 0.9;">${d.descripcion || 'Sin descripción'}</p>
                            <div style="margin-top: 15px;">
                                <strong>Intervenciones (${intervenciones.length}):</strong>
                                ${intervenciones.map(i => `
                                    <div class="intervencion">
                                        <div class="intervencion-header">
                                            <span class="ia-badge">${i.ia_author.toUpperCase()}</span>
                                            <span class="score-badge">Score: ${i.confidence_score.toFixed(2)}</span>
                                        </div>
                                        <div style="font-size: 0.9em; opacity: 0.8;">${i.contenido.substring(0, 100)}...</div>
                                    </div>
                                `).join('')}
                            </div>
                        </div>
                    `;
                }).join('');
            } catch (e) {
                console.error('Error:', e);
            }
        }
        
        document.getElementById('debate-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const participantes = Array.from(document.querySelectorAll('.checkbox-group input:checked'))
                .map(cb => cb.value);
            
            const data = {
                tema: document.getElementById('tema').value,
                descripcion: document.getElementById('descripcion').value,
                participantes: participantes
            };
            
            try {
                const response = await fetch('/api/debates', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(data)
                });
                
                if (response.ok) {
                    const result = await response.json();
                    alert('✅ Debate creado: ' + result.debate.id);
                    document.getElementById('debate-form').reset();
                    loadDebates();
                } else {
                    alert('❌ Error al crear debate');
                }
            } catch (e) {
                alert('Error: ' + e.message);
            }
        });
        
        loadDebates();
    </script>
</body>
</html>
"""

SYNC_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Sincronización - CORAL v5.3</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: 'Segoe UI', system-ui, sans-serif; 
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #eee; min-height: 100vh;
        }
        .navbar { 
            background: rgba(102, 126, 234, 0.2); 
            padding: 15px 30px; 
        }
        .navbar h1 { display: inline; font-size: 1.5em; }
        .nav-links { float: right; margin-top: 5px; }
        .nav-links a { 
            color: #fff; text-decoration: none; margin-left: 20px; 
            padding: 8px 16px; border-radius: 6px;
        }
        .nav-links a:hover { background: rgba(102, 126, 234, 0.3); }
        .container { max-width: 1000px; margin: 0 auto; padding: 30px; }
        .section { 
            background: rgba(22, 33, 62, 0.6); 
            padding: 25px; border-radius: 12px; 
            margin-bottom: 20px;
        }
        .section h2 { 
            color: #667eea; margin-bottom: 20px; 
            border-bottom: 2px solid #667eea; padding-bottom: 10px;
        }
        .sync-card {
            background: rgba(102, 126, 234, 0.1);
            padding: 20px; border-radius: 10px;
            margin-bottom: 15px;
            display: flex; justify-content: space-between; align-items: center;
        }
        .sync-info h3 { color: #667eea; margin-bottom: 5px; }
        .sync-info p { opacity: 0.8; font-size: 0.9em; }
        .btn { 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white; border: none; padding: 12px 24px;
            border-radius: 8px; cursor: pointer; font-size: 1em;
        }
        .btn:hover { transform: scale(1.05); }
        .btn:disabled { opacity: 0.5; cursor: not-allowed; }
        .btn-success { background: linear-gradient(135deg, #10b981 0%, #059669 100%); }
        .btn-danger { background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%); }
        .status-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px; margin: 20px 0; }
        .status-card { 
            background: rgba(0,0,0,0.2); padding: 15px; border-radius: 8px;
            text-align: center;
        }
        .status-card .value { font-size: 2em; font-weight: bold; color: #667eea; }
        .status-card .label { font-size: 0.9em; opacity: 0.8; margin-top: 5px; }
        .log-entry {
            background: rgba(0,0,0,0.2); padding: 10px; border-radius: 6px;
            margin: 5px 0; font-family: monospace; font-size: 0.9em;
            display: flex; justify-content: space-between;
        }
        .log-success { border-left: 3px solid #10b981; }
        .log-error { border-left: 3px solid #ef4444; }
        .log-pending { border-left: 3px solid #f59e0b; }
        .progress-bar {
            width: 100%; height: 8px; background: rgba(0,0,0,0.3);
            border-radius: 4px; overflow: hidden; margin: 10px 0;
        }
        .progress-fill {
            height: 100%; background: linear-gradient(90deg, #667eea, #764ba2);
            transition: width 0.3s;
        }
    </style>
</head>
<body>
    <nav class="navbar">
        <h1>🧠 CORAL v5.3</h1>
        <div class="nav-links">
            <a href="/">Dashboard</a>
            <a href="/memory">Memoria</a>
            <a href="/debates">Debates</a>
            <a href="/sync">Sincronización</a>
        </div>
    </nav>
    
    <div class="container">
        <div class="section">
            <h2>📊 Estado de Sincronización</h2>
            <div class="status-grid">
                <div class="status-card">
                    <div class="value" id="local-count">-</div>
                    <div class="label">Entradas Locales</div>
                </div>
                <div class="status-card">
                    <div class="value" id="pending-count">-</div>
                    <div class="label">Pendientes Sync</div>
                </div>
                <div class="status-card">
                    <div class="value" id="last-sync-time">-</div>
                    <div class="label">Última Sync</div>
                </div>
            </div>
            <div class="progress-bar">
                <div class="progress-fill" id="sync-progress" style="width: 0%"></div>
            </div>
        </div>
        
        <div class="section">
            <h2>🔄 Acciones de Sincronización</h2>
            
            <div class="sync-card">
                <div class="sync-info">
                    <h3>☁️ Subir a Supabase (Cloud)</h3>
                    <p>Sincroniza entradas locales pendientes a la base de datos cloud</p>
                </div>
                <button class="btn btn-success" id="btn-to-cloud" onclick="syncToCloud()">
                    Sincronizar Ahora
                </button>
            </div>
            
            <div class="sync-card">
                <div class="sync-info">
                    <h3>📥 Descargar de Supabase</h3>
                    <p>Obtiene nuevas entradas desde la nube al almacenamiento local</p>
                </div>
                <button class="btn" id="btn-from-cloud" onclick="syncFromCloud()">
                    Descargar Ahora
                </button>
            </div>
            
            <div class="sync-card">
                <div class="sync-info">
                    <h3>🔄 Sincronización Bidireccional</h3>
                    <p>Sube locales y descarga de cloud en una sola operación</p>
                </div>
                <button class="btn btn-success" id="btn-both" onclick="syncBoth()">
                    Sync Completo
                </button>
            </div>
            
            <div class="sync-card">
                <div class="sync-info">
                    <h3>🗑️ Limpiar Locales</h3>
                    <p>Elimina todas las entradas locales (no afecta cloud)</p>
                </div>
                <button class="btn btn-danger" onclick="clearLocal()">
                    Limpiar Local
                </button>
            </div>
        </div>
        
        <div class="section">
            <h2>📜 Historial de Sincronización</h2>
            <div id="sync-log">
                <p style="text-align:center; opacity:0.7;">Cargando historial...</p>
            </div>
        </div>
    </div>
    
    <script>
        async function loadStatus() {
            try {
                const response = await fetch('/api/sync/status');
                const data = await response.json();
                
                document.getElementById('local-count').textContent = data.total_local || 0;
                document.getElementById('pending-count').textContent = data.pending_sync || 0;
                
                if (data.last_sync && data.last_sync.time) {
                    const date = new Date(data.last_sync.time);
                    document.getElementById('last-sync-time').textContent = 
                        date.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
                    
                    const total = data.total_local || 1;
                    const synced = total - (data.pending_sync || 0);
                    const percent = (synced / total) * 100;
                    document.getElementById('sync-progress').style.width = percent + '%';
                } else {
                    document.getElementById('last-sync-time').textContent = 'Nunca';
                }
            } catch (e) {
                console.error('Error:', e);
            }
        }
        
        async function syncToCloud() {
            if (!confirm('¿Subir entradas locales a Supabase?')) return;
            
            setLoading('btn-to-cloud', true);
            try {
                const response = await fetch('/api/sync', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({direction: 'to_cloud'})
                });
                const data = await response.json();
                
                const msg = data.to_cloud?.message || 'Completado';
                const status = data.to_cloud?.status || 'success';
                
                addLog(`Sync to cloud: ${msg}`, status);
                alert(status === 'success' ? '✅ ' + msg : '❌ ' + msg);
                loadStatus();
            } catch (e) {
                addLog('Error: ' + e.message, 'error');
                alert('Error: ' + e.message);
            }
            setLoading('btn-to-cloud', false);
        }
        
        async function syncFromCloud() {
            if (!confirm('¿Descargar datos de Supabase?')) return;
            
            setLoading('btn-from-cloud', true);
            try {
                const response = await fetch('/api/sync', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({direction: 'from_cloud'})
                });
                const data = await response.json();
                
                const msg = data.from_cloud?.message || 'Completado';
                const status = data.from_cloud?.status || 'success';
                
                addLog(`Sync from cloud: ${msg}`, status);
                alert(status === 'success' ? '✅ ' + msg : '❌ ' + msg);
                loadStatus();
            } catch (e) {
                addLog('Error: ' + e.message, 'error');
                alert('Error: ' + e.message);
            }
            setLoading('btn-from-cloud', false);
        }
        
        async function syncBoth() {
            if (!confirm('¿Realizar sincronización bidireccional completa?')) return;
            
            setLoading('btn-both', true);
            try {
                const response = await fetch('/api/sync', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({direction: 'both'})
                });
                const data = await response.json();
                
                const toMsg = data.to_cloud?.message || 'N/A';
                const fromMsg = data.from_cloud?.message || 'N/A';
                
                addLog(`Bidireccional - Subir: ${toMsg}`, data.to_cloud?.status);
                addLog(`Bidireccional - Bajar: ${fromMsg}`, data.from_cloud?.status);
                
                alert(`✅ Sync completado\nSubir: ${toMsg}\nBajar: ${fromMsg}`);
                loadStatus();
            } catch (e) {
                addLog('Error bidireccional: ' + e.message, 'error');
                alert('Error: ' + e.message);
            }
            setLoading('btn-both', false);
        }
        
        async function clearLocal() {
            if (!confirm('⚠️ ¿Eliminar TODAS las entradas locales?\n\nEsto no se puede deshacer.')) return;
            if (!confirm('¿Estás absolutamente seguro?')) return;
            
            // Simulado - implementar endpoint real si se necesita
            alert('Función no implementada en API. Usar clean_database.py manualmente.');
        }
        
        function setLoading(btnId, loading) {
            const btn = document.getElementById(btnId);
            btn.disabled = loading;
            btn.textContent = loading ? '⏳ Procesando...' : btn.textContent.replace('⏳ Procesando...', '');
        }
        
        function addLog(message, status) {
            const log = document.getElementById('sync-log');
            const time = new Date().toLocaleTimeString();
            const statusClass = status === 'success' ? 'log-success' : (status === 'error' ? 'log-error' : 'log-pending');
            
            const entry = document.createElement('div');
            entry.className = `log-entry ${statusClass}`;
            entry.innerHTML = `<span>${time} - ${message}</span><span>${status || 'pending'}</span>`;
            
            if (log.querySelector('p')) log.innerHTML = '';
            log.insertBefore(entry, log.firstChild);
        }
        
        loadStatus();
        setInterval(loadStatus, 30000);
    </script>
</body>
</html>
"""

# ==================== PUNTO DE ENTRADA ====================

def main():
    """Punto de entrada principal"""
    print("="*70)
    print("CORAL v5.3 - Aplicación Unificada")
    print("Memoria Local SQLite + Web API + Sincronización Cloud")
    print("="*70)
    
    # Inicializar memoria local
    memory = LocalMemoryManager()
    
    # Inicializar app web
    if not FLASK_AVAILABLE:
        print("[ERROR] Flask no está disponible")
        return
    
    app = CoralWebApp(memory)
    
    # Iniciar sincronización automática en background
    def auto_sync():
        while True:
            time.sleep(Config.SYNC_INTERVAL)
            print("[AUTO SYNC] Iniciando sincronización...")
            result = memory.sync_to_cloud()
            print(f"[AUTO SYNC] Resultado: {result.get('message', 'N/A')}")
    
    sync_thread = threading.Thread(target=auto_sync, daemon=True)
    sync_thread.start()
    
    print(f"\n[OK] Sistema listo")
    print(f"[WEB] Abre tu navegador en: http://localhost:{Config.API_PORT}")
    print(f"[WEB] Dashboard: http://localhost:{Config.API_PORT}/")
    print(f"[WEB] API Docs: http://localhost:{Config.API_PORT}/api/status")
    print(f"\n[CONFIG] Sincronización automática cada {Config.SYNC_INTERVAL//60} minutos")
    print("\nPresiona Ctrl+C para detener\n")
    
    # Iniciar servidor
    try:
        app.run()
    except KeyboardInterrupt:
        print("\n[OK] Servidor detenido")

# Variable app para Gunicorn (producción)
app = None

def create_app():
    """Factory para crear la aplicación (usado por Gunicorn)"""
    global app
    
    # Inicializar memoria
    memory = LocalMemoryManager()
    
    # Crear app web
    web_app = CoralWebApp(memory)
    
    # Iniciar sync en background
    def auto_sync():
        while True:
            time.sleep(Config.SYNC_INTERVAL)
            print("[AUTO SYNC] Iniciando sincronización...")
            result = memory.sync_to_cloud()
            print(f"[AUTO SYNC] Resultado: {result.get('message', 'N/A')}")
    
    sync_thread = threading.Thread(target=auto_sync, daemon=True)
    sync_thread.start()
    
    app = web_app.app
    return app

# Crear app para Gunicorn (con manejo de errores)
try:
    application = create_app()
    app = application
    print("[OK] App creada exitosamente para Gunicorn")
except Exception as e:
    print(f"[ERROR] Fallo al crear app: {e}")
    # Crear app mínima para que Gunicorn no falle
    from flask import Flask
    app = Flask(__name__)
    
    @app.route('/')
    def error_page():
        return f"<h1>Error al iniciar CORAL</h1><p>{e}</p><p>Verifica las variables de entorno</p>", 500
    
    @app.route('/api/status')
    def error_status():
        return {"status": "error", "message": str(e)}, 500

if __name__ == "__main__":
    # Configurar puerto desde variable de entorno (para Render)
    port = int(os.getenv('PORT', Config.API_PORT))
    Config.API_PORT = port
    
    print(f"\n[OK] Sistema listo")
    print(f"[WEB] Abre tu navegador en: http://localhost:{port}")
    print(f"[WEB] Dashboard: http://localhost:{port}/")
    print(f"[WEB] API Docs: http://localhost:{port}/api/status")
    print(f"\n[CONFIG] Sincronización automática cada {Config.SYNC_INTERVAL//60} minutos")
    print("\nPresiona Ctrl+C para detener\n")
    
    # Iniciar servidor
    try:
        app.run(host=Config.API_HOST, port=port, debug=False)
    except KeyboardInterrupt:
        print("\n[OK] Servidor detenido")
