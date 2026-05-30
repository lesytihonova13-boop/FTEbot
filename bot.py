import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton
import sqlite3
from datetime import datetime
import threading
import time
from flask import Flask
import os

BOT_TOKEN = "8679034549:AAGiDwFbLrUF-beBHKHGMqRyTDBuFZo9jcU"
ADMIN_CHAT_ID = 284970550

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

def init_db():
    conn = sqlite3.connect('data.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        chat_id INTEGER PRIMARY KEY,
        name TEXT,
        plan INTEGER DEFAULT 25,
        done INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS admins (
        chat_id INTEGER PRIMARY KEY)''')
    c.execute('INSERT OR IGNORE INTO admins (chat_id) VALUES (?)', (ADMIN_CHAT_ID,))
    conn.commit()
    conn.close()

def get_user(chat_id):
    conn = sqlite3.connect('data.db')
    c = conn.cursor()
    c.execute('SELECT name, plan, done FROM users WHERE chat_id=?', (chat_id,))
    r = c.fetchone()
    conn.close()
    if r:
        return {"name": r[0], "plan": r[1], "done": r[2]}
    return {"name": None, "plan": 25, "done": 0}

def save_user(chat_id, name, plan, done):
    conn = sqlite3.connect('data.db')
    c = conn.cursor()
    c.execute('INSERT OR REPLACE INTO users VALUES (?,?,?,?)', (chat_id, name, plan, done))
    conn.commit()
    conn.close()

def get_all_users():
    conn = sqlite3.connect('data.db')
    c = conn.cursor()
    c.execute('SELECT chat_id, name, plan, done FROM users WHERE plan>0')
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

def menu(chat_id):
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    if is_admin(chat_id):
        markup.add(KeyboardButton("📊 Рейтинг"), KeyboardButton("📋 Список"))
    else:
        markup.add(KeyboardButton("📊 Статус"), KeyboardButton("➕ Внести"))
        markup.add(KeyboardButton("🏆 Рейтинг"), KeyboardButton("✏️ План"))
        markup.add(KeyboardButton("🔄 Сброс"))
    return markup

@bot.message_handler(commands=['start'])
def start(m):
    chat_id = m.chat.id
    init_db()
    if is_admin(chat_id):
        bot.send_message(chat_id, "👋 Здравствуйте, Руководитель!", reply_markup=menu(chat_id))
        return
    user = get_user(chat_id)
    if user["name"] is None:
        msg = bot.send_message(chat_id, "Привет! Как тебя зовут?")
        bot.register_next_step_handler(msg, set_name)
    else:
        bot.send_message(chat_id, f"С возвращением, {user['name']}!", reply_markup=menu(chat_id))
        show_status(chat_id)

def set_name(m):
    chat_id = m.chat.id
    name = m.text.strip()
    save_user(chat_id, name, 25, 0)
    bot.send_message(chat_id, f"Приятно познакомиться, {name}! План: 25 юзеров в день.", reply_markup=menu(chat_id))
    show_status(chat_id)

def show_status(chat_id):
    u = get_user(chat_id)
    left = u['plan'] - u['done']
    percent = (u['done']/u['plan']*100) if u['plan'] else 0
    bar = "█" * int(percent/10) + "░" * (10 - int(percent/10))
    if u['done'] >= 25:
        motivation = "🏆 ОТЛИЧНО! Ты на высоте!"
    elif u['done'] >= 23:
        motivation = "✅ ХОРОШО! Почти у цели!"
    elif u['done'] >= 20:
        motivation = "👍 ТЫ СМОЖЕШЬ! Верю в тебя!"
    else:
        motivation = "⚠️ НУЖНО ДОЖАТЬ! Соберись!"
    bot.send_message(chat_id, f"{motivation}\n\n`{bar}` {percent:.1f}%\n✅ Сделано: {u['done']}\n⚠️ Осталось: {left}\n🎯 План: {u['plan']}", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "📊 Статус")
def cmd_status(m):
    show_status(m.chat.id)

@bot.message_handler(func=lambda m: m.text == "➕ Внести")
def ask_add(m):
    bot.send_message(m.chat.id, "Сколько юзеров сделали? Введите число:")
    bot.register_next_step_handler(m, add_user)

def add_user(m):
    chat_id = m.chat.id
    try:
        val = int(m.text.strip())
        if val <= 0:
            bot.send_message(chat_id, "❌ Введите положительное число")
            return
        u = get_user(chat_id)
        new_done = u['done'] + val
        save_user(chat_id, u['name'], u['plan'], new_done)
        bot.send_message(chat_id, f"✅ Добавлено {val} юзеров!")
        if new_done >= u['plan'] and u['done'] < u['plan']:
            bot.send_message(chat_id, f"🎉 ПОЗДРАВЛЯЮ! План выполнен!")
            try:
                bot.send_message(ADMIN_CHAT_ID, f"✅ {u['name']} выполнил план! {new_done}/{u['plan']}")
            except:
                pass
        show_status(chat_id)
    except:
        bot.send_message(chat_id, "❌ Ошибка. Введите число, например: 5")

@bot.message_handler(func=lambda m: m.text == "🏆 Рейтинг")
def cmd_rating(m):
    users = get_all_users()
    if not users:
        bot.send_message(m.chat.id, "Нет менеджеров")
        return
    data = []
    for u in users:
        percent = (u[3]/u[2]*100) if u[2] else 0
        data.append((u[1], percent, u[3], u[2]))
    data.sort(key=lambda x: x[1], reverse=True)
    text = "🏆 РЕЙТИНГ МЕНЕДЖЕРОВ 🏆\n\n"
    for i, (name, pct, done, plan) in enumerate(data[:10], 1):
        medal = "🥇" if i==1 else "🥈" if i==2 else "🥉" if i==3 else f"{i}."
        text += f"{medal} {name}: {pct:.1f}% ({done}/{plan})\n"
    bot.send_message(m.chat.id, text)

@bot.message_handler(func=lambda m: m.text == "✏️ План")
def ask_plan(m):
    bot.send_message(m.chat.id, "Введите новый план на день:")
    bot.register_next_step_handler(m, set_plan)

def set_plan(m):
    chat_id = m.chat.id
    try:
        p = int(m.text.strip())
        if p <= 0:
            bot.send_message(chat_id, "❌ Введите положительное число")
            return
        u = get_user(chat_id)
        save_user(chat_id, u['name'], p, u['done'])
        bot.send_message(chat_id, f"✅ План изменён на {p} юзеров в день")
        show_status(chat_id)
    except:
        bot.send_message(chat_id, "❌ Введите число, например: 25")

@bot.message_handler(func=lambda m: m.text == "🔄 Сброс")
def cmd_reset(m):
    chat_id = m.chat.id
    u = get_user(chat_id)
    save_user(chat_id, u['name'], u['plan'], 0)
    bot.send_message(chat_id, "🔄 Счётчик сброшен. Начинаете с нуля!")
    show_status(chat_id)

@bot.message_handler(func=lambda m: m.text == "📊 Рейтинг" and is_admin(m.chat.id))
def admin_rating(m):
    cmd_rating(m)

@bot.message_handler(func=lambda m: m.text == "📋 Список" and is_admin(m.chat.id))
def admin_list(m):
    users = get_all_users()
    if not users:
        bot.send_message(m.chat.id, "Нет менеджеров")
        return
    text = "📋 СПИСОК МЕНЕДЖЕРОВ\n\n"
    for u in users:
        percent = (u[3]/u[2]*100) if u[2] else 0
        status = "✅" if percent >= 100 else "⚠️"
        text += f"{status} {u[1]}: {percent:.1f}% ({u[3]}/{u[2]})\n"
    bot.send_message(m.chat.id, text)

@bot.message_handler(commands=['all_users'])
def cmd_all_users(m):
    if not is_admin(m.chat.id):
        return
    users = get_all_users()
    if not users:
        bot.send_message(m.chat.id, "Нет менеджеров в базе")
        return
    text = "📋 Менеджеры в базе:\n"
    for u in users:
        text += f"- {u[1]} (сделано: {u[3]}/{u[2]})\n"
    bot.send_message(m.chat.id, text)

def send_reports():
    while True:
        now = datetime.now()
        if now.hour in [12, 15, 18] and now.minute == 0:
            users = get_all_users()
            if users:
                report = "📊 ОТЧЁТ\n\n"
                for u in users:
                    percent = (u[3]/u[2]*100) if u[2] else 0
                    report += f"{u[1]}: {percent:.1f}% ({u[3]}/{u[2]})\n"
                try:
                    bot.send_message(ADMIN_CHAT_ID, report)
                except:
                    pass
        time.sleep(60)

@app.route('/')
def home():
    return "Бот работает!"

if __name__ == "__main__":
    init_db()
    threading.Thread(target=send_reports, daemon=True).start()
    threading.Thread(target=lambda: bot.infinity_polling(), daemon=True).start()
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)