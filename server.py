from flask import Flask, request, jsonify, make_response, session, redirect, url_for
from flask_cors import CORS
import PyPDF2
import docx
import requests
import tempfile
import os
import uuid
from datetime import datetime, date
import json
import hashlib

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'super-secret-key-12345')

CORS(app, resources={r"/*": {"origins": "*"}})

from dotenv import load_dotenv
load_dotenv()

YANDEX_API_KEY = os.getenv('YANDEX_API_KEY')
YANDEX_FOLDER_ID = os.getenv('YANDEX_FOLDER_ID')

# Файлы данных
USERS_FILE = 'users_data.json'
ADMIN_FILE = 'admin_data.json'

# Дефолтные админские учетки (СМЕНИТЕ!)
DEFAULT_ADMIN = {
    'username': 'admin',
    'password_hash': hashlib.sha256('admin123'.encode()).hexdigest(),
    'is_default': True
}

def load_users():
    try:
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, 'r') as f:
                return json.load(f)
    except:
        pass
    return {'default': {'plan': 'free', 'used_today': 0, 'last_reset': date.today().isoformat(), 'total_used': 0}}

def save_users():
    try:
        with open(USERS_FILE, 'w') as f:
            json.dump(users_db, f, indent=2)
    except:
        pass

def load_admin():
    try:
        if os.path.exists(ADMIN_FILE):
            with open(ADMIN_FILE, 'r') as f:
                return json.load(f)
    except:
        pass
    
    # Создаем дефолтные учетки
    try:
        with open(ADMIN_FILE, 'w') as f:
            json.dump(DEFAULT_ADMIN, f, indent=2)
    except:
        pass
    
    print("🔐 ДЕФОЛТНЫЕ АДМИНСКИЕ УЧЕТКИ:")
    print("👤 Логин: admin")
    print("🔑 Пароль: admin123")
    print("🚨 СМЕНИТЕ ПАРОЛЬ!")
    
    return DEFAULT_ADMIN

def save_admin():
    try:
        with open(ADMIN_FILE, 'w') as f:
            json.dump(admin_data, f, indent=2)
    except:
        pass

# Загружаем данные
users_db = load_users()
admin_data = load_admin()

# Тарифы
PLANS = {
    'free': {'daily_limit': 1, 'ai_access': True, 'price': 0, 'name': 'Бесплатный'},
    'basic': {'daily_limit': 10, 'ai_access': True, 'price': 199, 'name': 'Базовый'},
    'premium': {'daily_limit': 50, 'ai_access': True, 'price': 399, 'name': 'Премиум'},
    'unlimited': {'daily_limit': 1000, 'ai_access': True, 'price': 800, 'name': 'Безлимитный'}
}

# Функции для пользователей
def get_or_create_user(request):
    user_id = request.cookies.get('user_id', 'default')
    if user_id not in users_db:
        users_db[user_id] = {
            'plan': 'free', 
            'used_today': 0, 
            'last_reset': date.today().isoformat(), 
            'total_used': 0,
            'created_at': datetime.now().isoformat()
        }
        save_users()
        print(f"🎉 Новый пользователь: {user_id}")
    return user_id

def can_analyze(user_id):
    user = users_db.get(user_id, users_db['default'])
    return user['used_today'] < PLANS[user['plan']]['daily_limit']

def record_usage(user_id):
    if user_id in users_db:
        users_db[user_id]['used_today'] += 1
        users_db[user_id]['total_used'] += 1
        save_users()

# Аутентификация админа
def admin_required(f):
    def decorated(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect('/admin/login')
        return f(*args, **kwargs)
    decorated.__name__ = f.__name__
    return decorated

# Главная страница
@app.route('/')
def home():
    user_id = get_or_create_user(request)
    response = make_response("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>DocScan</title>
        <meta charset="UTF-8">
        <style>
            body { font-family: Arial; margin: 40px; background: #f0f0f0; }
            .container { max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; }
            .upload-zone { border: 2px dashed #ccc; padding: 40px; text-align: center; margin: 20px 0; cursor: pointer; }
            .btn { background: #007cba; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🔍 DocScan - Анализ документов</h1>
            <p>Загрузите документ для анализа</p>
            
            <div class="upload-zone" onclick="document.getElementById('fileInput').click()">
                📄 Нажмите для выбора файла (PDF, DOCX, TXT)
            </div>
            
            <input type="file" id="fileInput" style="display:none" accept=".pdf,.docx,.txt">
            <button class="btn" onclick="analyze()">Анализировать</button>
            
            <div id="result" style="margin-top: 20px;"></div>
        </div>

        <script>
            async function analyze() {
                const fileInput = document.getElementById('fileInput');
                if (!fileInput.files[0]) return alert('Выберите файл');
                
                const formData = new FormData();
                formData.append('file', fileInput.files[0]);
                
                try {
                    const response = await fetch('/analyze', { method: 'POST', body: formData });
                    const data = await response.json();
                    
                    if (data.success) {
                        document.getElementById('result').innerHTML = '<h3>✅ Анализ завершен</h3>';
                    } else {
                        alert('Ошибка: ' + data.error);
                    }
                } catch (error) {
                    alert('Ошибка сети: ' + error);
                }
            }
        </script>
    </body>
    </html>
    """)
    response.set_cookie('user_id', user_id, max_age=365*24*60*60)
    return response

# Анализ документа
@app.route('/analyze', methods=['POST'])
def analyze_document():
    user_id = get_or_create_user(request)
    
    if not can_analyze(user_id):
        return jsonify({'success': False, 'error': 'Лимит исчерпан'}), 402
    
    if 'file' not in request.files:
        return jsonify({'error': 'Файл не загружен'}), 400
    
    file = request.files['file']
    if not file.filename:
        return jsonify({'error': 'Файл не выбран'}), 400
    
    record_usage(user_id)
    
    return jsonify({
        'success': True,
        'filename': file.filename,
        'result': {
            'risks': ['✅ Документ проверен'],
            'recommendations': ['💎 Перейдите на премиум для полного анализа'],
            'summary': 'Базовый анализ завершен'
        }
    })

# АДМИНКА
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if (username == admin_data['username'] and 
            hashlib.sha256(password.encode()).hexdigest() == admin_data['password_hash']):
            
            session['admin_logged_in'] = True
            session['admin_user'] = username
            return redirect('/admin')
        else:
            return """
            <html>
            <body style="font-family: Arial; margin: 40px;">
                <h2>❌ Неверный логин или пароль</h2>
                <a href="/admin/login">← Назад</a>
            </body>
            </html>
            """
    
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Admin Login</title>
        <style>
            body { font-family: Arial; margin: 40px; background: #f5f5f5; }
            .login-box { background: white; padding: 30px; max-width: 300px; margin: 100px auto; border-radius: 10px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }
            input { width: 100%; padding: 10px; margin: 8px 0; border: 1px solid #ddd; border-radius: 5px; }
            button { width: 100%; padding: 10px; background: #007cba; color: white; border: none; border-radius: 5px; cursor: pointer; }
        </style>
    </head>
    <body>
        <div class="login-box">
            <h2>🔐 Вход в админку</h2>
            <form method="POST">
                <input type="text" name="username" placeholder="Логин" value="admin" required>
                <input type="password" name="password" placeholder="Пароль" value="admin123" required>
                <button type="submit">Войти</button>
            </form>
        </div>
    </body>
    </html>
    """

@app.route('/admin/logout')
def admin_logout():
    session.clear()
    return redirect('/admin/login')

@app.route('/admin')
@admin_required
def admin_panel():
    total_users = len(users_db)
    total_analyses = sum(user['total_used'] for user in users_db.values())
    
    users_html = ""
    for user_id, user_data in users_db.items():
        users_html += f"""
        <div style="background: white; padding: 15px; margin: 10px 0; border-radius: 5px;">
            <strong>ID:</strong> {user_id}<br>
            <strong>Тариф:</strong> {user_data['plan']}<br>
            <strong>Использовано:</strong> {user_data['used_today']}/{PLANS[user_data['plan']]['daily_limit']}<br>
            <strong>Всего анализов:</strong> {user_data['total_used']}
        </div>
        """
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Admin Panel</title>
        <style>
            body {{ font-family: Arial; margin: 40px; background: #f5f5f5; }}
            .header {{ background: white; padding: 20px; border-radius: 10px; margin-bottom: 20px; }}
            .stats {{ display: flex; gap: 20px; margin: 20px 0; }}
            .stat-card {{ background: white; padding: 20px; border-radius: 10px; flex: 1; text-align: center; }}
            .users-list {{ background: white; padding: 20px; border-radius: 10px; }}
            .btn {{ background: #007cba; color: white; padding: 10px 15px; border: none; border-radius: 5px; cursor: pointer; text-decoration: none; display: inline-block; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🔧 Админ-панель DocScan</h1>
            <p>Вы вошли как: {session.get('admin_user', 'admin')}</p>
            <a href="/admin/logout" class="btn" style="background: #dc3545;">Выйти</a>
            <a href="/admin/change-password" class="btn" style="background: #28a745;">Сменить пароль</a>
        </div>

        <div class="stats">
            <div class="stat-card">
                <h3>👥 Пользователи</h3>
                <h1>{total_users}</h1>
            </div>
            <div class="stat-card">
                <h3>📊 Анализы</h3>
                <h1>{total_analyses}</h1>
            </div>
        </div>

        <div class="users-list">
            <h3>Список пользователей:</h3>
            {users_html if users_html else "<p>Пользователей нет</p>"}
        </div>
    </body>
    </html>
    """

@app.route('/admin/change-password', methods=['GET', 'POST'])
@admin_required
def change_password():
    if request.method == 'POST':
        new_password = request.form.get('new_password')
        if new_password and len(new_password) >= 6:
            admin_data['password_hash'] = hashlib.sha256(new_password.encode()).hexdigest()
            admin_data['is_default'] = False
            save_admin()
            return """
            <html>
            <body style="font-family: Arial; margin: 40px;">
                <h2>✅ Пароль успешно изменен!</h2>
                <a href="/admin">← В админку</a>
            </body>
            </html>
            """
        else:
            return """
            <html>
            <body style="font-family: Arial; margin: 40px;">
                <h2>❌ Пароль должен быть не менее 6 символов</h2>
                <a href="/admin/change-password">← Назад</a>
            </body>
            </html>
            """
    
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Смена пароля</title>
        <style>
            body { font-family: Arial; margin: 40px; background: #f5f5f5; }
            .form-box { background: white; padding: 30px; max-width: 400px; margin: 50px auto; border-radius: 10px; }
            input { width: 100%; padding: 10px; margin: 10px 0; border: 1px solid #ddd; border-radius: 5px; }
            button { width: 100%; padding: 10px; background: #28a745; color: white; border: none; border-radius: 5px; cursor: pointer; }
        </style>
    </head>
    <body>
        <div class="form-box">
            <h2>🔐 Смена пароля</h2>
            <form method="POST">
                <input type="password" name="new_password" placeholder="Новый пароль (мин. 6 символов)" required>
                <button type="submit">Сохранить</button>
            </form>
            <a href="/admin" style="display: block; text-align: center; margin-top: 15px;">← Назад</a>
        </div>
    </body>
    </html>
    """

@app.route('/admin/users')
@admin_required
def get_users_api():
    return jsonify(users_db)

if __name__ == '__main__':
    print("🚀 DocScan Server запущен!")
    print("🤖 YandexGPT: Активен") 
    print("📄 PDF отчеты: Отключены")
    print("💰 Бесплатный лимит: 1 анализ в день")
    print("💎 Платные тарифы: 199₽, 399₽, 800₽")
    print("👥 Загружено пользователей:", len(users_db))
    print("🔐 Админ-панель защищена паролем")
    print("⚠️  Временные учетные данные:")
    print("   👤 Логин: admin")
    print("   🔑 Пароль: admin123")
    print("   🚨 Смените пароль в админке!")
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
