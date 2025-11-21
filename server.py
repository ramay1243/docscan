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
import secrets

app = Flask(__name__)
# Секретный ключ для сессий - ОБЯЗАТЕЛЬНО поменяйте в продакшене!
app.secret_key = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')

# Исправляем CORS для работы на Render
CORS(app, resources={r"/*": {"origins": "*"}})

# Загружаем переменные окружения
from dotenv import load_dotenv
load_dotenv()

# Данные Yandex Cloud из переменных окружения
YANDEX_API_KEY = os.getenv('YANDEX_API_KEY')
YANDEX_FOLDER_ID = os.getenv('YANDEX_FOLDER_ID')

# Файл для хранения данных пользователей
USERS_FILE = 'users_data.json'
ADMIN_CREDENTIALS_FILE = 'admin_credentials.json'

# АДМИН ДАННЫЕ - ОБЯЗАТЕЛЬНО ПОМЕНЯЙТЕ В ПРОДАКШЕНЕ!
DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "admin123"  # СМЕНИТЕ ПАРОЛЬ!

def load_admin_credentials():
    """Загружает или создает админские учетные данные"""
    try:
        if os.path.exists(ADMIN_CREDENTIALS_FILE):
            with open(ADMIN_CREDENTIALS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"Ошибка загрузки админских данных: {e}")
    
    # Создаем дефолтные учетные данные
    admin_data = {
        'username': DEFAULT_ADMIN_USERNAME,
        'password_hash': hashlib.sha256(DEFAULT_ADMIN_PASSWORD.encode()).hexdigest(),
        'created_at': datetime.now().isoformat(),
        'is_default': True  # Флаг что это дефолтные учетки
    }
    
    try:
        with open(ADMIN_CREDENTIALS_FILE, 'w', encoding='utf-8') as f:
            json.dump(admin_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Ошибка сохранения админских данных: {e}")
    
    print("⚠️  СОЗДАНЫ ДЕФОЛТНЫЕ АДМИНСКИЕ УЧЕТКИ!")
    print(f"👤 Логин: {DEFAULT_ADMIN_USERNAME}")
    print(f"🔑 Пароль: {DEFAULT_ADMIN_PASSWORD}")
    print("🚨 СМЕНИТЕ ПАРОЛЬ НЕМЕДЛЕННО!")
    
    return admin_data

def is_admin_logged_in():
    """Проверяет, авторизован ли админ"""
    return session.get('admin_logged_in', False)

def require_admin_login(f):
    """Декоратор для защиты админских роутов"""
    def decorated_function(*args, **kwargs):
        if not is_admin_logged_in():
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

# Загружаем админские данные
admin_credentials = load_admin_credentials()

# ... (остальной код load_users, save_users, users_db, PLANS и т.д. остается без изменений)

# ОБНОВЛЕННАЯ АДМИН-ПАНЕЛЬ С АУТЕНТИФИКАЦИЕЙ
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    """Страница входа в админ-панель"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if (username == admin_credentials['username'] and 
            hashlib.sha256(password.encode()).hexdigest() == admin_credentials['password_hash']):
            
            session['admin_logged_in'] = True
            session['admin_username'] = username
            session['admin_login_time'] = datetime.now().isoformat()
            
            print(f"🔐 АДМИН ВОШЕЛ: {username} в {datetime.now()}")
            
            # Если используются дефолтные учетки, показываем предупреждение
            if admin_credentials.get('is_default'):
                return redirect(url_for('admin_security_warning'))
            
            return redirect(url_for('admin_panel'))
        else:
            return """
            <!DOCTYPE html>
            <html>
            <head>
                <title>Admin Login - Ошибка</title>
                <style>
                    body { font-family: Arial; margin: 40px; background: #f0f0f0; }
                    .login-box { background: white; padding: 30px; border-radius: 10px; max-width: 400px; margin: 100px auto; box-shadow: 0 0 10px rgba(0,0,0,0.1); }
                    .error { background: #ffe6e6; color: #d00; padding: 10px; border-radius: 5px; margin-bottom: 15px; }
                    input { width: 100%; padding: 10px; margin: 8px 0; border: 1px solid #ddd; border-radius: 5px; }
                    button { width: 100%; padding: 10px; background: #007cba; color: white; border: none; border-radius: 5px; cursor: pointer; }
                </style>
            </head>
            <body>
                <div class="login-box">
                    <h2>🔐 Вход в админ-панель</h2>
                    <div class="error">❌ Неверный логин или пароль</div>
                    <form method="POST">
                        <input type="text" name="username" placeholder="Логин" required>
                        <input type="password" name="password" placeholder="Пароль" required>
                        <button type="submit">Войти</button>
                    </form>
                </div>
            </body>
            </html>
            """
    
    # Показываем предупреждение если используются дефолтные учетки
    security_warning = ""
    if admin_credentials.get('is_default'):
        security_warning = """
        <div class="security-warning critical">
            🚨 ВНИМАНИЕ: Используются стандартные логин и пароль! 
            Немедленно смените их после входа!
        </div>
        """
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Admin Login - DocScan</title>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }}
            body {{ background: linear-gradient(135deg, #2c3e50 0%, #3498db 100%); min-height: 100vh; display: flex; justify-content: center; align-items: center; }}
            .login-box {{ background: white; padding: 40px; border-radius: 15px; box-shadow: 0 20px 40px rgba(0,0,0,0.1); max-width: 400px; width: 100%; }}
            h2 {{ color: #2c3e50; margin-bottom: 10px; text-align: center; }}
            .subtitle {{ color: #7f8c8d; text-align: center; margin-bottom: 30px; }}
            input {{ width: 100%; padding: 15px; margin: 10px 0; border: 1px solid #ddd; border-radius: 8px; font-size: 1em; }}
            button {{ width: 100%; padding: 15px; background: #3498db; color: white; border: none; border-radius: 8px; font-size: 1.1em; cursor: pointer; transition: background 0.3s; }}
            button:hover {{ background: #2980b9; }}
            .security-warning {{ background: #fff3cd; border: 1px solid #ffeaa7; color: #856404; padding: 10px; border-radius: 5px; margin-top: 15px; font-size: 0.9em; }}
            .security-warning.critical {{ background: #f8d7da; border: 1px solid #f5c6cb; color: #721c24; }}
        </style>
    </head>
    <body>
        <div class="login-box">
            <h2>🔐 Админ-панель</h2>
            <p class="subtitle">DocScan - Система управления</p>
            
            <form method="POST">
                <input type="text" name="username" placeholder="Логин" required value="{admin_credentials['username']}">
                <input type="password" name="password" placeholder="Пароль" required>
                <button type="submit">Войти</button>
            </form>
            
            {security_warning}
            
            <div class="security-warning">
                ⚠️ Доступ только для авторизованного персонала
            </div>
        </div>
    </body>
    </html>
    """

@app.route('/admin/security-warning')
@require_admin_login
def admin_security_warning():
    """Страница предупреждения о безопасности"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Security Warning - DocScan</title>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
            body { background: linear-gradient(135deg, #e74c3c 0%, #c0392b 100%); min-height: 100vh; display: flex; justify-content: center; align-items: center; padding: 20px; }
            .warning-box { background: white; padding: 40px; border-radius: 15px; box-shadow: 0 20px 40px rgba(0,0,0,0.2); max-width: 600px; width: 100%; text-align: center; }
            .warning-icon { font-size: 4em; margin-bottom: 20px; }
            h1 { color: #e74c3c; margin-bottom: 20px; }
            .warning-text { background: #f8d7da; color: #721c24; padding: 20px; border-radius: 10px; margin: 20px 0; border-left: 5px solid #e74c3c; }
            .btn { display: inline-block; background: #e74c3c; color: white; padding: 15px 30px; border-radius: 8px; text-decoration: none; margin: 10px; font-size: 1.1em; transition: background 0.3s; }
            .btn:hover { background: #c0392b; }
            .btn-secondary { background: #3498db; }
            .btn-secondary:hover { background: #2980b9; }
        </style>
    </head>
    <body>
        <div class="warning-box">
            <div class="warning-icon">🚨</div>
            <h1>КРИТИЧЕСКОЕ ПРЕДУПРЕЖДЕНИЕ БЕЗОПАСНОСТИ</h1>
            
            <div class="warning-text">
                <strong>Вы используете стандартные логин и пароль!</strong><br><br>
                Это представляет серьезную угрозу безопасности вашей системы.<br>
                Злоумышленники могут легко получить доступ к админ-панели.
            </div>
            
            <p>Немедленно смените логин и пароль для защиты системы.</p>
            
            <div style="margin-top: 30px;">
                <a href="/admin/change-credentials" class="btn">🔐 Сменить логин и пароль</a>
                <a href="/admin" class="btn btn-secondary">➡️ Перейти в админку</a>
            </div>
        </div>
    </body>
    </html>
    """

@app.route('/admin/change-credentials')
@require_admin_login
def admin_change_credentials_page():
    """Страница смены логина и пароля"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Change Credentials - DocScan</title>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
            body { background: linear-gradient(135deg, #2c3e50 0%, #3498db 100%); min-height: 100vh; padding: 20px; }
            .container { max-width: 500px; margin: 0 auto; }
            .header { background: white; padding: 30px; border-radius: 15px; margin-bottom: 20px; box-shadow: 0 10px 30px rgba(0,0,0,0.1); text-align: center; }
            .form-section { background: white; padding: 30px; border-radius: 15px; margin: 20px 0; box-shadow: 0 10px 30px rgba(0,0,0,0.1); }
            h1 { color: #2c3e50; margin-bottom: 10px; }
            input { width: 100%; padding: 15px; margin: 10px 0; border: 1px solid #ddd; border-radius: 8px; font-size: 1em; }
            button { width: 100%; padding: 15px; background: #27ae60; color: white; border: none; border-radius: 8px; font-size: 1.1em; cursor: pointer; transition: background 0.3s; margin: 10px 0; }
            button:hover { background: #219a52; }
            .btn-back { background: #3498db; }
            .btn-back:hover { background: #2980b9; }
            .message { padding: 10px; border-radius: 5px; margin: 10px 0; display: none; }
            .success { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
            .error { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
            .requirements { font-size: 0.9em; color: #7f8c8d; margin: 5px 0; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🔐 Смена учетных данных</h1>
                <p>Установите безопасные логин и пароль для админ-панели</p>
            </div>

            <div class="form-section">
                <div id="message" class="message"></div>
                
                <h3>📝 Новые учетные данные</h3>
                
                <input type="text" id="newUsername" placeholder="Новый логин" required>
                <div class="requirements">Логин должен быть не менее 3 символов</div>
                
                <input type="password" id="newPassword" placeholder="Новый пароль" required>
                <div class="requirements">Пароль должен быть не менее 6 символов</div>
                
                <input type="password" id="confirmPassword" placeholder="Подтвердите пароль" required>
                
                <button onclick="changeCredentials()">💾 Сохранить новые учетные данные</button>
                <button class="btn-back" onclick="window.location.href='/admin'">← Назад в админку</button>
            </div>
        </div>

        <script>
            function changeCredentials() {
                const newUsername = document.getElementById('newUsername').value;
                const newPassword = document.getElementById('newPassword').value;
                const confirmPassword = document.getElementById('confirmPassword').value;
                const message = document.getElementById('message');
                
                // Валидация
                if (newUsername.length < 3) {
                    showMessage('Логин должен быть не менее 3 символов', 'error');
                    return;
                }
                
                if (newPassword.length < 6) {
                    showMessage('Пароль должен быть не менее 6 символов', 'error');
                    return;
                }
                
                if (newPassword !== confirmPassword) {
                    showMessage('Пароли не совпадают', 'error');
                    return;
                }
                
                // Отправка на сервер
                fetch('/admin/change-credentials', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        new_username: newUsername,
                        new_password: newPassword
                    })
                })
                .then(r => r.json())
                .then(result => {
                    if (result.success) {
                        showMessage('✅ ' + result.message, 'success');
                        // Очищаем поля
                        document.getElementById('newUsername').value = '';
                        document.getElementById('newPassword').value = '';
                        document.getElementById('confirmPassword').value = '';
                        
                        // Предлагаем перелогиниться
                        setTimeout(() => {
                            if (confirm('Учетные данные изменены. Хотите войти заново?')) {
                                window.location.href = '/admin/logout';
                            }
                        }, 2000);
                    } else {
                        showMessage('❌ ' + result.error, 'error');
                    }
                })
                .catch(error => {
                    showMessage('❌ Ошибка сети: ' + error, 'error');
                });
            }
            
            function showMessage(text, type) {
                const message = document.getElementById('message');
                message.textContent = text;
                message.className = 'message ' + type;
                message.style.display = 'block';
                
                setTimeout(() => {
                    message.style.display = 'none';
                }, 5000);
            }
        </script>
    </body>
    </html>
    """

@app.route('/admin/change-credentials', methods=['POST'])
@require_admin_login
def admin_change_credentials():
    """API для смены логина и пароля"""
    try:
        data = request.json
        new_username = data.get('new_username')
        new_password = data.get('new_password')
        
        if not new_username or len(new_username) < 3:
            return jsonify({'success': False, 'error': 'Логин должен быть не менее 3 символов'})
        
        if not new_password or len(new_password) < 6:
            return jsonify({'success': False, 'error': 'Пароль должен быть не менее 6 символов'})
        
        # Обновляем учетные данные
        admin_credentials['username'] = new_username
        admin_credentials['password_hash'] = hashlib.sha256(new_password.encode()).hexdigest()
        admin_credentials['is_default'] = False  # Снимаем флаг дефолтных учеток
        admin_credentials['last_changed'] = datetime.now().isoformat()
        
        try:
            with open(ADMIN_CREDENTIALS_FILE, 'w', encoding='utf-8') as f:
                json.dump(admin_credentials, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Ошибка сохранения учетных данных: {e}")
        
        # Обновляем сессию
        session['admin_username'] = new_username
        
        print(f"🔐 УЧЕТНЫЕ ДАННЫЕ АДМИНА ИЗМЕНЕНЫ: {new_username} в {datetime.now()}")
        
        return jsonify({
            'success': True,
            'message': 'Логин и пароль успешно изменены!'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/admin/logout')
def admin_logout():
    """Выход из админ-панели"""
    session.clear()
    return redirect(url_for('admin_login'))

@app.route('/admin')
@require_admin_login
def admin_panel():
    """Главная админ-панель"""
    
    # Проверяем используются ли дефолтные учетки
    security_alert = ""
    if admin_credentials.get('is_default'):
        security_alert = """
        <div class="security-alert">
            🚨 <strong>ВНИМАНИЕ БЕЗОПАСНОСТИ!</strong> 
            Используются стандартные логин и пароль. 
            <a href="/admin/change-credentials" style="color: #e74c3c; text-decoration: underline;">Сменить немедленно!</a>
        </div>
        """
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Admin Panel - DocScan</title>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }}
            body {{ background: linear-gradient(135deg, #2c3e50 0%, #3498db 100%); min-height: 100vh; padding: 20px; }}
            .container {{ max-width: 1200px; margin: 0 auto; }}
            .header {{ background: white; padding: 30px; border-radius: 15px; margin-bottom: 20px; box-shadow: 0 10px 30px rgba(0,0,0,0.1); }}
            .admin-bar {{ background: #e74c3c; color: white; padding: 10px 20px; border-radius: 10px; margin-bottom: 15px; display: flex; justify-content: space-between; align-items: center; }}
            .admin-info {{ font-size: 0.9em; }}
            .logout-btn {{ background: #c0392b; color: white; border: none; padding: 5px 15px; border-radius: 5px; cursor: pointer; text-decoration: none; }}
            .security-alert {{ background: #f8d7da; color: #721c24; padding: 15px; border-radius: 10px; margin-bottom: 15px; border-left: 5px solid #e74c3c; }}
            h1 {{ color: #2c3e50; margin-bottom: 10px; }}
            .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin: 20px 0; }}
            .stat-card {{ background: white; padding: 20px; border-radius: 10px; text-align: center; box-shadow: 0 5px 15px rgba(0,0,0,0.1); }}
            .stat-number {{ font-size: 2em; font-weight: bold; color: #3498db; }}
            .new-user {{ background: #e8f5e8 !important; border-left: 4px solid #27ae60; }}
            .user-card {{ background: white; padding: 20px; border-radius: 10px; margin: 10px 0; box-shadow: 0 5px 15px rgba(0,0,0,0.1); }}
            .user-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }}
            .user-id {{ font-weight: bold; color: #2c3e50; font-size: 1.2em; }}
            .user-plan {{ background: #3498db; color: white; padding: 5px 10px; border-radius: 20px; font-size: 0.9em; }}
            .user-stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin: 10px 0; }}
            .stat-item {{ background: #f8f9fa; padding: 8px; border-radius: 5px; text-align: center; }}
            .controls {{ display: flex; gap: 10px; flex-wrap: wrap; margin-top: 10px; }}
            button {{ background: #3498db; color: white; border: none; padding: 8px 15px; border-radius: 5px; cursor: pointer; transition: background 0.3s; }}
            button:hover {{ background: #2980b9; }}
            .btn-premium {{ background: #e74c3c; }}
            .btn-premium:hover {{ background: #c0392b; }}
            .btn-unlimited {{ background: #9b59b6; }}
            .btn-unlimited:hover {{ background: #8e44ad; }}
            .btn-security {{ background: #27ae60; }}
            .btn-security:hover {{ background: #219a52; }}
            .form-section {{ background: white; padding: 25px; border-radius: 15px; margin: 20px 0; box-shadow: 0 10px 30px rgba(0,0,0,0.1); }}
            input, select {{ width: 100%; padding: 12px; margin: 8px 0; border: 1px solid #ddd; border-radius: 8px; font-size: 1em; }}
            .new-badge {{ background: #e74c3c; color: white; padding: 2px 8px; border-radius: 10px; font-size: 0.8em; margin-left: 10px; }}
            .last-active {{ font-size: 0.9em; color: #7f8c8d; margin-top: 5px; }}
            .user-info {{ font-size: 0.8em; color: #95a5a6; margin-top: 3px; }}
        </style>
    </head>
    <body>
        <div class="container">
            {security_alert}
            
            <div class="admin-bar">
                <div class="admin-info">
                    👤 Вы вошли как: <strong>{session.get('admin_username', 'admin')}</strong>
                    | 🕒 Вход: {session.get('admin_login_time', 'N/A')}
                </div>
                <div>
                    <a href="/admin/change-credentials" class="logout-btn" style="background: #27ae60; margin-right: 10px;">🔐 Сменить логин/пароль</a>
                    <a href="/admin/logout" class="logout-btn">🚪 Выйти</a>
                </div>
            </div>

            <div class="header">
                <h1>🔧 Админ-панель DocScan</h1>
                <p>Управление пользователями и тарифами в реальном времени</p>
                
                <div class="stats" id="statsContainer">
                    <!-- Статистика будет загружена через JavaScript -->
                </div>
            </div>

            <!-- ... остальная часть админ-панели без изменений ... -->
            
        </div>

        <script>
            // ... JavaScript код админ-панели без изменений ...
        </script>
    </body>
    </html>
    """

# ... остальной код без изменений ...

if __name__ == '__main__':
    print("🚀 DocScan Server запущен!")
    print("🤖 YandexGPT: Активен") 
    print("📄 PDF отчеты: Отключены")
    print("💰 Бесплатный лимит: 1 анализ в день")
    print("💎 Платные тарифы: 199₽, 399₽, 800₽")
    print("👥 Загружено пользователей:", len(users_db))
    print("🔐 Админ-панель защищена паролем")
    print("⚠️  Дефолтные учетные данные:")
    print(f"   👤 Логин: {DEFAULT_ADMIN_USERNAME}")
    print(f"   🔑 Пароль: {DEFAULT_ADMIN_PASSWORD}")
    print("   🚨 НЕМЕДЛЕННО СМЕНИТЕ ПАРОЛЬ В АДМИНКЕ!")
    
    # Для продакшена на Render
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
