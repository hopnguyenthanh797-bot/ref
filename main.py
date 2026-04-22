import os
import re
import asyncio
import logging
from fastapi import FastAPI, Request
import uvicorn

from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base, Mapped, mapped_column
from sqlalchemy import Integer, String, select, update, ForeignKey

# ==========================================
# 1. CẤU HÌNH & BIẾN MÔI TRƯỜNG
# ==========================================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8743099227:AAGXQH4f9SUndwnCjahZ9b_Tsa-yQUGOq4g")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "7816353760")) # Thay bằng ID Telegram của bạn
PORT = int(os.environ.get("PORT", 5000))

# Khởi tạo Bot & FastAPI
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
app = FastAPI()
router = Router()
dp.include_router(router)

logging.basicConfig(level=logging.INFO)

# ==========================================
# 2. CẤU TRÚC DATABASE (SQLAlchemy Async)
# ==========================================
# Lưu ý: Trên Render, aiosqlite sẽ bị reset khi deploy lại. 
# Nếu có Database PostgreSQL trên Render, chỉ cần thay URL dưới đây.
DB_URL = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///bot_database.db")
if DB_URL.startswith("postgres://"):
    DB_URL = DB_URL.replace("postgres://", "postgresql+asyncpg://", 1)

engine = create_async_engine(DB_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    balance: Mapped[int] = mapped_column(Integer, default=0)

class Category(Base):
    __tablename__ = "categories"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)

class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category_id: Mapped[int] = mapped_column(Integer, ForeignKey("categories.id"))
    name: Mapped[str] = mapped_column(String, nullable=False)
    price: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=True)

class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer)
    product_name: Mapped[str] = mapped_column(String)
    price: Mapped[int] = mapped_column(Integer)
    target_username: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="PENDING")

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

# ==========================================
# 3. QUẢN LÝ TRẠNG THÁI (FSM)
# ==========================================
class BuyState(StatesGroup):
    waiting_for_username = State()
    product_id = State()
    price = State()
    product_name = State()

class AdminState(StatesGroup):
    add_category_name = State()
    add_product_category = State()
    add_product_name = State()
    add_product_price = State()
    add_product_desc = State()

# ==========================================
# 4. GIAO DIỆN INLINE KEYBOARDS
# ==========================================
def main_menu_kb():
    kb = [
        [InlineKeyboardButton(text="🛍 Danh Mục Sản Phẩm", callback_data="show_categories")],
        [InlineKeyboardButton(text="💳 Nạp Tiền (Auto MSB)", callback_data="topup_info"),
         InlineKeyboardButton(text="👤 Tài Khoản", callback_data="my_profile")],
        [InlineKeyboardButton(text="🎧 Hỗ Trợ Kỹ Thuật", url=f"tg://user?id={ADMIN_ID}")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def admin_menu_kb():
    kb = [
        [InlineKeyboardButton(text="📂 Thêm Danh Mục Mới", callback_data="admin_add_cat")],
        [InlineKeyboardButton(text="📦 Thêm Sản Phẩm Mới", callback_data="admin_add_prod")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

# ==========================================
# 5. XỬ LÝ LỆNH BOT (USER TIER)
# ==========================================
@router.message(CommandStart())
async def cmd_start(message: Message):
    async with AsyncSessionLocal() as session:
        # Check and create user
        stmt = select(User).where(User.telegram_id == message.from_user.id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        if not user:
            new_user = User(telegram_id=message.from_user.id, balance=0)
            session.add(new_user)
            await session.commit()

    text = (
        f"👋 Xin chào <b>{message.from_user.full_name}</b>!\n\n"
        f"🚀 <b>HỆ THỐNG MUA BÁN GROUP & KÊNH TELEGRAM TỰ ĐỘNG</b>\n"
        f"Giao dịch an toàn - Chuyển quyền owner siêu tốc 24/7.\n\n"
        f"👇 Vui lòng chọn tính năng bên dưới:"
    )
    await message.answer(text, reply_markup=main_menu_kb())

@router.callback_query(F.data == "my_profile")
async def show_profile(call: CallbackQuery):
    async with AsyncSessionLocal() as session:
        stmt = select(User).where(User.telegram_id == call.from_user.id)
        user = (await session.execute(stmt)).scalar_one()
        
    text = (
        f"👤 <b>Thông Tin Của Bạn</b>\n"
        f"├ ID Telegram: <code>{call.from_user.id}</code>\n"
        f"└ Số dư hiện tại: <b>{user.balance:,} VNĐ</b>\n"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Quay lại", callback_data="back_main")]])
    await call.message.edit_text(text, reply_markup=kb)

@router.callback_query(F.data == "topup_info")
async def show_topup(call: CallbackQuery):
    text = (
        f"🏦 <b>NẠP TIỀN TỰ ĐỘNG QUA SEPAY</b>\n\n"
        f"💳 Ngân hàng: <b>MSB (Ngân hàng Hàng Hải)</b>\n"
        f"🔢 Số tài khoản: <code>1234567890</code>\n" # Sửa lại số tài khoản thật của bạn
        f"👤 Chủ tài khoản: <b>NGUYEN VAN A</b>\n\n"
        f"📝 <b>Nội dung chuyển khoản (bắt buộc):</b>\n"
        f"👉 <code>NAP {call.from_user.id}</code>\n\n"
        f"<i>⚠️ Hệ thống xử lý tự động trong 3 - 5 giây. Nếu sai nội dung vui lòng liên hệ Admin.</i>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Quay lại", callback_data="back_main")]])
    await call.message.edit_text(text, reply_markup=kb)

@router.callback_query(F.data == "back_main")
async def back_to_main(call: CallbackQuery, state: FSMContext):
    await state.clear()
    text = f"🚀 <b>HỆ THỐNG MUA BÁN GROUP & KÊNH TELEGRAM TỰ ĐỘNG</b>"
    await call.message.edit_text(text, reply_markup=main_menu_kb())

# --- LUỒNG MUA HÀNG ---
@router.callback_query(F.data == "show_categories")
async def show_categories(call: CallbackQuery):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Category))
        categories = result.scalars().all()
        
    if not categories:
        await call.answer("Hiện chưa có danh mục nào!", show_alert=True)
        return
        
    kb = []
    for cat in categories:
        kb.append([InlineKeyboardButton(text=f"📂 {cat.name}", callback_data=f"cat_{cat.id}")])
    kb.append([InlineKeyboardButton(text="🔙 Quay lại", callback_data="back_main")])
    
    await call.message.edit_text("🛒 <b>Chọn Danh Mục Bạn Quan Tâm:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("cat_"))
async def show_products(call: CallbackQuery):
    cat_id = int(call.data.split("_")[1])
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Product).where(Product.category_id == cat_id))
        products = result.scalars().all()
        
    kb = []
    for p in products:
        kb.append([InlineKeyboardButton(text=f"▪️ {p.name} - {p.price:,}đ", callback_data=f"prod_{p.id}")])
    kb.append([InlineKeyboardButton(text="🔙 Quay lại danh mục", callback_data="show_categories")])
    
    await call.message.edit_text("📦 <b>Danh sách sản phẩm:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("prod_"))
async def product_details(call: CallbackQuery):
    prod_id = int(call.data.split("_")[1])
    async with AsyncSessionLocal() as session:
        product = (await session.execute(select(Product).where(Product.id == prod_id))).scalar_one_or_none()
        
    if not product:
        await call.answer("Sản phẩm không tồn tại!", show_alert=True)
        return
        
    text = (
        f"🏷 <b>{product.name}</b>\n\n"
        f"📝 Mô tả: <i>{product.description}</i>\n"
        f"💰 Giá: <b>{product.price:,} VNĐ</b>"
    )
    kb = [
        [InlineKeyboardButton(text="✅ Mua Ngay", callback_data=f"buy_{product.id}")],
        [InlineKeyboardButton(text="🔙 Quay lại", callback_data="show_categories")]
    ]
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("buy_"))
async def process_buy(call: CallbackQuery, state: FSMContext):
    prod_id = int(call.data.split("_")[1])
    user_id = call.from_user.id
    
    async with AsyncSessionLocal() as session:
        product = (await session.execute(select(Product).where(Product.id == prod_id))).scalar_one()
        user = (await session.execute(select(User).where(User.telegram_id == user_id))).scalar_one()
        
        if user.balance < product.price:
            await call.answer("❌ Số dư không đủ! Vui lòng nạp thêm.", show_alert=True)
            return

    # Set State yêu cầu nhập Username
    await state.update_data(product_id=product.id, price=product.price, product_name=product.name)
    await state.set_state(BuyState.waiting_for_username)
    
    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Hủy bỏ", callback_data="back_main")]])
    await call.message.edit_text(
        f"⚠️ <b>YÊU CẦU BẮT BUỘC:</b>\n\n"
        f"Bạn đang mua: <b>{product.name}</b>\n"
        f"Vui lòng nhập <code>@username</code> Telegram của bạn để Admin cấp quyền Transfer Ownership.\n\n"
        f"<i>VD: @my_telegram_id</i>", 
        reply_markup=cancel_kb
    )

@router.message(BuyState.waiting_for_username)
async def confirm_purchase(message: Message, state: FSMContext):
    username = message.text.strip()
    if not username.startswith("@"):
        await message.answer("❌ Username phải bắt đầu bằng ký tự '@'. Vui lòng nhập lại:")
        return
        
    data = await state.get_data()
    price = data['price']
    p_name = data['product_name']
    
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.telegram_id == message.from_user.id))).scalar_one()
        
        # Check lại balance lần cuối tránh race condition
        if user.balance < price:
            await message.answer("❌ Số dư của bạn không đủ để thực hiện giao dịch này.")
            await state.clear()
            return
            
        # Trừ tiền
        user.balance -= price
        # Lưu Order
        new_order = Order(user_id=message.from_user.id, product_name=p_name, price=price, target_username=username)
        session.add(new_order)
        await session.commit()

    await state.clear()
    await message.answer(
        f"✅ <b>GIAO DỊCH THÀNH CÔNG!</b>\n\n"
        f"📦 Đã mua: <b>{p_name}</b>\n"
        f"🎯 Nhận quyền tại: <code>{username}</code>\n\n"
        f"⏳ Admin đã nhận được lệnh và sẽ tiến hành transfer cho bạn trong ít phút."
    )
    
    # Bắn thông báo cho Admin
    admin_msg = (
        f"🚨 <b>ĐƠN HÀNG MỚI</b> 🚨\n\n"
        f"👤 Khách hàng: <code>{message.from_user.id}</code>\n"
        f"📦 Sản phẩm: <b>{p_name}</b>\n"
        f"💰 Tiền thu: {price:,} VNĐ\n"
        f"🎯 <b>Acc Nhận:</b> {username}"
    )
    try:
        await bot.send_message(chat_id=ADMIN_ID, text=admin_msg)
    except Exception as e:
        logging.error(f"Failed to send admin alert: {e}")

# ==========================================
# 6. XỬ LÝ LỆNH ADMIN (Tùy chỉnh danh mục/SP)
# ==========================================
@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("🛠 <b>QUẢN TRỊ HỆ THỐNG</b>\nChọn thao tác:", reply_markup=admin_menu_kb())

@router.callback_query(F.data == "admin_add_cat")
async def admin_ask_cat(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID: return
    await state.set_state(AdminState.add_category_name)
    await call.message.edit_text("📝 Nhập tên Danh Mục mới:")

@router.message(AdminState.add_category_name)
async def admin_save_cat(message: Message, state: FSMContext):
    cat_name = message.text.strip()
    async with AsyncSessionLocal() as session:
        new_cat = Category(name=cat_name)
        session.add(new_cat)
        await session.commit()
    await message.answer(f"✅ Đã thêm danh mục: <b>{cat_name}</b>", reply_markup=admin_menu_kb())
    await state.clear()

@router.callback_query(F.data == "admin_add_prod")
async def admin_ask_prod_cat(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID: return
    async with AsyncSessionLocal() as session:
        categories = (await session.execute(select(Category))).scalars().all()
        
    if not categories:
        await call.answer("❌ Phải tạo Danh Mục trước!", show_alert=True)
        return
        
    kb = []
    for cat in categories:
        kb.append([InlineKeyboardButton(text=cat.name, callback_data=f"selcat_{cat.id}")])
    
    await call.message.edit_text("📂 Chọn danh mục cho sản phẩm mới:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("selcat_"))
async def admin_ask_prod_name(call: CallbackQuery, state: FSMContext):
    cat_id = int(call.data.split("_")[1])
    await state.update_data(cat_id=cat_id)
    await state.set_state(AdminState.add_product_name)
    await call.message.edit_text("📝 Nhập TÊN sản phẩm:")

@router.message(AdminState.add_product_name)
async def admin_ask_prod_price(message: Message, state: FSMContext):
    await state.update_data(p_name=message.text.strip())
    await state.set_state(AdminState.add_product_price)
    await message.answer("💰 Nhập GIÁ sản phẩm (Viết số, vd: 500000):")

@router.message(AdminState.add_product_price)
async def admin_ask_prod_desc(message: Message, state: FSMContext):
    try:
        price = int(message.text.strip())
        await state.update_data(p_price=price)
        await state.set_state(AdminState.add_product_desc)
        await message.answer("📋 Nhập MÔ TẢ sản phẩm:")
    except ValueError:
        await message.answer("❌ Giá phải là số nguyên. Nhập lại:")

@router.message(AdminState.add_product_desc)
async def admin_save_prod(message: Message, state: FSMContext):
    desc = message.text.strip()
    data = await state.get_data()
    
    async with AsyncSessionLocal() as session:
        new_prod = Product(category_id=data['cat_id'], name=data['p_name'], price=data['p_price'], description=desc)
        session.add(new_prod)
        await session.commit()
        
    await message.answer(f"✅ Đã thêm sản phẩm <b>{data['p_name']}</b> thành công!", reply_markup=admin_menu_kb())
    await state.clear()

# ==========================================
# 7. FASTAPI CATCH WEBHOOK SEPAY (NẠP TỰ ĐỘNG)
# ==========================================
@app.post("/sepay-webhook")
async def sepay_webhook(request: Request):
    try:
        data = await request.json()
        amount = int(data.get('transferAmount', 0))
        content = str(data.get('content', '')).upper()
        
        # Cú pháp: NAP <USER_ID>
        match = re.search(r'NAP\s+(\d+)', content)
        if match and amount > 0:
            user_id = int(match.group(1))
            
            async with AsyncSessionLocal() as session:
                user = (await session.execute(select(User).where(User.telegram_id == user_id))).scalar_one_or_none()
                if user:
                    user.balance += amount
                    await session.commit()
                    
                    # Bắn tin nhắn cho user thông qua API của Bot
                    try:
                        await bot.send_message(
                            chat_id=user_id, 
                            text=f"✅ <b>NẠP TIỀN THÀNH CÔNG</b>\n\nTài khoản của bạn vừa được cộng <b>{amount:,} VNĐ</b> từ MSB!"
                        )
                    except Exception as e:
                        logging.error(f"Cannot send topup message to user: {e}")
                        
        return {"status": "success"}
    except Exception as e:
        logging.error(f"Webhook error: {e}")
        return {"status": "error"}

@app.get("/")
async def health_check():
    return {"status": "Bot & Server are running!"}

# ==========================================
# 8. HỆ THỐNG KHỞI CHẠY (CHẠY SONG SONG)
# ==========================================
@app.on_event("startup")
async def on_startup():
    await init_db()
    # Chạy Polling của Bot dưới dạng Task ngầm bên trong Event Loop của FastAPI
    asyncio.create_task(dp.start_polling(bot))
    logging.info("🚀 Bot Telegram đã khởi động...")

if __name__ == "__main__":
    # Render sẽ cung cấp biến môi trường PORT
    uvicorn.run(app, host="0.0.0.0", port=PORT)
    
