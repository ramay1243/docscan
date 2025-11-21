from flask import Flask, request, jsonify, make_response
from flask_cors import CORS
import PyPDF2
import docx
import requests
import tempfile
import os
import uuid
from datetime import datetime, date
import json

app = Flask(__name__)
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

# Система пользователей и лимитов
def load_users():
    """Загружает пользователей из файла"""
    try:
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"Ошибка загрузки пользователей: {e}")
    return {
        'default': {
            'plan': 'free',
            'used_today': 0,
            'last_reset': date.today().isoformat(),
            'total_used': 0,
            'created_at': datetime.now().isoformat(),
            'last_activity': datetime.now().isoformat(),
            'first_visit': True,
            'user_agent': 'default'
        }
    }

def save_users():
    """Сохраняет пользователей в файл"""
    try:
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(users_db, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Ошибка сохранения пользователей: {e}")

# Загружаем пользователей при старте
users_db = load_users()

def generate_user_id():
    """Генерирует уникальный ID пользователя"""
    return str(uuid.uuid4())

def get_or_create_user(request):
    """Получает или создает пользователя на основе куки или генерирует нового"""
    user_id = request.cookies.get('user_id')
    
    if not user_id or user_id not in users_db:
        # Создаем нового пользователя
        user_id = generate_user_id()
        users_db[user_id] = {
            'plan': 'free',
            'used_today': 0,
            'last_reset': date.today().isoformat(),
            'total_used': 0,
            'created_at': datetime.now().isoformat(),
            'last_activity': datetime.now().isoformat(),
            'first_visit': True,
            'user_agent': request.headers.get('User-Agent', 'unknown')[:100],
            'ip_address': request.remote_addr
        }
        save_users()
        print(f"🎉 НОВЫЙ ПОЛЬЗОВАТЕЛЬ: {user_id}")
        print(f"   User-Agent: {request.headers.get('User-Agent', 'unknown')[:50]}...")
        print(f"   IP: {request.remote_addr}")
    
    return user_id

def update_user_activity(user_id, request):
    """Обновляет активность пользователя"""
    if user_id in users_db:
        users_db[user_id]['last_activity'] = datetime.now().isoformat()
        users_db[user_id]['user_agent'] = request.headers.get('User-Agent', 'unknown')[:100]
        users_db[user_id]['ip_address'] = request.remote_addr
        users_db[user_id]['first_visit'] = False

# ... (остальной код PLANS, функций анализа документов и т.д. остается без изменений)

# ОБНОВЛЕННЫЕ ТАРИФЫ - 1 бесплатный, потом платные
PLANS = {
    'free': {
        'daily_limit': 1,
        'ai_access': True,
        'price': 0,
        'name': 'Бесплатный'
    },
    'basic': {
        'daily_limit': 10,
        'ai_access': True, 
        'price': 199,
        'name': 'Базовый'
    },
    'premium': {
        'daily_limit': 50,
        'ai_access': True,
        'price': 399,
        'name': 'Премиум'
    },
    'unlimited': {
        'daily_limit': 1000,
        'ai_access': True,
        'price': 800,
        'name': 'Безлимитный'
    }
}

def can_analyze(user_id):
    """Проверяет может ли пользователь сделать анализ"""
    if user_id not in users_db:
        return False
    user = users_db[user_id]
    return user['used_today'] < PLANS[user['plan']]['daily_limit']

def record_usage(user_id):
    """Записывает использование"""
    if user_id in users_db:
        users_db[user_id]['used_today'] += 1
        users_db[user_id]['total_used'] += 1
        save_users()

# ... (функции extract_text_from_pdf, analyze_with_yandexgpt и т.д. остаются без изменений)

# ОБНОВЛЕННЫЕ API ENDPOINTS
@app.route('/')
def home():
    """Главная страница с интерфейсом"""
    user_id = get_or_create_user(request)
    response = make_response("""
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>DocScan - Анализ документов за 60 секунд</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
            body { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; padding: 20px; display: flex; justify-content: center; align-items: center; }
            .container { background: white; border-radius: 20px; padding: 40px; box-shadow: 0 20px 40px rgba(0,0,0,0.1); max-width: 1000px; width: 100%; }
            .header { text-align: center; margin-bottom: 40px; }
            .logo { font-size: 3em; margin-bottom: 10px; }
            h1 { color: #2d3748; margin-bottom: 10px; font-size: 2.2em; }
            .subtitle { color: #718096; font-size: 1.2em; }
            .upload-zone { border: 3px dashed #cbd5e0; border-radius: 15px; padding: 60px 30px; text-align: center; margin: 30px 0; transition: all 0.3s ease; background: #f7fafc; cursor: pointer; }
            .upload-zone:hover { border-color: #667eea; background: #edf2f7; }
            .upload-icon { font-size: 4em; color: #667eea; margin-bottom: 20px; }
            .btn { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border: none; padding: 15px 40px; border-radius: 50px; font-size: 1.1em; cursor: pointer; transition: transform 0.2s ease; margin: 10px; }
            .btn:hover { transform: translateY(-2px); box-shadow: 0 10px 20px rgba(102,126,234,0.3); }
            .btn:disabled { background: #a0aec0; cursor: not-allowed; transform: none; box-shadow: none; }
            .file-info { background: #edf2f7; padding: 15px; border-radius: 10px; margin: 20px 0; }
            .loading { display: none; text-align: center; margin: 20px 0; }
            .spinner { border: 4px solid #f3f3f3; border-top: 4px solid #667eea; border-radius: 50%; width: 40px; height: 40px; animation: spin 1s linear infinite; margin: 0 auto 20px; }
            @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
            .result { background: #f8fafc; border-radius: 15px; padding: 30px; margin-top: 30px; display: none; }
            .risk-item { background: white; padding: 15px; margin: 10px 0; border-radius: 10px; border-left: 4px solid #e53e3e; }
            .success-item { background: white; padding: 15px; margin: 10px 0; border-radius: 10px; border-left: 4px solid #48bb78; }
            .summary { background: #e6fffa; padding: 20px; border-radius: 10px; margin: 20px 0; border-left: 4px solid #38a169; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <div class="logo">🔍</div>
                <h1>DocScan</h1>
                <p class="subtitle">Понять суть документа за 60 секунд</p>
            </div>

            <div class="upload-zone" id="dropZone" onclick="document.getElementById('fileInput').click()">
                <div class="upload-icon">📄</div>
                <p><strong>Нажмите чтобы выбрать документ</strong></p>
                <p style="color: #718096; margin-top: 15px;">PDF, DOCX, TXT (до 10MB)</p>
            </div>

            <input type="file" id="fileInput" style="display: none;" accept=".pdf,.docx,.txt" onchange="handleFileSelect(event)">
            
            <div class="file-info" id="fileInfo" style="display: none;">
                <strong>Выбран файл:</strong> <span id="fileName"></span>
            </div>

            <button class="btn" id="analyzeBtn" onclick="analyzeDocument()" disabled>Начать анализ</button>

            <div class="loading" id="loading">
                <div class="spinner"></div>
                <p>Анализируем документ...</p>
            </div>

            <div class="result" id="result">
                <h3>✅ Анализ завершен</h3>
                <div id="resultContent"></div>
            </div>

            <div class="plans" style="margin-top: 40px;">
                <div style="text-align: center; margin-bottom: 20px;">
                    <h3>💎 Выберите тариф</h3>
                </div>
                
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px;">
                    <div style="background: white; padding: 25px; border-radius: 15px; border: 2px solid #e53e3e; text-align: center;">
                        <div style="font-size: 1.3em; font-weight: bold; margin-bottom: 10px; color: #e53e3e;">Бесплатный</div>
                        <div style="font-size: 2em; font-weight: bold; color: #e53e3e; margin-bottom: 15px;">0₽</div>
                        <ul style="list-style: none; margin-bottom: 20px; text-align: left;">
                            <li style="padding: 5px 0;">✅ 1 анализ в день</li>
                            <li style="padding: 5px 0;">✅ AI-анализ YandexGPT</li>
                            <li style="padding: 5px 0;">✅ Все форматы файлов</li>
                        </ul>
                        <button class="btn" disabled style="background: #e53e3e;">Текущий тариф</button>
                    </div>
                    
                    <div style="background: #f0fff4; padding: 25px; border-radius: 15px; border: 2px solid #38a169; text-align: center;">
                        <div style="font-size: 1.3em; font-weight: bold; margin-bottom: 10px; color: #38a169;">Базовый</div>
                        <div style="font-size: 2em; font-weight: bold; color: #38a169; margin-bottom: 15px;">199₽/мес</div>
                        <ul style="list-style: none; margin-bottom: 20px; text-align: left;">
                            <li style="padding: 5px 0;">🚀 10 анализов в день</li>
                            <li style="padding: 5px 0;">🚀 Приоритетный AI-анализ</li>
                            <li style="padding: 5px 0;">🚀 Быстрая обработка</li>
                        </ul>
                        <button class="btn" onclick="alert('Тариф будет доступен после подключения платежей')" style="background: #38a169;">Выбрать</button>
                    </div>
                </div>
            </div>
        </div>

        <script>
            let selectedFile = null;

            function handleFileSelect(event) {
                const file = event.target.files[0];
                if (!file) return;
                
                if (!file.name.match(/\.(pdf|docx|txt)$/)) {
                    alert('Пожалуйста, выберите файл в формате PDF, DOCX или TXT');
                    return;
                }

                if (file.size > 10 * 1024 * 1024) {
                    alert('Файл слишком большой. Максимальный размер: 10MB');
                    return;
                }

                selectedFile = file;
                document.getElementById('fileName').textContent = file.name;
                document.getElementById('fileInfo').style.display = 'block';
                document.getElementById('analyzeBtn').disabled = false;
            }

            async function analyzeDocument() {
                if (!selectedFile) return;

                document.getElementById('loading').style.display = 'block';
                document.getElementById('analyzeBtn').disabled = true;

                try {
                    const formData = new FormData();
                    formData.append('file', selectedFile);

                    const response = await fetch(window.location.origin + '/analyze', {
                        method: 'POST',
                        body: formData,
                        credentials: 'include' // Важно для отправки куки
                    });

                    if (!response.ok) {
                        throw new Error(`HTTP error! status: ${response.status}`);
                    }

                    const data = await response.json();

                    document.getElementById('loading').style.display = 'none';

                    if (data.success) {
                        showResult(data);
                    } else {
                        alert('Ошибка: ' + data.error);
                        document.getElementById('analyzeBtn').disabled = false;
                    }

                } catch (error) {
                    document.getElementById('loading').style.display = 'none';
                    
                    if (error.message.includes('402')) {
                        alert('❌ Бесплатный лимит исчерпан!\\n\\nСегодня вы использовали 1/1 бесплатный анализ.\\n\\n💎 Перейдите на платный тариф для продолжения.');
                    } else {
                        alert('Ошибка соединения: ' + error.message);
                    }
                    
                    document.getElementById('analyzeBtn').disabled = false;
                }
            }

            function showResult(data) {
                const resultDiv = document.getElementById('result');
                const resultContent = document.getElementById('resultContent');
                
                let risksHTML = '';
                data.result.risks.forEach(risk => {
                    risksHTML += `<div class="risk-item">${risk}</div>`;
                });
                
                let recommendationsHTML = '';
                data.result.recommendations.forEach(rec => {
                    recommendationsHTML += `<div class="success-item">${rec}</div>`;
                });
                
                resultContent.innerHTML = `
                    <div style="margin-bottom: 20px;">
                        <strong>📄 Анализ документа:</strong> ${data.filename}
                    </div>
                    
                    <div class="summary">
                        ${data.result.summary}
                    </div>
                    
                    ${risksHTML ? `<h4 style="margin: 20px 0 10px 0; color: #e53e3e;">⚠️ Выявленные риски:</h4>${risksHTML}` : ''}
                    
                    ${recommendationsHTML ? `<h4 style="margin: 20px 0 10px 0; color: #48bb78;">✅ Рекомендации:</h4>${recommendationsHTML}` : ''}
                `;
                
                resultDiv.style.display = 'block';
                resultDiv.scrollIntoView({ behavior: 'smooth' });
            }

            // Показываем информацию о пользователе в консоли для отладки
            console.log('DocScan загружен. User ID сохранен в куках.');
        </script>
    </body>
    </html>
    """)
    
    # Устанавливаем куку на 1 год
    response.set_cookie('user_id', user_id, max_age=365*24*60*60, httponly=True, secure=False)
    update_user_activity(user_id, request)
    
    return response

@app.route('/analyze', methods=['POST'])
def analyze_document():
    user_id = get_or_create_user(request)
    update_user_activity(user_id, request)
    
    # Проверяем лимиты
    if not can_analyze(user_id):
        user = users_db[user_id]
        plan = PLANS[user['plan']]
        return jsonify({
            'success': False,
            'error': f'❌ Бесплатный лимит исчерпан! Сегодня использовано {user["used_today"]}/{plan["daily_limit"]} анализов.',
            'upgrade_required': True
        }), 402
    
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'Файл не загружен'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'Файл не выбран'}), 400
        
        # Сохраняем временный файл
        temp_path = os.path.join(tempfile.gettempdir(), f"{uuid.uuid4()}_{file.filename}")
        file.save(temp_path)
        
        try:
            # Извлекаем текст
            if file.filename.lower().endswith('.pdf'):
                text = extract_text_from_pdf(temp_path)
            elif file.filename.lower().endswith('.docx'):
                text = extract_text_from_docx(temp_path)
            elif file.filename.lower().endswith('.txt'):
                with open(temp_path, 'r', encoding='utf-8') as f:
                    text = f.read()
            else:
                return jsonify({'error': 'Неподдерживаемый формат файла'}), 400
            
            # Проверяем что текст извлекся
            if not text or len(text.strip()) < 10:
                return jsonify({'error': 'Не удалось извлечь текст из файла'}), 400
            
            # Анализируем текст
            analysis_result = analyze_text(text, user_id)
            
            # Записываем использование
            record_usage(user_id)
            
            # Добавляем информацию о лимитах в ответ
            user = users_db[user_id]
            plan = PLANS[user['plan']]
            analysis_result['usage_info'] = {
                'used_today': user['used_today'],
                'daily_limit': plan['daily_limit'],
                'plan_name': plan['name'],
                'remaining': plan['daily_limit'] - user['used_today']
            }
            
            return jsonify({
                'success': True,
                'filename': file.filename,
                'result': analysis_result
            })
            
        finally:
            # Удаляем временный файл
            try:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
            except:
                pass
            
    except Exception as e:
        return jsonify({'error': f'Ошибка обработки: {str(e)}'}), 500

# ОБНОВЛЕННАЯ АДМИН-ПАНЕЛЬ
@app.route('/admin')
def admin_panel():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Admin Panel - DocScan</title>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
            body { background: linear-gradient(135deg, #2c3e50 0%, #3498db 100%); min-height: 100vh; padding: 20px; }
            .container { max-width: 1200px; margin: 0 auto; }
            .header { background: white; padding: 30px; border-radius: 15px; margin-bottom: 20px; box-shadow: 0 10px 30px rgba(0,0,0,0.1); }
            h1 { color: #2c3e50; margin-bottom: 10px; }
            .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin: 20px 0; }
            .stat-card { background: white; padding: 20px; border-radius: 10px; text-align: center; box-shadow: 0 5px 15px rgba(0,0,0,0.1); }
            .stat-number { font-size: 2em; font-weight: bold; color: #3498db; }
            .new-user { background: #e8f5e8 !important; border-left: 4px solid #27ae60; }
            .user-card { background: white; padding: 20px; border-radius: 10px; margin: 10px 0; box-shadow: 0 5px 15px rgba(0,0,0,0.1); }
            .user-header { display: flex; justify-content: between; align-items: center; margin-bottom: 10px; }
            .user-id { font-weight: bold; color: #2c3e50; font-size: 1.2em; }
            .user-plan { background: #3498db; color: white; padding: 5px 10px; border-radius: 20px; font-size: 0.9em; }
            .user-stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin: 10px 0; }
            .stat-item { background: #f8f9fa; padding: 8px; border-radius: 5px; text-align: center; }
            .controls { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 10px; }
            button { background: #3498db; color: white; border: none; padding: 8px 15px; border-radius: 5px; cursor: pointer; transition: background 0.3s; }
            button:hover { background: #2980b9; }
            .btn-premium { background: #e74c3c; }
            .btn-premium:hover { background: #c0392b; }
            .btn-unlimited { background: #9b59b6; }
            .btn-unlimited:hover { background: #8e44ad; }
            .form-section { background: white; padding: 25px; border-radius: 15px; margin: 20px 0; box-shadow: 0 10px 30px rgba(0,0,0,0.1); }
            input, select { width: 100%; padding: 12px; margin: 8px 0; border: 1px solid #ddd; border-radius: 8px; font-size: 1em; }
            .new-badge { background: #e74c3c; color: white; padding: 2px 8px; border-radius: 10px; font-size: 0.8em; margin-left: 10px; }
            .last-active { font-size: 0.9em; color: #7f8c8d; margin-top: 5px; }
            .user-info { font-size: 0.8em; color: #95a5a6; margin-top: 3px; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🔧 Админ-панель DocScan</h1>
                <p>Управление пользователями и тарифами в реальном времени</p>
                
                <div class="stats" id="statsContainer">
                    <!-- Статистика будет загружена через JavaScript -->
                </div>
            </div>

            <div class="form-section">
                <h3>📊 Общая статистика</h3>
                <div class="stats">
                    <div class="stat-card">
                        <div class="stat-number" id="totalUsers">0</div>
                        <div>Всего пользователей</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number" id="newUsers">0</div>
                        <div>Новых сегодня</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number" id="activeUsers">0</div>
                        <div>Активных сегодня</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number" id="totalAnalyses">0</div>
                        <div>Всего анализов</div>
                    </div>
                </div>
            </div>

            <div class="form-section">
                <h3>👥 Все пользователи</h3>
                <div style="margin-bottom: 20px;">
                    <input type="text" id="searchUsers" placeholder="🔍 Поиск пользователей..." onkeyup="filterUsers()">
                </div>
                <div id="usersList">
                    <!-- Список пользователей будет загружен через JavaScript -->
                </div>
            </div>

            <div class="form-section">
                <h3>🎯 Быстрые действия</h3>
                <div class="controls">
                    <button onclick="loadUsers()">🔄 Обновить данные</button>
                    <button onclick="exportUsers()">📊 Экспорт данных</button>
                    <button onclick="resetDailyLimits()">🔄 Сбросить дневные лимиты</button>
                    <button onclick="createTestUser()">🧪 Создать тестового пользователя</button>
                </div>
            </div>

            <div class="form-section">
                <h3>⚙️ Управление тарифами</h3>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
                    <div>
                        <h4>Выдать тариф пользователю:</h4>
                        <input type="text" id="userId" placeholder="ID пользователя">
                        <select id="planSelect">
                            <option value="free">Бесплатный (1 анализ)</option>
                            <option value="basic">Базовый (10 анализов)</option>
                            <option value="premium">Премиум (50 анализов)</option>
                            <option value="unlimited">Безлимитный</option>
                        </select>
                        <button onclick="setUserPlan()" style="width: 100%;">Выдать тариф</button>
                    </div>
                    <div>
                        <h4>Создать нового пользователя:</h4>
                        <input type="text" id="newUserId" placeholder="Новый ID пользователя">
                        <button onclick="createUser()" style="width: 100%;">Создать пользователя</button>
                    </div>
                </div>
            </div>
        </div>

        <script>
            let allUsers = [];

            function loadUsers() {
                fetch('/admin/users')
                    .then(r => r.json())
                    .then(users => {
                        allUsers = Object.entries(users);
                        displayUsers(allUsers);
                        updateStats(users);
                    })
                    .catch(error => {
                        console.error('Ошибка загрузки:', error);
                        alert('Ошибка загрузки данных');
                    });
            }

            function displayUsers(users) {
                const usersList = document.getElementById('usersList');
                
                if (users.length === 0) {
                    usersList.innerHTML = '<div class="user-card">Пользователи не найдены</div>';
                    return;
                }

                usersList.innerHTML = users.map(([userId, userData]) => {
                    const isNew = isNewUser(userData);
                    const isTodayActive = isActiveToday(userData);
                    const createdDate = new Date(userData.created_at).toLocaleDateString('ru-RU');
                    const lastActive = new Date(userData.last_activity).toLocaleString('ru-RU');
                    const userAgent = userData.user_agent || 'Неизвестно';
                    const ipAddress = userData.ip_address || 'Неизвестно';
                    
                    return `
                        <div class="user-card ${isNew ? 'new-user' : ''}">
                            <div class="user-header">
                                <div>
                                    <span class="user-id">${userId}</span>
                                    ${isNew ? '<span class="new-badge">НОВЫЙ</span>' : ''}
                                </div>
                                <span class="user-plan">${getPlanName(userData.plan)}</span>
                            </div>
                            
                            <div class="user-stats">
                                <div class="stat-item">
                                    <div>📊 Использовано</div>
                                    <strong>${userData.used_today}/${getPlanLimit(userData.plan)}</strong>
                                </div>
                                <div class="stat-item">
                                    <div>📈 Всего</div>
                                    <strong>${userData.total_used}</strong>
                                </div>
                                <div class="stat-item">
                                    <div>📅 Создан</div>
                                    <strong>${createdDate}</strong>
                                </div>
                            </div>
                            
                            <div class="last-active">
                                📍 Последняя активность: ${lastActive}
                                ${isTodayActive ? ' <span style="color:#27ae60;">● Сегодня</span>' : ''}
                            </div>
                            
                            <div class="user-info">
                                🌐 User-Agent: ${userAgent.substring(0, 50)}...
                            </div>
                            <div class="user-info">
                                📍 IP: ${ipAddress}
                            </div>
                            
                            <div class="controls">
                                <button onclick="setUserPlanQuick('${userId}', 'free')">Бесплатный</button>
                                <button onclick="setUserPlanQuick('${userId}', 'basic')">Базовый</button>
                                <button class="btn-premium" onclick="setUserPlanQuick('${userId}', 'premium')">Премиум</button>
                                <button class="btn-unlimited" onclick="setUserPlanQuick('${userId}', 'unlimited')">Безлимит</button>
                                <button onclick="resetUserUsage('${userId}')" style="background: #e67e22;">Сбросить лимит</button>
                                <button onclick="deleteUser('${userId}')" style="background: #e74c3c;">Удалить</button>
                            </div>
                        </div>
                    `;
                }).join('');
            }

            function createTestUser() {
                fetch('/admin/create-test-user', {
                    method: 'POST'
                })
                .then(r => r.json())
                .then(result => {
                    alert(result.success ? '✅ ' + result.message : '❌ ' + result.error);
                    loadUsers();
                });
            }

            function deleteUser(userId) {
                if (confirm(`Удалить пользователя ${userId}?`)) {
                    fetch('/admin/delete-user', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({user_id: userId})
                    })
                    .then(r => r.json())
                    .then(result => {
                        alert(result.success ? '✅ ' + result.message : '❌ ' + result.error);
                        loadUsers();
                    });
                }
            }

            // ... остальные функции JavaScript остаются без изменений
        </script>
    </body>
    </html>
    """

# ДОБАВЛЕННЫЕ API ДЛЯ АДМИНКИ
@app.route('/admin/create-test-user', methods=['POST'])
def admin_create_test_user():
    """Создать тестового пользователя"""
    try:
        user_id = generate_user_id()
        users_db[user_id] = {
            'plan': 'free',
            'used_today': 0,
            'last_reset': date.today().isoformat(),
            'total_used': 0,
            'created_at': datetime.now().isoformat(),
            'last_activity': datetime.now().isoformat(),
            'first_visit': True,
            'user_agent': 'Test User',
            'ip_address': '127.0.0.1'
        }
        save_users()
        
        return jsonify({
            'success': True,
            'message': f'Тестовый пользователь {user_id} создан'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/admin/delete-user', methods=['POST'])
def admin_delete_user():
    """Удалить пользователя"""
    try:
        data = request.json
        user_id = data.get('user_id')
        
        if user_id not in users_db:
            return jsonify({'success': False, 'error': 'Пользователь не найден'})
        
        if user_id == 'default':
            return jsonify({'success': False, 'error': 'Нельзя удалить пользователя по умолчанию'})
        
        del users_db[user_id]
        save_users()
        
        return jsonify({
            'success': True,
            'message': f'Пользователь {user_id} удален'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ... остальные API endpoints остаются без изменений

if __name__ == '__main__':
    print("🚀 DocScan Server запущен!")
    print("🤖 YandexGPT: Активен") 
    print("📄 PDF отчеты: Отключены")
    print("💰 Бесплатный лимит: 1 анализ в день")
    print("💎 Платные тарифы: 199₽, 399₽, 800₽")
    print("👥 Загружено пользователей:", len(users_db))
    print("🎯 Каждое устройство теперь получает уникальный ID!")
    
    # Для продакшена на Render
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
