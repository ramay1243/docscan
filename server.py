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

# Дефолтные админские учетки
DEFAULT_ADMIN = {
    'username': 'admin',
    'password_hash': hashlib.sha256('admin123'.encode()).hexdigest(),
    'is_default': True
}

def load_users():
    try:
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except:
        pass
    return {
        'default': {
            'plan': 'free', 
            'used_today': 0, 
            'last_reset': date.today().isoformat(), 
            'total_used': 0,
            'created_at': datetime.now().isoformat(),
            'last_activity': datetime.now().isoformat()
        }
    }

def save_users():
    try:
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(users_db, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Ошибка сохранения пользователей: {e}")

def load_admin():
    try:
        if os.path.exists(ADMIN_FILE):
            with open(ADMIN_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except:
        pass
    
    # Создаем дефолтные учетки
    try:
        with open(ADMIN_FILE, 'w', encoding='utf-8') as f:
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
        with open(ADMIN_FILE, 'w', encoding='utf-8') as f:
            json.dump(admin_data, f, indent=2)
    except Exception as e:
        print(f"Ошибка сохранения админских данных: {e}")

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
def generate_user_id():
    return str(uuid.uuid4())

def get_or_create_user(request):
    user_id = request.cookies.get('user_id')
    
    if not user_id or user_id not in users_db:
        user_id = generate_user_id()
        users_db[user_id] = {
            'plan': 'free', 
            'used_today': 0, 
            'last_reset': date.today().isoformat(), 
            'total_used': 0,
            'created_at': datetime.now().isoformat(),
            'last_activity': datetime.now().isoformat(),
            'user_agent': request.headers.get('User-Agent', 'unknown')[:100],
            'ip_address': request.remote_addr
        }
        save_users()
        print(f"🎉 Новый пользователь: {user_id}")
    
    # Обновляем активность
    users_db[user_id]['last_activity'] = datetime.now().isoformat()
    
    return user_id

def can_analyze(user_id):
    user = users_db.get(user_id)
    if not user:
        return False
    
    # Сбрасываем дневной лимит если новый день
    if user['last_reset'] < date.today().isoformat():
        user['used_today'] = 0
        user['last_reset'] = date.today().isoformat()
        save_users()
    
    return user['used_today'] < PLANS[user['plan']]['daily_limit']

def record_usage(user_id):
    if user_id in users_db:
        users_db[user_id]['used_today'] += 1
        users_db[user_id]['total_used'] += 1
        save_users()

# Функции анализа документов
def extract_text_from_pdf(file_path):
    text = ""
    try:
        with open(file_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            for page in reader.pages:
                text += page.extract_text() + "\n"
    except Exception as e:
        return f"Ошибка чтения PDF: {str(e)}"
    return text

def extract_text_from_docx(file_path):
    text = ""
    try:
        doc = docx.Document(file_path)
        for paragraph in doc.paragraphs:
            text += paragraph.text + "\n"
    except Exception as e:
        return f"Ошибка чтения DOCX: {str(e)}"
    return text

def analyze_with_yandexgpt(text):
    """Анализирует текст с помощью YandexGPT"""
    if not YANDEX_API_KEY or not YANDEX_FOLDER_ID:
        return {
            'risks': ['❌ YandexGPT не настроен'],
            'warnings': [],
            'summary': 'AI анализ недоступен',
            'recommendations': ['🔧 Настройте Yandex Cloud API ключи'],
            'ai_used': False
        }
    
    try:
        headers = {
            "Authorization": f"Api-Key {YANDEX_API_KEY}",
            "Content-Type": "application/json"
        }
        
        data = {
            "modelUri": f"gpt://{YANDEX_FOLDER_ID}/yandexgpt-lite/latest",
            "completionOptions": {
                "stream": False,
                "temperature': 0.1,
                "maxTokens": 2000
            },
            "messages": [
                {
                    "role": "system", 
                    "text": """Ты опытный юрист-аналитик. Проанализируй документ и выдели ТОЛЬКО:
1. ПОТЕНЦИАЛЬНЫЕ РИСКИ (конкретные проблемы, что может привести к потерям)
2. КОНКРЕТНЫЕ РЕКОМЕНДАЦИИ по исправлению

Формат ответа:
РИСКИ:
- риск 1
- риск 2

РЕКОМЕНДАЦИИ:
- рекомендация 1
- рекомендация 2

Не добавляй общие оценки безопасности и другие комментарии."""
                },
                {
                    "role": "user",
                    "text": f"Проанализируй этот документ как юрист и выдели только риски и рекомендации:\n\n{text[:8000]}"
                }
            ]
        }
        
        response = requests.post(
            "https://llm.api.cloud.yandex.net/foundationModels/v1/completion",
            headers=headers,
            json=data,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            ai_response = result['result']['alternatives'][0]['message']['text']
            
            # Парсинг ответа
            risks = []
            recommendations = []
            current_section = None
            
            for line in ai_response.split('\n'):
                line = line.strip()
                if not line:
                    continue
                    
                line_lower = line.lower()
                if 'риск' in line_lower:
                    current_section = 'risks'
                    continue
                elif 'рекомендац' in line_lower:
                    current_section = 'recommendations'
                    continue
                
                if line.startswith(('-', '•', '—', '*')) and len(line) > 5:
                    if current_section == 'risks':
                        risks.append(line.lstrip('-•—* '))
                    elif current_section == 'recommendations':
                        recommendations.append(line.lstrip('-•—* '))
            
            return {
                'risks': risks if risks else ['✅ Критических рисков не обнаружено'],
                'warnings': [],
                'summary': f'🤖 YandexGPT: {len(text)} символов проанализировано',
                'recommendations': recommendations if recommendations else ['✅ Все рекомендации учтены в документе'],
                'ai_used': True
            }
        else:
            return {
                'risks': [f'❌ Ошибка YandexGPT: {response.status_code}'],
                'warnings': [],
                'summary': 'Ошибка доступа к AI',
                'recommendations': ['🔄 Используем локальный анализ...'],
                'ai_used': False
            }
            
    except Exception as e:
        return {
            'risks': [f'❌ Ошибка соединения: {str(e)}'],
            'warnings': [],
            'summary': 'Нет соединения с AI',
            'recommendations': ['🔄 Переключаемся на локальный анализ'],
            'ai_used': False
        }

def analyze_text(text, user_id='default'):
    """Основная функция анализа"""
    user = users_db.get(user_id, users_db['default'])
    
    # Проверяем доступ к AI по тарифу
    if PLANS[user['plan']]['ai_access']:
        result = analyze_with_yandexgpt(text)
        if result['ai_used']:
            return result
    
    # Если AI недоступен, используем локальный анализ
    return {
        'risks': ['✅ Базовый анализ завершен'],
        'warnings': [],
        'summary': f'📊 Локальный анализ: {len(text)} символов',
        'recommendations': ['💎 Перейдите на премиум для AI-анализа'],
        'ai_used': False
    }

# Аутентификация админа
def admin_required(f):
    def decorated(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect('/admin/login')
        return f(*args, **kwargs)
    decorated.__name__ = f.__name__
    return decorated

# ГЛАВНАЯ СТРАНИЦА
@app.route('/')
def home():
    user_id = get_or_create_user(request)
    
    html = """
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
                
                if (!file.name.match(/\\.(pdf|docx|txt)$/)) {
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

                    const response = await fetch('/analyze', {
                        method: 'POST',
                        body: formData
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
                        alert('❌ Бесплатный лимит исчерпан!\\\\n\\\\nСегодня вы использовали 1/1 бесплатный анализ.\\\\n\\\\n💎 Перейдите на платный тариф для продолжения.');
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
        </script>
    </body>
    </html>
    """
    
    response = make_response(html)
    response.set_cookie('user_id', user_id, max_age=365*24*60*60, httponly=True, secure=False)
    return response

# Анализ документа
@app.route('/analyze', methods=['POST'])
def analyze_document():
    user_id = get_or_create_user(request)
    
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
            session['login_time'] = datetime.now().isoformat()
            
            print(f"🔐 АДМИН ВОШЕЛ: {username}")
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
    
    security_warning = ""
    if admin_data.get('is_default'):
        security_warning = """
        <div style="background: #f8d7da; color: #721c24; padding: 15px; border-radius: 5px; margin: 20px 0; border-left: 4px solid #e74c3c;">
            🚨 ВНИМАНИЕ: Используются стандартные логин и пароль! Немедленно смените их после входа!
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
            body {{ font-family: Arial; margin: 40px; background: linear-gradient(135deg, #2c3e50 0%, #3498db 100%); min-height: 100vh; display: flex; justify-content: center; align-items: center; }}
            .login-box {{ background: white; padding: 40px; border-radius: 15px; box-shadow: 0 20px 40px rgba(0,0,0,0.1); max-width: 400px; width: 100%; }}
            h2 {{ color: #2c3e50; margin-bottom: 10px; text-align: center; }}
            .subtitle {{ color: #7f8c8d; text-align: center; margin-bottom: 30px; }}
            input {{ width: 100%; padding: 15px; margin: 10px 0; border: 1px solid #ddd; border-radius: 8px; font-size: 1em; }}
            button {{ width: 100%; padding: 15px; background: #3498db; color: white; border: none; border-radius: 8px; font-size: 1.1em; cursor: pointer; transition: background 0.3s; }}
            button:hover {{ background: #2980b9; }}
        </style>
    </head>
    <body>
        <div class="login-box">
            <h2>🔐 Админ-панель</h2>
            <p class="subtitle">DocScan - Система управления</p>
            
            {security_warning}
            
            <form method="POST">
                <input type="text" name="username" placeholder="Логин" value="{admin_data['username']}" required>
                <input type="password" name="password" placeholder="Пароль" required>
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
    active_today = sum(1 for user in users_db.values() 
                      if user.get('last_activity', '').startswith(date.today().isoformat()))
    new_today = sum(1 for user in users_db.values() 
                   if user.get('created_at', '').startswith(date.today().isoformat()))
    
    users_html = ""
    for user_id, user_data in users_db.items():
        is_new = user_data.get('created_at', '').startswith(date.today().isoformat())
        users_html += f"""
        <div style="background: white; padding: 15px; margin: 10px 0; border-radius: 10px; border-left: 4px solid {'#27ae60' if is_new else '#3498db'};">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <strong>{user_id}</strong>
                <span style="background: #3498db; color: white; padding: 3px 8px; border-radius: 10px; font-size: 0.8em;">
                    {user_data['plan']}
                </span>
            </div>
            <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px; margin: 10px 0;">
                <div style="text-align: center;">
                    <div>📊 Использовано</div>
                    <strong>{user_data['used_today']}/{PLANS[user_data['plan']]['daily_limit']}</strong>
                </div>
                <div style="text-align: center;">
                    <div>📈 Всего</div>
                    <strong>{user_data['total_used']}</strong>
                </div>
                <div style="text-align: center;">
                    <div>📅 Создан</div>
                    <strong>{user_data.get('created_at', 'N/A')[:10]}</strong>
                </div>
            </div>
            {f'<div style="color: #27ae60; font-size: 0.9em;">🆕 Новый пользователь</div>' if is_new else ''}
        </div>
        """
    
    security_alert = ""
    if admin_data.get('is_default'):
        security_alert = """
        <div style="background: #f8d7da; color: #721c24; padding: 15px; border-radius: 10px; margin-bottom: 20px; border-left: 5px solid #e74c3c;">
            🚨 <strong>ВНИМАНИЕ БЕЗОПАСНОСТИ!</strong> 
            Используются стандартные логин и пароль. 
            <a href="/admin/change-password" style="color: #e74c3c; text-decoration: underline; font-weight: bold;">Сменить немедленно!</a>
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
            body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }}
            .container {{ max-width: 1200px; margin: 0 auto; }}
            .header {{ background: white; padding: 30px; border-radius: 15px; margin-bottom: 20px; box-shadow: 0 5px 15px rgba(0,0,0,0.1); }}
            .admin-bar {{ background: #2c3e50; color: white; padding: 15px 20px; border-radius: 10px; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center; }}
            .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin: 20px 0; }}
            .stat-card {{ background: white; padding: 25px; border-radius: 10px; text-align: center; box-shadow: 0 5px 15px rgba(0,0,0,0.1); }}
            .stat-number {{ font-size: 2.5em; font-weight: bold; color: #3498db; margin: 10px 0; }}
            .users-section {{ background: white; padding: 25px; border-radius: 15px; margin: 20px 0; box-shadow: 0 5px 15px rgba(0,0,0,0.1); }}
            .btn {{ background: #3498db; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; text-decoration: none; display: inline-block; margin: 5px; }}
            .btn-danger {{ background: #e74c3c; }}
            .btn-success {{ background: #27ae60; }}
        </style>
    </head>
    <body>
        <div class="container">
            {security_alert}
            
            <div class="admin-bar">
                <div>
                    <strong>👤 Админ:</strong> {session.get('admin_user', 'admin')} 
                    | <strong>🕒 Вход:</strong> {session.get('login_time', 'N/A')[:16]}
                </div>
                <div>
                    <a href="/admin/change-password" class="btn btn-success">🔐 Сменить пароль</a>
                    <a href="/admin/logout" class="btn btn-danger">🚪 Выйти</a>
                </div>
            </div>

            <div class="header">
                <h1>🔧 Админ-панель DocScan</h1>
                <p>Управление пользователями и тарифами в реальном времени</p>
                
                <div class="stats">
                    <div class="stat-card">
                        <div>👥 Всего пользователей</div>
                        <div class="stat-number">{total_users}</div>
                    </div>
                    <div class="stat-card">
                        <div>🆕 Новых сегодня</div>
                        <div class="stat-number">{new_today}</div>
                    </div>
                    <div class="stat-card">
                        <div>📱 Активных сегодня</div>
                        <div class="stat-number">{active_today}</div>
                    </div>
                    <div class="stat-card">
                        <div>📊 Всего анализов</div>
                        <div class="stat-number">{total_analyses}</div>
                    </div>
                </div>
            </div>

            <div class="users-section">
                <h3>👥 Все пользователи ({total_users})</h3>
                <div style="margin-bottom: 20px;">
                    <input type="text" id="searchUsers" placeholder="🔍 Поиск пользователей..." 
                           style="width: 100%; padding: 12px; border: 1px solid #ddd; border-radius: 8px; font-size: 1em;">
                </div>
                <div id="usersList">
                    {users_html if users_html else "<p>Пользователей нет</p>"}
                </div>
            </div>

            <div class="users-section">
                <h3>⚙️ Управление тарифами</h3>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
                    <div>
                        <h4>Выдать тариф пользователю:</h4>
                        <input type="text" id="userId" placeholder="ID пользователя" style="width: 100%; padding: 10px; margin: 5px 0; border: 1px solid #ddd; border-radius: 5px;">
                        <select id="planSelect" style="width: 100%; padding: 10px; margin: 5px 0; border: 1px solid #ddd; border-radius: 5px;">
                            <option value="free">Бесплатный (1 анализ)</option>
                            <option value="basic">Базовый (10 анализов)</option>
                            <option value="premium">Премиум (50 анализов)</option>
                            <option value="unlimited">Безлимитный</option>
                        </select>
                        <button class="btn" onclick="setUserPlan()" style="width: 100%;">Выдать тариф</button>
                    </div>
                    <div>
                        <h4>Быстрые действия:</h4>
                        <button class="btn" onclick="loadUsers()">🔄 Обновить данные</button>
                        <button class="btn" onclick="resetAllLimits()">🔄 Сбросить все лимиты</button>
                        <button class="btn btn-success" onclick="createTestUser()">🧪 Создать тестового пользователя</button>
                    </div>
                </div>
            </div>
        </div>

        <script>
            function loadUsers() {{
                location.reload();
            }}

            function setUserPlan() {{
                const userId = document.getElementById('userId').value;
                const plan = document.getElementById('planSelect').value;
                
                if (!userId) {{
                    alert('Введите ID пользователя');
                    return;
                }}
                
                fetch('/admin/set-plan', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{user_id: userId, plan: plan}})
                }})
                .then(r => r.json())
                .then(result => {{
                    alert(result.success ? '✅ ' + result.message : '❌ ' + result.error);
                    if (result.success) loadUsers();
                }})
                .catch(error => {{
                    alert('Ошибка сети: ' + error);
                }});
            }}

            function resetAllLimits() {{
                if (confirm('Сбросить дневные лимиты для ВСЕХ пользователей?')) {{
                    fetch('/admin/reset-all-limits', {{method: 'POST'}})
                    .then(r => r.json())
                    .then(result => {{
                        alert(result.success ? '✅ ' + result.message : '❌ ' + result.error);
                        if (result.success) loadUsers();
                    }});
                }}
            }}

            function createTestUser() {{
                fetch('/admin/create-test-user', {{method: 'POST'}})
                .then(r => r.json())
                .then(result => {{
                    alert(result.success ? '✅ ' + result.message : '❌ ' + result.error);
                    if (result.success) loadUsers();
                }});
            }}

            // Поиск пользователей
            document.getElementById('searchUsers').addEventListener('input', function(e) {{
                const searchTerm = e.target.value.toLowerCase();
                const userCards = document.querySelectorAll('#usersList > div');
                
                userCards.forEach(card => {{
                    const userId = card.querySelector('strong').textContent.toLowerCase();
                    if (userId.includes(searchTerm)) {{
                        card.style.display = 'block';
                    }} else {{
                        card.style.display = 'none';
                    }}
                }});
            }});
        </script>
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
            <head>
                <style>
                    body { font-family: Arial; margin: 40px; background: #f5f5f5; display: flex; justify-content: center; align-items: center; height: 100vh; }
                    .message { background: white; padding: 40px; border-radius: 10px; text-align: center; box-shadow: 0 5px 15px rgba(0,0,0,0.1); }
                    .btn { background: #3498db; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; text-decoration: none; display: inline-block; margin: 10px; }
                </style>
            </head>
            <body>
                <div class="message">
                    <h2>✅ Пароль успешно изменен!</h2>
                    <p>Новые учетные данные сохранены.</p>
                    <a href="/admin" class="btn">В админку</a>
                    <a href="/admin/logout" class="btn" style="background: #e74c3c;">Выйти и войти заново</a>
                </div>
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
        <meta charset="UTF-8">
        <style>
            body { font-family: Arial; margin: 0; padding: 20px; background: #f5f5f5; display: flex; justify-content: center; align-items: center; min-height: 100vh; }
            .form-box { background: white; padding: 40px; border-radius: 15px; box-shadow: 0 10px 30px rgba(0,0,0,0.1); max-width: 400px; width: 100%; }
            input { width: 100%; padding: 15px; margin: 10px 0; border: 1px solid #ddd; border-radius: 8px; font-size: 1em; }
            button { width: 100%; padding: 15px; background: #27ae60; color: white; border: none; border-radius: 8px; font-size: 1.1em; cursor: pointer; margin: 10px 0; }
            .btn-back { background: #3498db; }
        </style>
    </head>
    <body>
        <div class="form-box">
            <h2>🔐 Смена пароля админа</h2>
            <form method="POST">
                <input type="password" name="new_password" placeholder="Новый пароль (мин. 6 символов)" required>
                <button type="submit">💾 Сохранить новый пароль</button>
            </form>
            <a href="/admin" class="btn-back" style="display: block; text-align: center; padding: 10px; background: #3498db; color: white; text-decoration: none; border-radius: 5px; margin-top: 10px;">← Назад в админку</a>
        </div>
    </body>
    </html>
    """

# Админские API
@app.route('/admin/users')
@admin_required
def get_users_api():
    return jsonify(users_db)

@app.route('/admin/set-plan', methods=['POST'])
@admin_required
def admin_set_plan():
    try:
        data = request.json
        user_id = data.get('user_id')
        plan = data.get('plan')
        
        if not user_id or user_id not in users_db:
            return jsonify({'success': False, 'error': 'Пользователь не найден'})
        
        if plan not in PLANS:
            return jsonify({'success': False, 'error': 'Неверный тариф'})
        
        users_db[user_id]['plan'] = plan
        users_db[user_id]['used_today'] = 0
        save_users()
        
        return jsonify({
            'success': True,
            'message': f'Пользователю {user_id} выдан тариф: {PLANS[plan]["name"]}'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/admin/reset-all-limits', methods=['POST'])
@admin_required
def reset_all_limits():
    try:
        for user_id in users_db:
            users_db[user_id]['used_today'] = 0
            users_db[user_id]['last_reset'] = date.today().isoformat()
        
        save_users()
        
        return jsonify({
            'success': True,
            'message': f'Лимиты сброшены для {len(users_db)} пользователей'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/admin/create-test-user', methods=['POST'])
@admin_required
def create_test_user():
    try:
        user_id = f"test_{uuid.uuid4().hex[:8]}"
        users_db[user_id] = {
            'plan': 'free',
            'used_today': 0,
            'last_reset': date.today().isoformat(),
            'total_used': 0,
            'created_at': datetime.now().isoformat(),
            'last_activity': datetime.now().isoformat(),
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

if __name__ == '__main__':
    print("🚀 DocScan Server запущен!")
    print("🤖 YandexGPT: Активен") 
    print("📄 Поддержка PDF/DOCX/TXT: Включена")
    print("💰 Бесплатный лимит: 1 анализ в день")
    print("💎 Платные тарифы: 199₽, 399₽, 800₽")
    print("👥 Загружено пользователей:", len(users_db))
    print("🔐 Админ-панель защищена паролем")
    print("⚠️  Временные учетные данные админа:")
    print("   👤 Логин: admin")
    print("   🔑 Пароль: admin123")
    print("   🚨 Смените пароль в админке!")
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
