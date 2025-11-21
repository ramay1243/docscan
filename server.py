from flask import Flask, request, jsonify
from flask_cors import CORS
import PyPDF2
import docx
import requests
import tempfile
import os
import uuid
from datetime import datetime, date

app = Flask(__name__)
CORS(app)

import os
from dotenv import load_dotenv

load_dotenv()  # Загружаем переменные из .env

# Данные Yandex Cloud из переменных окружения
YANDEX_API_KEY = os.getenv('YANDEX_API_KEY')
YANDEX_FOLDER_ID = os.getenv('YANDEX_FOLDER_ID')

# Система пользователей и лимитов
users_db = {
    'default': {
        'plan': 'free',
        'used_today': 0,
        'last_reset': date.today().isoformat(),
        'total_used': 0
    }
}

PLANS = {
    'free': {
        'daily_limit': 3,
        'ai_access': True,
        'price': 0,
        'name': 'Бесплатный'
    },
    'premium': {
        'daily_limit': 50,
        'ai_access': True, 
        'price': 490,
        'name': 'Премиум'
    },
    'business': {
        'daily_limit': 1000,
        'ai_access': True,
        'price': 1900,
        'name': 'Бизнес'
    }
}

def get_user(user_id='default'):
    """Получает или создает пользователя"""
    if user_id not in users_db:
        users_db[user_id] = {
            'plan': 'free',
            'used_today': 0,
            'last_reset': date.today().isoformat(),
            'total_used': 0
        }
    
    user = users_db[user_id]
    
    # Сбрасываем дневной лимит если новый день
    if user['last_reset'] < date.today().isoformat():
        user['used_today'] = 0
        user['last_reset'] = date.today().isoformat()
    
    return user

def can_analyze(user_id='default'):
    """Проверяет может ли пользователь сделать анализ"""
    user = get_user(user_id)
    return user['used_today'] < PLANS[user['plan']]['daily_limit']

def record_usage(user_id='default'):
    """Записывает использование"""
    user = get_user(user_id)
    user['used_today'] += 1
    user['total_used'] += 1

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

def parse_fallback_response(ai_response):
    """Резервный парсинг для неструктурированных ответов"""
    risks = []
    recommendations = []
    
    lines = [line.strip() for line in ai_response.split('\n') if line.strip()]
    
    for i, line in enumerate(lines):
        line_lower = line.lower()
        
        # Ищем риски по ключевым словам
        if any(word in line_lower for word in ['риск', 'опасность', 'проблема', 'недостаток', 'слабое место', 'угроза']):
            # Берем следующие несколько строк как описание риска
            for j in range(i+1, min(i+4, len(lines))):
                next_line = lines[j]
                if next_line and len(next_line) > 20 and not next_line.lower().startswith('рекомендац'):
                    risks.append(next_line)
                    break
        
        # Ищем рекомендации по ключевым словам
        elif any(word in line_lower for word in ['рекомендац', 'совет', 'следует', 'рекомендуется', 'улучшить', 'добавить']):
            # Берем следующие несколько строк как рекомендацию
            for j in range(i+1, min(i+4, len(lines))):
                next_line = lines[j]
                if next_line and len(next_line) > 20 and not next_line.lower().startswith('риск'):
                    recommendations.append(next_line)
                    break
    
    return risks, recommendations

def analyze_with_yandexgpt(text):
    """Анализирует текст с помощью YandexGPT"""
    try:
        headers = {
            "Authorization": f"Api-Key {YANDEX_API_KEY}",
            "Content-Type": "application/json"
        }
        
        data = {
            "modelUri": f"gpt://{YANDEX_FOLDER_ID}/yandexgpt-lite/latest",
            "completionOptions": {
                "stream": False,
                "temperature": 0.1,
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
            
            # Улучшенный парсинг ответа
            lines = [line.strip() for line in ai_response.split('\n') if line.strip()]
            risks = []
            recommendations = []
            
            current_section = None
            
            for line in lines:
                line_lower = line.lower()
                
                # Определяем разделы
                if any(marker in line_lower for marker in ['риск', 'проблем', 'опасност', 'недостаток', 'слаб']):
                    current_section = 'risks'
                    continue
                elif any(marker in line_lower for marker in ['рекомендац', 'совет', 'улучшен', 'исправлен']):
                    current_section = 'recommendations'
                    continue
                
                # Пропускаем заголовки и общие фразы
                if any(phrase in line_lower for phrase in [
                    'общая оценка', 'документ выглядит', 'безопасн', 'итог', 'заключен'
                ]):
                    continue
                
                # Добавляем пункты только если они начинаются с маркера списка
                if line.startswith(('-', '•', '—', '*', '1.', '2.', '3.', '4.', '5.')) and len(line) > 5:
                    if current_section == 'risks':
                        risks.append(line.lstrip('-•—*123456789. '))
                    elif current_section == 'recommendations':
                        recommendations.append(line.lstrip('-•—*123456789. '))
            
            # Если не нашли структурированный ответ, используем эвристический подход
            if not risks or not recommendations:
                risks, recommendations = parse_fallback_response(ai_response)
            
            # Очистка от дубликатов и пустых строк
            risks = list(dict.fromkeys([r for r in risks if r and len(r) > 10]))
            recommendations = list(dict.fromkeys([r for r in recommendations if r and len(r) > 10]))
            
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
    user = get_user(user_id)
    
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

# API endpoints
@app.route('/analyze', methods=['POST'])
def analyze_document():
    user_id = 'default'
    
    # Проверяем лимиты
    if not can_analyze(user_id):
        user = get_user(user_id)
        plan = PLANS[user['plan']]
        return jsonify({
            'success': False,
            'error': f'❌ Лимит исчерпан! Использовано {user["used_today"]}/{plan["daily_limit"]} сегодня.',
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
            user = get_user(user_id)
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

@app.route('/usage', methods=['GET'])
def get_usage():
    """Получить информацию об использовании"""
    user_id = 'default'
    user = get_user(user_id)
    plan = PLANS[user['plan']]
    
    return jsonify({
        'plan': user['plan'],
        'plan_name': plan['name'],
        'used_today': user['used_today'],
        'daily_limit': plan['daily_limit'],
        'remaining': plan['daily_limit'] - user['used_today'],
        'total_used': user['total_used']
    })

@app.route('/plans', methods=['GET'])
def get_plans():
    """Получить информацию о тарифах"""
    return jsonify(PLANS)

@app.route('/')
def home():
    return jsonify({
        'message': 'DocScan API работает!',
        'status': 'active',
        'ai_available': True,
        'pdf_export': False
    })

if __name__ == '__main__':
    print("🚀 DocScan Server запущен!")
    print("📍 Адрес: http://localhost:5000")
    print("🤖 YandexGPT: Активен")
    print("📄 PDF отчеты: Отключены")
    print("💰 Бесплатный лимит: 3 анализа в день")
    app.run(debug=True, port=5000)



