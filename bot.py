import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton
import sqlite3
from datetime import datetime
import threading
import time
from flask import Flask
import os
import requests

BOT_TOKEN = "8679034549:AAGiDwFbLrUF-beBHKHGMqRyTDBuFZo9jcU"
ADMIN_CHAT_ID = 284970550

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

TARGET_MINUTES = 210

def init_db():
    conn = sqlite3.connect('data.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        chat_id INTEGER PRIMARY KEY,
        name TEXT,
        plan_users INTEGER DEFAULT 25,
        done_users INTEGER DEFAULT 0,
        plan_minutes INTEGER DEFAULT 210,
        done_minutes INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS admins (
        chat_id INTEGER PRIMARY KEY)''')
    c.execute('INSERT OR IGNORE INTO admins (chat_id) VALUES (?)', (ADMIN_CHAT_ID,))
    
    c.execute('SELECT * FROM users WHERE chat_id = ?', (ADMIN_CHAT_ID,))
    if not c.fetchone():
        c.execute('INSERT INTO users (chat_id, name, plan_users, done_users, plan_minutes, done_minutes) VALUES (?, ?, 25, 0, 210, 0)', (ADMIN_CHAT_ID, "Руководитель"))
    
    conn.commit()
    conn.close()

def get_user(chat_id):
    conn = sqlite3.connect('data.db')
    c = conn.cursor()
    c.execute('SELECT name, plan_users, done_users, plan_minutes, done_minutes FROM users WHERE chat_id=?', (chat_id,))
    r = c.fetchone()
    conn.close()
    if r:
        return {
            "name": r[0],
            "plan_users": r[1],
            "done_users": r[2],
            "plan_minutes": r[3],
            "done_minutes": r[4]
        }
    return {"name": None, "plan_users": 25, "done_users": 0, "plan_minutes": TARGET_MINUTES, "done_minutes": 0}

def save_user(chat_id, name, plan_users, done_users, plan_minutes, done_minutes):
    conn = sqlite3.connect('data.db')
    c = conn.cursor()
    c.execute('INSERT OR REPLACE INTO users VALUES (?,?,?,?,?,?)', (chat_id, name, plan_users, done_users, plan_minutes, done_minutes))
    conn.commit()
    conn.close()

def get_all_users():
    conn = sqlite3.connect('data.db')
    c = conn.cursor()
    c.execute('SELECT chat_id, name, plan_users, done_users, plan_minutes, done_minutes FROM users WHERE plan_users>0 OR plan_minutes>0')
    r = c.fetchall()
    conn.close()
    return r

def is_admin(chat_id):
    conn = sqlite3.connect('data.db')
    c = conn.cursor()
    c.execute('SELECT 1 FROM admins WHERE chat_id=?', (chat_id,))
    r = c.fetchone()
    conn.close()
    return r is not None

def get_all_chats_for_report():
    conn = sqlite3.connect('data.db')
    c = conn.cursor()
    c.execute('SELECT chat_id FROM users')
    users = [row[0] for row in c.fetchall()]
    c.execute('SELECT chat_id FROM admins')
    admins = [row[0] for row in c.fetchall()]
    conn.close()
    return list(set(users + admins))

def get_motivation_users(done):
    if done >= 25:
        return "🏆 ОТЛИЧНО! Ты на высоте!"
    elif done >= 23:
        return "✅ ХОРОШО! Почти у цели!"
    elif done >= 20:
        return "👍 ТЫ СМОЖЕШЬ! Верю в тебя!"
    else:
        return "⚠️ НУЖНО ДОЖАТЬ! Соберись!"

def get_motivation_minutes(done):
    if done >= TARGET_MINUTES:
        return "🏆 ОТЛИЧНО! Время на линии отличное!"
    elif done >= TARGET_MINUTES * 0.9:
        return "✅ ХОРОШО! Почти у цели по времени!"
    elif done >= TARGET_MINUTES * 0.7:
        return "👍 ТЫ СМОЖЕШЬ! Поднажми!"
    else:
        return "⚠️ НУЖНО ДОЖАТЬ! Мало времени на линии!"

def menu(chat_id):
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    if is_admin(chat_id):
        markup.add(KeyboardButton("📊 Рейтинг"), KeyboardButton("📋 Список"))
        markup.add(KeyboardButton("📊 Мой статус"), KeyboardButton("➕ Внести юзеров"), KeyboardButton("⏱ Внести минуты"))
        markup.add(KeyboardButton("✏️ Мой план"), KeyboardButton("🔄 Мой сброс"))
    else:
        markup.add(KeyboardButton("📊 Статус"), KeyboardButton("➕ Внести юзеров"), KeyboardButton("⏱ Внести минуты"))
        markup.add(KeyboardButton("🏆 Рейтинг"), KeyboardButton("✏️ План"))
        markup.add(KeyboardButton("🔄 Сброс"))
    return markup

@bot.message_handler(commands=['start'])
def start(m):
    chat_id = m.chat.id
    init_db()
    user = get_user(chat_id)
    if user["name"] is None:
        msg = bot.send_message(chat_id, "Привет! Как тебя зовут?")
        bot.register_next_step_handler(msg, set_name)
    else:
        bot.send_message(chat_id, f"С возвращением, {user['name']}!", reply_markup=menu(chat_id))
        if not is_admin(chat_id):
            show_status(chat_id)

def set_name(m):
    chat_id = m.chat.id
    name = m.text.strip()
    save_user(chat_id, name, 25, 0, TARGET_MINUTES, 0)
    bot.send_message(chat_id, f"Приятно познакомиться, {name}!\n\n📊 План по юзерам: 25\n⏱ План по времени на линии: {TARGET_MINUTES} мин", reply_markup=menu(chat_id))
    if not is_admin(chat_id):
        show_status(chat_id)

def show_status(chat_id):
    u = get_user(chat_id)
    
    left_users = u['plan_users'] - u['done_users']
    percent_users = (u['done_users']/u['plan_users']*100) if u['plan_users'] else 0
    bar_users = "█" * int(percent_users/10) + "░" * (10 - int(percent_users/10))
    motivation_users = get_motivation_users(u['done_users'])
    
    left_minutes = u['plan_minutes'] - u['done_minutes']
    percent_minutes = (u['done_minutes']/u['plan_minutes']*100) if u['plan_minutes'] else 0
    bar_minutes = "█" * int(percent_minutes/10) + "░" * (10 - int(percent_minutes/10))
    motivation_minutes = get_motivation_minutes(u['done_minutes'])
    
    status = (
        f"📊 *ТВОЙ ПРОГРЕСС*\n\n"
        f"👥 *ЮЗЕРЫ*\n"
        f"{motivation_users}\n"
        f"`{bar_users}` {percent_users:.1f}%\n"
        f"✅ Сделано: {u['done_users']} / {u['plan_users']}\n"
        f"⚠️ Осталось: {left_users}\n\n"
        f"⏱ *ВРЕМЯ НА ЛИНИИ*\n"
        f"{motivation_minutes}\n"
        f"`{bar_minutes}` {percent_minutes:.1f}%\n"
        f"✅ Внесено: {u['done_minutes']} / {u['plan_minutes']} мин\n"
        f"⚠️ Осталось: {left_minutes} мин"
    )
    bot.send_message(chat_id, status, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "📊 Статус" or m.text == "📊 Мой статус")
def cmd_status(m):
    show_status(m.chat.id)

@bot.message_handler(func=lambda m: m.text == "➕ Внести юзеров")
def ask_add_users(m):
    bot.send_message(m.chat.id, "Сколько юзеров сделали? Введите число:")
    bot.register_next_step_handler(m, add_users)

def add_users(m):
    chat_id = m.chat.id
    try:
        val = int(m.text.strip())
        if val <= 0:
            bot.send_message(chat_id, "❌ Введите положительное число")
            return
        u = get_user(chat_id)
        new_done = u['done_users'] + val
        save_user(chat_id, u['name'], u['plan_users'], new_done, u['plan_minutes'], u['done_minutes'])
        bot.send_message(chat_id, f"✅ Добавлено {val} юзеров! Всего: {new_done}")
        show_status(chat_id)
    except:
        bot.send_message(chat_id, "❌ Ошибка. Введите число, например: 5")

@bot.message_handler(func=lambda m: m.text == "⏱ Внести минуты")
def ask_add_minutes(m):
    bot.send_message(m.chat.id, "Сколько минут вы были на линии? Введите число (обновит текущее значение):")
    bot.register_next_step_handler(m, add_minutes)

def add_minutes(m):
    chat_id = m.chat.id
    try:
        val = int(m.text.strip())
        if val < 0:
            bot.send_message(chat_id, "❌ Введите положительное число или 0")
            return
        u = get_user(chat_id)
        save_user(chat_id, u['name'], u['plan_users'], u['done_users'], u['plan_minutes'], val)
        bot.send_message(chat_id, f"✅ Время на линии обновлено: {val} / {u['plan_minutes']} мин")
        show_status(chat_id)
    except:
        bot.send_message(chat_id, "❌ Ошибка. Введите число, например: 60")

@bot.message_handler(func=lambda m: m.text in ["🏆 Рейтинг", "📊 Рейтинг"])
def cmd_rating(m):
    users = get_all_users()
    if not users:
        bot.send_message(m.chat.id, "Нет менеджеров")
        return
    
    data = []
    for u in users:
        name = u[1]
        plan_users = u[2]
        done_users = u[3]
        plan_minutes = u[4]
        done_minutes = u[5]
        
        percent_users = (done_users / plan_users * 100) if plan_users > 0 else 0
        percent_minutes = (done_minutes / plan_minutes * 100) if plan_minutes > 0 else 0
        avg_percent = (percent_users + percent_minutes) / 2
        
        data.append({
            "name": name,
            "percent_users": percent_users,
            "percent_minutes": percent_minutes,
            "done_users": done_users,
            "plan_users": plan_users,
            "done_minutes": done_minutes,
            "plan_minutes": plan_minutes,
            "avg_percent": avg_percent
        })
    
    data.sort(key=lambda x: x["avg_percent"], reverse=True)
    
    text = "🏆 *ОБЩИЙ РЕЙТИНГ* 🏆\n\n"
    
    for i, mng in enumerate(data[:10], 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        
        if mng["avg_percent"] >= 90:
            status_icon = "🏆"
        elif mng["avg_percent"] >= 70:
            status_icon = "✅"
        elif mng["avg_percent"] >= 50:
            status_icon = "⚠️"
        else:
            status_icon = "❌"
        
        text += f"{medal} {status_icon} *{mng['name']}*\n"
        text += f"   👥 {mng['done_users']}/{mng['plan_users']} ({mng['percent_users']:.0f}%)\n"
        text += f"   ⏱ {mng['done_minutes']}/{mng['plan_minutes']} мин ({mng['percent_minutes']:.0f}%)\n\n"
    
    text += "`---`\n"
    text += "👥 *Юзеры* | ⏱ *Время на линии*"
    
    bot.send_message(m.chat.id, text, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text in ["✏️ План", "✏️ Мой план"])
def ask_plan(m):
    bot.send_message(m.chat.id, "Что хотите изменить?\n\n1️⃣ План по юзерам\n2️⃣ План по времени на линии\n\nВведите 1 или 2:")
    bot.register_next_step_handler(m, choose_plan)

def choose_plan(m):
    chat_id = m.chat.id
    choice = m.text.strip()
    if choice == "1":
        msg = bot.send_message(chat_id, "Введите новый план по юзерам на день:")
        bot.register_next_step_handler(msg, set_plan_users)
    elif choice == "2":
        msg = bot.send_message(chat_id, f"Введите новый план по времени на линии (сейчас {TARGET_MINUTES} мин):")
        bot.register_next_step_handler(msg, set_plan_minutes)
    else:
        bot.send_message(chat_id, "❌ Введите 1 или 2")

def set_plan_users(m):
    chat_id = m.chat.id
    try:
        p = int(m.text.strip())
        if p <= 0:
            bot.send_message(chat_id, "❌ Введите положительное число")
            return
        u = get_user(chat_id)
        save_user(chat_id, u['name'], p, u['done_users'], u['plan_minutes'], u['done_minutes'])
        bot.send_message(chat_id, f"✅ План по юзерам изменён на {p}")
        show_status(chat_id)
    except:
        bot.send_message(chat_id, "❌ Введите число, например: 25")

def set_plan_minutes(m):
    chat_id = m.chat.id
    try:
        p = int(m.text.strip())
        if p <= 0:
            bot.send_message(chat_id, "❌ Введите положительное число")
            return
        u = get_user(chat_id)
        save_user(chat_id, u['name'], u['plan_users'], u['done_users'], p, u['done_minutes'])
        bot.send_message(chat_id, f"✅ План по времени на линии изменён на {p} мин")
        show_status(chat_id)
    except:
        bot.send_message(chat_id, "❌ Введите число, например: 210")

@bot.message_handler(func=lambda m: m.text in ["🔄 Сброс", "🔄 Мой сброс"])
def ask_reset(m):
    bot.send_message(m.chat.id, "Что сбросить?\n\n1️⃣ Сбросить юзеров\n2️⃣ Сбросить время на линии\n3️⃣ Сбросить всё\n\nВведите 1, 2 или 3:")
    bot.register_next_step_handler(m, choose_reset)

def choose_reset(m):
    chat_id = m.chat.id
    choice = m.text.strip()
    u = get_user(chat_id)
    if choice == "1":
        save_user(chat_id, u['name'], u['plan_users'], 0, u['plan_minutes'], u['done_minutes'])
        bot.send_message(chat_id, "🔄 Счётчик юзеров сброшен")
    elif choice == "2":
        save_user(chat_id, u['name'], u['plan_users'], u['done_users'], u['plan_minutes'], 0)
        bot.send_message(chat_id, "🔄 Счётчик времени на линии сброшен")
    elif choice == "3":
        save_user(chat_id, u['name'], u['plan_users'], 0, u['plan_minutes'], 0)
        bot.send_message(chat_id, "🔄 Все счётчики сброшены")
    else:
        bot.send_message(chat_id, "❌ Введите 1, 2 или 3")
        return
    show_status(chat_id)

@bot.message_handler(func=lambda m: m.text == "📋 Список" and is_admin(m.chat.id))
def admin_list(m):
    users = get_all_users()
    if not users:
        bot.send_message(m.chat.id, "Нет менеджеров")
        return
    text = "📋 СПИСОК МЕНЕДЖЕРОВ\n\n"
    for u in users:
        percent_users = (u[3]/u[2]*100) if u[2] else 0
        percent_minutes = (u[5]/u[4]*100) if u[4] else 0
        status = "✅" if percent_users >= 100 else "⚠️"
        text += f"{status} {u[1]}: 👥 {percent_users:.0f}% | ⏱ {percent_minutes:.0f}%\n"
    bot.send_message(m.chat.id, text)

def send_reports():
    my_url = "https://ftebot.onrender.com"
    while True:
        now = datetime.now()
        if now.hour in [12, 15, 18] and now.minute == 0:
            users = get_all_users()
            if users:
                report = "📊 *ОТЧЁТ* 📊\n\n"
                for u in users:
                    name = u[1]
                    plan_users = u[2]
                    done_users = u[3]
                    plan_minutes = u[4]
                    done_minutes = u[5]
                    
                    percent_users = (done_users / plan_users * 100) if plan_users > 0 else 0
                    percent_minutes = (done_minutes / plan_minutes * 100) if plan_minutes > 0 else 0
                    
                    if percent_users >= 100 and percent_minutes >= 100:
                        icon = "✅✅"
                    elif percent_users >= 100:
                        icon = "✅"
                    elif percent_minutes >= 100:
                        icon = "⏱✅"
                    else:
                        icon = "⚠️"
                    
                    report += f"{icon} *{name}*\n"
                    report += f"   👥 {done_users}/{plan_users} ({percent_users:.0f}%)\n"
                    report += f"   ⏱ {done_minutes}/{plan_minutes} мин ({percent_minutes:.0f}%)\n\n"
                
                report += "`---`\n"
                report += "✅✅ План выполнен | ✅ Юзеры | ⏱✅ Время | ⚠️ В работе"
                
                for chat_id in get_all_chats_for_report():
                    try:
                        bot.send_message(chat_id, report, parse_mode="Markdown")
                    except:
                        pass
        if now.minute % 10 == 0 and now.second < 30:
            try:
                requests.get(my_url, timeout=5)
            except:
                pass
        time.sleep(30)

def check_missed_report():
    now = datetime.now()
    if now.hour in [12, 15, 18] and now.minute > 0 and now.minute < 10:
        users = get_all_users()
        if users:
            report = "📊 *ОТЧЁТ (ПРОПУЩЕННЫЙ)* 📊\n\n"
            for u in users:
                name = u[1]
                plan_users = u[2]
                done_users = u[3]
                plan_minutes = u[4]
                done_minutes = u[5]
                
                percent_users = (done_users / plan_users * 100) if plan_users > 0 else 0
                percent_minutes = (done_minutes / plan_minutes * 100) if plan_minutes > 0 else 0
                
                if percent_users >= 100 and percent_minutes >= 100:
                    icon = "✅✅"
                elif percent_users >= 100:
                    icon = "✅"
                elif percent_minutes >= 100:
                    icon = "⏱✅"
                else:
                    icon = "⚠️"
                
                report += f"{icon} *{name}*\n"
                report += f"   👥 {done_users}/{plan_users} ({percent_users:.0f}%)\n"
                report += f"   ⏱ {done_minutes}/{plan_minutes} мин ({percent_minutes:.0f}%)\n\n"
            
            report += "`---`\n"
            report += "✅✅ План выполнен | ✅ Юзеры | ⏱✅ Время | ⚠️ В работе"
            
            for chat_id in get_all_chats_for_report():
                try:
                    bot.send_message(chat_id, report, parse_mode="Markdown")
                except:
                    pass

@app.route('/')
def home():
    return "Бот работает 24/7!"

if __name__ == "__main__":
    init_db()
    threading.Thread(target=send_reports, daemon=True).start()
    threading.Thread(target=bot.infinity_polling, daemon=True).start()
    check_missed_report()
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)