from fastapi import FastAPI, APIRouter, HTTPException, Request, Depends
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional
import uuid
from datetime import datetime, timedelta, timezone
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import asyncio
import httpx
import json

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Create the main app without a prefix
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Telegram Bot setup
bot_token = os.environ['TELEGRAM_TOKEN']
admin_username = os.environ['ADMIN_USERNAME']
bot = Bot(token=bot_token)

# Initialize Telegram Application
telegram_app = None

async def init_telegram_app():
    global telegram_app
    telegram_app = Application.builder().token(bot_token).build()
    
    # Add handlers
    telegram_app.add_handler(CommandHandler("start", start_command))
    telegram_app.add_handler(CommandHandler("admin", admin_command))
    telegram_app.add_handler(CallbackQueryHandler(handle_callback))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    return telegram_app

# Pydantic Models
class Booking(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    masks_count: int  # 1 or 2
    days_count: int   # 1, 2, or 3
    start_date: datetime
    end_date: datetime
    price: int
    delivery_address: str
    status: str = "pending"  # pending, confirmed, completed, cancelled
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class BookingCreate(BaseModel):
    user_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    masks_count: int
    days_count: int
    start_date: datetime
    delivery_address: str

# User session storage (in production, use Redis or similar)
user_sessions = {}

# Pricing configuration
PRICES = {
    1: {1: 70, 2: 130, 3: 180},    # 1 mask
    2: {1: 140, 2: 260, 3: 360}   # 2 masks
}

# Helper functions
async def get_available_dates(masks_needed: int, days_needed: int):
    """Get available dates for booking"""
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    available_dates = []
    
    # Check next 30 days
    for i in range(1, 31):
        check_date = today + timedelta(days=i)
        end_date = check_date + timedelta(days=days_needed)
        
        # Count existing bookings for this period
        existing_bookings = await db.bookings.count_documents({
            "status": {"$in": ["pending", "confirmed"]},
            "$or": [
                {"start_date": {"$lt": end_date, "$gte": check_date}},
                {"end_date": {"$gt": check_date, "$lte": end_date}},
                {"start_date": {"$lte": check_date}, "end_date": {"$gte": end_date}}
            ]
        })
        
        # Get total masks booked for this period
        pipeline = [
            {
                "$match": {
                    "status": {"$in": ["pending", "confirmed"]},
                    "$or": [
                        {"start_date": {"$lt": end_date, "$gte": check_date}},
                        {"end_date": {"$gt": check_date, "$lte": end_date}},
                        {"start_date": {"$lte": check_date}, "end_date": {"$gte": end_date}}
                    ]
                }
            },
            {
                "$group": {
                    "_id": None,
                    "total_masks": {"$sum": "$masks_count"}
                }
            }
        ]
        
        result = await db.bookings.aggregate(pipeline).to_list(1)
        booked_masks = result[0]["total_masks"] if result else 0
        
        # We have 2 masks total
        if booked_masks + masks_needed <= 2:
            available_dates.append(check_date)
        
        if len(available_dates) >= 7:  # Show only first 7 available dates
            break
    
    return available_dates

async def send_admin_notification(booking: Booking):
    """Send notification to admin about new booking"""
    try:
        message = f"""🆕 Новое бронирование Meta Quest 3!

👤 Клиент: {booking.first_name or 'Неизвестно'} (@{booking.username or 'нет username'})
🥽 Количество масок: {booking.masks_count}
📅 Период: {booking.start_date.strftime('%d.%m.%Y')} - {booking.end_date.strftime('%d.%m.%Y')} ({booking.days_count} дн.)
💰 Стоимость: {booking.price}₽
📍 Адрес доставки: {booking.delivery_address}
🆔 ID заказа: {booking.id}

Статус: ⏳ Ожидает подтверждения"""
        
        await bot.send_message(chat_id=admin_username, text=message)
    except Exception as e:
        logging.error(f"Failed to send admin notification: {e}")

# Telegram Bot Handlers
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user = update.effective_user
    
    welcome_message = f"""🎮 Добро пожаловать, {user.first_name}!

Я бот для аренды VR-масок Meta Quest 3.

У нас доступны:
🥽 2 маски Meta Quest 3

📋 Тарифы:
• 1 маска:
  - 1 день: 70₽
  - 2 дня: 130₽
  - 3 дня: 180₽

• 2 маски:
  - 1 день: 140₽
  - 2 дня: 260₽
  - 3 дня: 360₽

Нажмите кнопку ниже, чтобы начать бронирование! 👇"""

    keyboard = [
        [InlineKeyboardButton("🥽 Забронировать маски", callback_data="start_booking")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(welcome_message, reply_markup=reply_markup)

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /admin command"""
    user = update.effective_user
    
    if f"@{user.username}" != admin_username:
        await update.message.reply_text("❌ У вас нет доступа к админ-панели.")
        return
    
    # Get current bookings
    today = datetime.now(timezone.utc)
    active_bookings = await db.bookings.count_documents({
        "status": {"$in": ["pending", "confirmed"]},
        "end_date": {"$gte": today}
    })
    
    total_bookings = await db.bookings.count_documents({})
    
    keyboard = [
        [InlineKeyboardButton("📋 Все бронирования", callback_data="admin_all_bookings")],
        [InlineKeyboardButton("⏳ Активные бронирования", callback_data="admin_active_bookings")],
        [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message = f"""🔧 Админ-панель

📊 Общая статистика:
• Всего бронирований: {total_bookings}
• Активных бронирований: {active_bookings}

Выберите действие:"""
    
    await update.message.reply_text(message, reply_markup=reply_markup)

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle callback queries from inline keyboards"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    if data == "start_booking":
        # Step 1: Choose number of masks
        keyboard = [
            [InlineKeyboardButton("1️⃣ Одна маска", callback_data="masks_1")],
            [InlineKeyboardButton("2️⃣ Две маски", callback_data="masks_2")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "🥽 Сколько масок хотите взять в аренду?",
            reply_markup=reply_markup
        )
    
    elif data.startswith("masks_"):
        masks_count = int(data.split("_")[1])
        user_sessions[user_id] = {"masks_count": masks_count}
        
        # Step 2: Choose rental duration
        keyboard = [
            [InlineKeyboardButton(f"1️⃣ день - {PRICES[masks_count][1]}₽", callback_data="days_1")],
            [InlineKeyboardButton(f"2️⃣ дня - {PRICES[masks_count][2]}₽", callback_data="days_2")],
            [InlineKeyboardButton(f"3️⃣ дня - {PRICES[masks_count][3]}₽", callback_data="days_3")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        mask_word = "маску" if masks_count == 1 else "маски"
        await query.edit_message_text(
            f"📅 На сколько дней берете {mask_word}?",
            reply_markup=reply_markup
        )
    
    elif data.startswith("days_"):
        days_count = int(data.split("_")[1])
        if user_id not in user_sessions:
            await query.edit_message_text("❌ Сессия истекла. Начните заново с /start")
            return
            
        user_sessions[user_id]["days_count"] = days_count
        masks_count = user_sessions[user_id]["masks_count"]
        
        # Get available dates
        available_dates = await get_available_dates(masks_count, days_count)
        
        if not available_dates:
            await query.edit_message_text(
                "😔 К сожалению, на ближайшие 30 дней нет свободных дат для выбранного периода.\n\nПопробуйте изменить количество дней или масок.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Начать заново", callback_data="start_booking")]])
            )
            return
        
        # Step 3: Choose date
        keyboard = []
        for date in available_dates:
            date_str = date.strftime("%d.%m.%Y")
            callback_data = f"date_{date.strftime('%Y-%m-%d')}"
            keyboard.append([InlineKeyboardButton(date_str, callback_data=callback_data)])
        
        keyboard.append([InlineKeyboardButton("🔄 Начать заново", callback_data="start_booking")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        price = PRICES[masks_count][days_count]
        await query.edit_message_text(
            f"📅 Выберите дату начала аренды:\n\n💰 Стоимость: {price}₽",
            reply_markup=reply_markup
        )
    
    elif data.startswith("date_"):
        date_str = data.split("_")[1]
        start_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        
        if user_id not in user_sessions:
            await query.edit_message_text("❌ Сессия истекла. Начните заново с /start")
            return
        
        user_sessions[user_id]["start_date"] = start_date
        
        # Step 4: Ask for delivery address
        days_count = user_sessions[user_id]["days_count"]
        end_date = start_date + timedelta(days=days_count)
        
        await query.edit_message_text(
            f"📅 Выбрано: {start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')}\n\n📍 Теперь напишите адрес доставки оборудования:"
        )
    
    elif data.startswith("admin_"):
        user = query.from_user
        if f"@{user.username}" != admin_username:
            await query.edit_message_text("❌ У вас нет доступа к админ-панели.")
            return
        
        if data == "admin_all_bookings":
            bookings = await db.bookings.find().sort("created_at", -1).limit(10).to_list(10)
            message = "📋 Последние 10 бронирований:\n\n"
            
            for booking in bookings:
                b = Booking(**booking)
                status_emoji = {"pending": "⏳", "confirmed": "✅", "completed": "✔️", "cancelled": "❌"}
                message += f"{status_emoji.get(b.status, '❓')} {b.start_date.strftime('%d.%m')} | {b.masks_count}🥽 | {b.price}₽\n"
            
            keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="admin_back")]]
            await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard))
        
        elif data == "admin_active_bookings":
            today = datetime.now(timezone.utc)
            bookings = await db.bookings.find({
                "status": {"$in": ["pending", "confirmed"]},
                "end_date": {"$gte": today}
            }).sort("start_date", 1).to_list(20)
            
            message = "⏳ Активные бронирования:\n\n"
            
            for booking in bookings:
                b = Booking(**booking)
                status_emoji = {"pending": "⏳", "confirmed": "✅"}
                message += f"{status_emoji.get(b.status, '❓')} {b.start_date.strftime('%d.%m')} - {b.end_date.strftime('%d.%m')}\n"
                message += f"   🥽 {b.masks_count} маски | 💰 {b.price}₽\n"
                message += f"   👤 {b.first_name or 'Неизвестно'}\n\n"
            
            if not bookings:
                message += "Нет активных бронирований."
            
            keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="admin_back")]]
            await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard))
        
        elif data == "admin_stats":
            today = datetime.now(timezone.utc)
            month_start = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            
            total_bookings = await db.bookings.count_documents({})
            monthly_bookings = await db.bookings.count_documents({"created_at": {"$gte": month_start}})
            
            # Calculate monthly revenue
            pipeline = [
                {"$match": {"created_at": {"$gte": month_start}, "status": {"$ne": "cancelled"}}},
                {"$group": {"_id": None, "total_revenue": {"$sum": "$price"}}}
            ]
            result = await db.bookings.aggregate(pipeline).to_list(1)
            monthly_revenue = result[0]["total_revenue"] if result else 0
            
            message = f"""📊 Статистика:

📈 Всего бронирований: {total_bookings}
📅 За текущий месяц: {monthly_bookings}
💰 Доход за месяц: {monthly_revenue}₽

🗓️ Период: {month_start.strftime('%d.%m.%Y')} - {today.strftime('%d.%m.%Y')}"""
            
            keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="admin_back")]]
            await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard))
        
        elif data == "admin_back":
            await admin_command(query, context)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages (delivery address)"""
    user_id = update.effective_user.id
    
    if user_id not in user_sessions or "start_date" not in user_sessions[user_id]:
        return
    
    delivery_address = update.message.text
    session = user_sessions[user_id]
    
    # Create booking
    start_date = session["start_date"]
    days_count = session["days_count"]
    masks_count = session["masks_count"]
    end_date = start_date + timedelta(days=days_count)
    price = PRICES[masks_count][days_count]
    
    booking = Booking(
        user_id=user_id,
        username=update.effective_user.username,
        first_name=update.effective_user.first_name,
        masks_count=masks_count,
        days_count=days_count,
        start_date=start_date,
        end_date=end_date,
        price=price,
        delivery_address=delivery_address
    )
    
    # Save to database
    await db.bookings.insert_one(booking.dict())
    
    # Send confirmation to user
    mask_word = "маску" if masks_count == 1 else "маски"
    confirmation_message = f"""✅ Ваше бронирование принято!

🆔 Номер заказа: {booking.id[:8]}
🥽 Количество: {masks_count} {mask_word}
📅 Период: {start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')} ({days_count} дн.)
💰 Стоимость: {price}₽
📍 Адрес доставки: {delivery_address}

⏳ Ожидайте подтверждения от администратора.
Мы свяжемся с вами в ближайшее время!

Спасибо за выбор нашего сервиса! 🎮"""
    
    await update.message.reply_text(confirmation_message)
    
    # Send notification to admin
    await send_admin_notification(booking)
    
    # Clear user session
    if user_id in user_sessions:
        del user_sessions[user_id]

# FastAPI Routes
@api_router.post("/webhook")
async def telegram_webhook(request: Request):
    """Handle Telegram webhook"""
    try:
        update_data = await request.json()
        update = Update.de_json(update_data, bot)
        
        if telegram_app:
            # Ensure the application is initialized
            if not telegram_app.running:
                await telegram_app.initialize()
            await telegram_app.process_update(update)
        
        return {"status": "ok"}
    except Exception as e:
        logging.error(f"Webhook processing failed: {e}")
        raise HTTPException(status_code=500, detail=f"Webhook processing failed: {str(e)}")

@api_router.get("/bookings", response_model=List[Booking])
async def get_bookings():
    """Get all bookings"""
    bookings = await db.bookings.find().sort("created_at", -1).to_list(100)
    return [Booking(**booking) for booking in bookings]

@api_router.get("/bookings/active", response_model=List[Booking])
async def get_active_bookings():
    """Get active bookings"""
    today = datetime.now(timezone.utc)
    bookings = await db.bookings.find({
        "status": {"$in": ["pending", "confirmed"]},
        "end_date": {"$gte": today}
    }).sort("start_date", 1).to_list(100)
    return [Booking(**booking) for booking in bookings]

@api_router.put("/bookings/{booking_id}/status")
async def update_booking_status(booking_id: str, status: str):
    """Update booking status"""
    result = await db.bookings.update_one(
        {"id": booking_id},
        {"$set": {"status": status}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Booking not found")
    
    return {"status": "updated"}

@api_router.delete("/bookings/{booking_id}")
async def delete_booking(booking_id: str):
    """Delete booking"""
    result = await db.bookings.delete_one({"id": booking_id})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Booking not found")
    
    return {"status": "deleted"}

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("startup")
async def startup_event():
    """Initialize Telegram bot on startup"""
    global telegram_app
    telegram_app = await init_telegram_app()
    await telegram_app.initialize()
    logger.info("Telegram bot initialized")

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()