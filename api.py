from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import json
import time
import sqlite3
from datetime import datetime
import os

app = Flask(__name__)
CORS(app)

# Production database path
db_path = os.path.join(os.getcwd(), 'botd.db')

def init_db():
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS users (api_key TEXT PRIMARY KEY, tier TEXT, requests INTEGER)")
    conn.commit()
    conn.close()

init_db()

@app.route('/')
def home():
    # Serve the dashboard as the main page
    return send_from_directory('.', 'dashboard.html')

@app.route('/api')
def api_info():
    return jsonify({"message": "BotD SaaS API is running", "status": "active"})

@app.route('/api/register', methods=['POST'])
def register():
    api_key = f"botd_{int(time.time())}"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO users (api_key, tier, requests) VALUES (?, ?, ?)", (api_key, 'free', 0))
    conn.commit()
    conn.close()
    return jsonify({'api_key': api_key})

@app.route('/api/detect', methods=['POST'])
def detect():
    api_key = request.headers.get('X-API-Key')
    if not api_key:
        return jsonify({'error': 'API key required'}), 401
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT requests FROM users WHERE api_key = ?", (api_key,))
    result = cursor.fetchone()
    conn.close()
    
    if not result or result[0] > 1000:
        return jsonify({'error': 'Limit exceeded'}), 429
    
    # Update usage
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET requests = requests + 1 WHERE api_key = ?", (api_key,))
    conn.commit()
    conn.close()
    
    # Bot detection
    user_agent = request.headers.get('User-Agent', '').lower()
    is_bot = any(word in user_agent for word in ['bot', 'crawler', 'spider', 'curl'])
    
    return jsonify({
        'is_bot': is_bot,
        'confidence': 0.8 if is_bot else 0.2,
        'timestamp': datetime.now().isoformat()
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
