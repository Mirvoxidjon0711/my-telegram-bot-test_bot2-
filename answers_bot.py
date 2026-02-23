import json
import time
import sqlite3
import logging
import pandas as pd
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# 1. SOZLAMALAR
TOKEN = "8566864498:AAFkTRfhiCyJha7HAIIfU6ne934JLGe9vq8"
ADMIN_ID = 1496011980  # <--- BU YERGA O'ZINGIZNING TELEGRAM ID'INGIZNI YOZING
user_states = {}

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# 2. BAZA BILAN ISHLASH
def init_db():
    conn = sqlite3.connect('quiz_results.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            full_name TEXT,
            username TEXT,
            score INTEGER,
            total INTEGER,
            duration INTEGER,
            date TEXT
        )
    ''')
    conn.commit()
    conn.close()

def save_result(user_id, full_name, username, score, total, duration):
    conn = sqlite3.connect('quiz_results.db')
    cursor = conn.cursor()
    date_now = datetime.now().strftime("%Y-%m-%d %H:%M")
    cursor.execute('''
        INSERT INTO results (user_id, full_name, username, score, total, duration, date)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, full_name, username, score, total, duration, date_now))
    conn.commit()
    conn.close()

# 3. SAVOLLARNI YUKLASH
def load_questions():
    try:
        with open('answers.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Fayl o'qishda xato: {e}")
        return []

# 4. BOT FUNKSIYALARI
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_states[user_id] = {'step': 'ASK_NAME'}
    await update.message.reply_text("Assalomu alaykum! Viktorinada qatnashish uchun ism va familiyangizni kiriting:")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = user_states.get(user_id)

    if state and state.get('step') == 'ASK_NAME':
        full_name = update.message.text
        questions = load_questions()
        
        if not questions:
            await update.message.reply_text("Xatolik: Savollar topilmadi! (answers.json faylini tekshiring)")
            return

        user_states[user_id] = {
            'step': 'QUIZ',
            'full_name': full_name,
            'index': 0,
            'score': 0,
            'start_time': time.time(),
            'questions': questions
        }
        await update.message.reply_text(f"Rahmat, {full_name}! Test boshlandi. Omad!")
        await send_question(update, context, user_id)

async def send_question(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    state = user_states.get(user_id)
    questions = state['questions']
    index = state['index']
    
    if index < len(questions):
        q = questions[index]
        # Xavfsizlik uchun variantlarni index bilan bog'laymiz
        keyboard = [[InlineKeyboardButton(opt, callback_data=str(i))] for i, opt in enumerate(q['variantlar'])]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        text = f"<b>{index + 1}-savol:</b>\n\n{q['savol']}"
        
        if update.message:
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="HTML")
        else:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode="HTML")
    else:
        # Test yakunlandi
        duration = round(time.time() - state['start_time'])
        score = state['score']
        full_name = state['full_name']
        total = len(questions)
        username = update.effective_user.username or "Noma'lum"
        
        save_result(user_id, full_name, username, score, total, duration)
        
        result_text = (
            f"<b>Test tugadi!</b> 🏁\n\n"
            f"👤 Ism: {full_name}\n"
            f"📊 Natija: {score}/{total}\n"
            f"⏱ Vaqt: {duration} soniya\n"
            f"✅ Natijangiz saqlandi!"
        )
        
        if update.callback_query:
            await update.callback_query.edit_message_text(result_text, parse_mode="HTML")
        else:
            await update.message.reply_text(result_text, parse_mode="HTML")
        
        del user_states[user_id]

async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    
    if user_id not in user_states or user_states[user_id].get('step') != 'QUIZ':
        await query.answer("Iltimos, testni qaytadan boshlang.")
        return

    state = user_states[user_id]
    current_q = state['questions'][state['index']]
    
    selected_index = int(query.data)
    selected_variant = current_q['variantlar'][selected_index]
    
    if selected_variant == current_q['javob']:
        state['score'] += 1
    
    state['index'] += 1
    await query.answer()
    await send_question(update, context, user_id)

# 5. ADMIN KOMANDASI (EXCEL EKSPORT)
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("Kechirasiz, siz admin emassiz! ❌")
        return

    conn = sqlite3.connect('quiz_results.db')
    df = pd.read_sql_query("SELECT * FROM results", conn)
    conn.close()

    if df.empty:
        await update.message.reply_text("Bazada hali natijalar yo'q.")
        return

    file_path = "quiz_natijalari.xlsx"
    df.to_excel(file_path, index=False)

    with open(file_path, 'rb') as file:
        await context.bot.send_document(
            chat_id=user_id, 
            document=file, 
            caption=f"📅 Holat: {datetime.now().strftime('%Y-%m-%d %H:%M')}\nJami qatnashchilar: {len(df)}"
        )

# 6. ASOSIY ISHGA TUSHIRISH
if __name__ == '__main__':
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(handle_answer))
    
    print("Bot ishga tushdi...")
    app.run_polling()