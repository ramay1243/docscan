from flask import Flask, request, jsonify
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
            'first_visit': True
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

# ОБНОВЛЕННЫЕ ТАРИФЫ - 1 бесплатный, потом платные
PLANS = {
    'free': {
        'daily_limit': 1,  # БЫЛО 3, ТЕПЕРЬ 1
        'ai_access': True,
        'price': 0,
        'name': 'Бесплатный'
    },
    'basic': {
        'daily_limit': 10,  # 10 анализов в день
        'ai_access': True, 
        'price': 199,
        'name': 'Базовый'
    },
    'premium': {
        'daily_limit': 50,  # 50 анализов в день
        'ai_access': True,
        'price': 399,
        'name': 'Премиум'
    },
    'unlimited': {
        'daily_limit': 1000,  # Фактически безлимит
        'ai_access': True,
        'price': 800,
        'name': 'Безлимитный'
    }
}

def get_user(user_id='default'):
    """Получает или создает пользователя"""
    if user_id not in users_db:
        users_db[user_id] = {
            'plan': 'free',
            'used_today': 0,
            'last_reset': date.today().isoformat(),
            'total_used': 0,
            'created_at': datetime.now().isoformat(),
            'last_activity': datetime.now().isoformat(),
            'first_visit': True  # Флаг первого посещения
        }
        save_users()  # Сохраняем при создании нового пользователя
        print(f"🎉 НОВЫЙ ПОЛЬЗОВАТЕЛЬ: {user_id}")
    
    user = users_db[user_id]
    
    # Сбрасываем дневной лимит если новый день
    if user['last_reset'] < date.today().isoformat():
        user['used_today'] = 0
        user['last_reset'] = date.today().isoformat()
    
    # Обновляем время последней активности
    user['last_activity'] = datetime.now().isoformat()
    
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
    user['first_visit'] = False  # Уже не первый визит
    save_users()  # Сохраняем после изменения

# ... (остальные функции extract_text_from_pdf, analyze_with_yandexgpt и т.д. остаются без изменений)

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
                </div>
            </div>

            <div class="form-section">
                <h3>⚙️ Управление тарифами</h3>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
                    <div>
                        <h4>Выдать тариф пользователю:</h4>
                        <input type="text" id="userId" placeholder="ID пользователя" value="default">
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
                            
                            <div class="controls">
                                <button onclick="setUserPlanQuick('${userId}', 'free')">Бесплатный</button>
                                <button onclick="setUserPlanQuick('${userId}', 'basic')">Базовый</button>
                                <button class="btn-premium" onclick="setUserPlanQuick('${userId}', 'premium')">Премиум</button>
                                <button class="btn-unlimited" onclick="setUserPlanQuick('${userId}', 'unlimited')">Безлимит</button>
                                <button onclick="resetUserUsage('${userId}')" style="background: #e67e22;">Сбросить лимит</button>
                            </div>
                        </div>
                    `;
                }).join('');
            }

            function filterUsers() {
                const searchTerm = document.getElementById('searchUsers').value.toLowerCase();
                const filteredUsers = allUsers.filter(([userId, userData]) => 
                    userId.toLowerCase().includes(searchTerm) || 
                    userData.plan.toLowerCase().includes(searchTerm)
                );
                displayUsers(filteredUsers);
            }

            function updateStats(users) {
                const userArray = Object.values(users);
                const today = new Date().toDateString();
                
                const totalUsers = userArray.length;
                const newUsers = userArray.filter(user => 
                    new Date(user.created_at).toDateString() === today
                ).length;
                const activeUsers = userArray.filter(user => 
                    new Date(user.last_activity).toDateString() === today
                ).length;
                const totalAnalyses = userArray.reduce((sum, user) => sum + user.total_used, 0);
                
                document.getElementById('totalUsers').textContent = totalUsers;
                document.getElementById('newUsers').textContent = newUsers;
                document.getElementById('activeUsers').textContent = activeUsers;
                document.getElementById('totalAnalyses').textContent = totalAnalyses;
            }

            function isNewUser(userData) {
                const created = new Date(userData.created_at);
                const now = new Date();
                const diffTime = Math.abs(now - created);
                const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
                return diffDays <= 1; // Новый если создан в течение последних 24 часов
            }

            function isActiveToday(userData) {
                return new Date(userData.last_activity).toDateString() === new Date().toDateString();
            }

            function getPlanName(plan) {
                const names = {
                    free: 'Бесплатный', 
                    basic: 'Базовый', 
                    premium: 'Премиум', 
                    unlimited: 'Безлимитный'
                };
                return names[plan] || plan;
            }

            function getPlanLimit(plan) {
                const limits = {free: 1, basic: 10, premium: 50, unlimited: 1000};
                return limits[plan] || 0;
            }

            function setUserPlan() {
                const userId = document.getElementById('userId').value;
                const plan = document.getElementById('planSelect').value;
                
                if (!userId) {
                    alert('Введите ID пользователя');
                    return;
                }
                
                fetch('/admin/set-plan', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({user_id: userId, plan: plan})
                })
                .then(r => r.json())
                .then(result => {
                    alert(result.success ? '✅ ' + result.message : '❌ ' + result.error);
                    loadUsers();
                });
            }

            function setUserPlanQuick(userId, plan) {
                fetch('/admin/set-plan', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({user_id: userId, plan: plan})
                })
                .then(r => r.json())
                .then(result => {
                    alert(result.success ? '✅ ' + result.message : '❌ ' + result.error);
                    loadUsers();
                });
            }

            function createUser() {
                const userId = document.getElementById('newUserId').value;
                if (!userId) {
                    alert('Введите ID пользователя');
                    return;
                }
                
                fetch('/admin/create-user', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({user_id: userId})
                })
                .then(r => r.json())
                .then(result => {
                    alert(result.success ? '✅ ' + result.message : '❌ ' + result.error);
                    loadUsers();
                    document.getElementById('newUserId').value = '';
                });
            }

            function resetUserUsage(userId) {
                if (confirm(`Сбросить дневной лимит для пользователя ${userId}?`)) {
                    fetch('/admin/reset-usage', {
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

            function resetDailyLimits() {
                if (confirm('Сбросить дневные лимиты для ВСЕХ пользователей?')) {
                    fetch('/admin/reset-all-usage', {
                        method: 'POST'
                    })
                    .then(r => r.json())
                    .then(result => {
                        alert(result.success ? '✅ ' + result.message : '❌ ' + result.error);
                        loadUsers();
                    });
                }
            }

            function exportUsers() {
                fetch('/admin/export-users')
                    .then(r => r.json())
                    .then(data => {
                        const blob = new Blob([JSON.stringify(data, null, 2)], {type: 'application/json'});
                        const url = URL.createObjectURL(blob);
                        const a = document.createElement('a');
                        a.href = url;
                        a.download = `docscan_users_${new Date().toISOString().split('T')[0]}.json`;
                        a.click();
                        URL.revokeObjectURL(url);
                    });
            }

            // Автообновление каждые 30 секунд
            setInterval(loadUsers, 30000);
            
            // Загружаем пользователей при открытии
            loadUsers();
        </script>
    </body>
    </html>
    """

# Новые API endpoints для админ-панели
@app.route('/admin/users', methods=['GET'])
def get_all_users():
    """Получить всех пользователей"""
    return jsonify(users_db)

@app.route('/admin/set-plan', methods=['POST'])
def admin_set_plan():
    """Установить тариф пользователю"""
    try:
        data = request.json
        user_id = data.get('user_id', 'default')
        plan = data.get('plan')
        
        if user_id not in users_db:
            return jsonify({'success': False, 'error': 'Пользователь не найден'})
        
        if plan not in PLANS:
            return jsonify({'success': False, 'error': 'Неверный тариф'})
        
        # Обновляем тариф
        users_db[user_id]['plan'] = plan
        users_db[user_id]['used_today'] = 0  # Сбрасываем лимит при смене тарифа
        save_users()
        
        return jsonify({
            'success': True,
            'message': f'Пользователю {user_id} выдан тариф: {PLANS[plan]["name"]}'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/admin/create-user', methods=['POST'])
def admin_create_user():
    """Создать нового пользователя"""
    try:
        data = request.json
        user_id = data.get('user_id')
        
        if not user_id:
            return jsonify({'success': False, 'error': 'Укажите ID пользователя'})
        
        if user_id in users_db:
            return jsonify({'success': False, 'error': 'Пользователь уже существует'})
        
        # Создаем пользователя
        users_db[user_id] = {
            'plan': 'free',
            'used_today': 0,
            'last_reset': date.today().isoformat(),
            'total_used': 0,
            'created_at': datetime.now().isoformat(),
            'last_activity': datetime.now().isoformat(),
            'first_visit': True
        }
        save_users()
        
        return jsonify({
            'success': True,
            'message': f'Пользователь {user_id} создан с бесплатным тарифом'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/admin/reset-usage', methods=['POST'])
def admin_reset_usage():
    """Сбросить использование для пользователя"""
    try:
        data = request.json
        user_id = data.get('user_id')
        
        if user_id not in users_db:
            return jsonify({'success': False, 'error': 'Пользователь не найден'})
        
        users_db[user_id]['used_today'] = 0
        users_db[user_id]['last_reset'] = date.today().isoformat()
        save_users()
        
        return jsonify({
            'success': True,
            'message': f'Лимиты пользователя {user_id} сброшены'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/admin/reset-all-usage', methods=['POST'])
def admin_reset_all_usage():
    """Сбросить использование для всех пользователей"""
    try:
        for user_id in users_db:
            users_db[user_id]['used_today'] = 0
            users_db[user_id]['last_reset'] = date.today().isoformat()
        
        save_users()
        
        return jsonify({
            'success': True,
            'message': f'Дневные лимиты сброшены для {len(users_db)} пользователей'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/admin/export-users', methods=['GET'])
def admin_export_users():
    """Экспорт данных пользователей"""
    return jsonify(users_db)

# ... (остальной код main и endpoints остается без изменений)

if __name__ == '__main__':
    print("🚀 DocScan Server запущен!")
    print("🤖 YandexGPT: Активен") 
    print("📄 PDF отчеты: Отключены")
    print("💰 Бесплатный лимит: 1 анализ в день")
    print("💎 Платные тарифы: 199₽, 399₽, 800₽")
    print("👥 Загружено пользователей:", len(users_db))
    
    # Для продакшена на Render
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
