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
from sqlalchemy import Integer, String, select, update, ForeignKey, func, Boolean

# ==========================================
# 1. CẤU HÌNH & BIẾN MÔI TRƯỜNG
# ==========================================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8743099227:AAGXQH4f9SUndwnCjahZ9b_Tsa-yQUGOq4g")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "7816353760"))
PORT = int(os.environ.get("PORT", 5000))

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
app = FastAPI()
router = Router()
dp.include_router(router)

logging.basicConfig(level=logging.INFO)

# ==========================================
# 2. CẤU TRÚC DATABASE (V3: Thêm Giftcode)
# ==========================================
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
    category_id: Mapped[int] = mapped_column(Integer, ForeignKey("categories.id", ondelete="CASCADE"))
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
    status: Mapped[str] = mapped_column(String, default="PENDING") # PENDING / DONE / REFUNDED

class GiftCode(Base):
    __tablename__ = "giftcodes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String, unique=True, index=True)
    amount: Mapped[int] = mapped_column(Integer)
    is_used: Mapped[bool] = mapped_column(Boolean, default=False)

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

class UserActionState(StatesGroup):
    enter_giftcode = State()

class AdminState(StatesGroup):
    # Category
    add_category_name = State()
    del_category = State()
    # Product
    add_product_category = State()
    add_product_name = State()
    add_product_price = State()
    add_product_desc = State()
    del_product = State()
    # Users & Balance
    manage_balance = State()
    # Broadcast
    broadcast_msg = State()
    # Giftcode
    add_giftcode_name = State()
    add_giftcode_amount = State()

# ==========================================
# 4. GIAO DIỆN INLINE KEYBOARDS
# ==========================================
def main_menu_kb():
    kb = [
        [InlineKeyboardButton(text="🛍 Danh Mục Sản Phẩm", callback_data="show_categories")],
        [InlineKeyboardButton(text="💳 Nạp Tiền (Auto)", callback_data="topup_info"),
         InlineKeyboardButton(text="👤 Tài Khoản", callback_data="my_profile")],
        [InlineKeyboardButton(text="📜 Lịch Sử Đơn Hàng", callback_data="my_orders"),
         InlineKeyboardButton(text="🎁 Nhập Giftcode", callback_data="enter_giftcode")],
        [InlineKeyboardButton(text="🎧 Hỗ Trợ Kỹ Thuật", url=f"tg://user?id={ADMIN_ID}")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def cancel_admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Hủy Thao Tác", callback_data="admin_cancel")]])

def cancel_user_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Hủy", callback_data="back_main")]])

# ==========================================
# 5. XỬ LÝ LỆNH BOT (USER TIER)
# ==========================================
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    async with AsyncSessionLocal() as session:
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
        f"🏦 <b>NẠP TIỀN TỰ ĐỘNG </b>\n\n"
        f"💳 Ngân hàng: <b>MSB (Ngân hàng Hàng Hải)</b>\n"
        f"🔢 Số tài khoản: <code>96886693002613</code>\n" 
        f"👤 Chủ tài khoản: <b>NGUYEN THANH HOP</b>\n\n"
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

# --- XEM LỊCH SỬ ĐƠN HÀNG ---
@router.callback_query(F.data == "my_orders")
async def show_my_orders(call: CallbackQuery):
    async with AsyncSessionLocal() as session:
        stmt = select(Order).where(Order.user_id == call.from_user.id).order_by(Order.id.desc()).limit(5)
        orders = (await session.execute(stmt)).scalars().all()
        
    if not orders:
        text = "🤷‍♂️ Bạn chưa có đơn hàng nào."
    else:
        text = "📜 <b>5 ĐƠN HÀNG GẦN NHẤT CỦA BẠN:</b>\n\n"
        for o in orders:
            status_str = "⏳ Đang xử lý" if o.status == "PENDING" else "✅ Hoàn thành" if o.status == "DONE" else "❌ Đã Hoàn Tiền"
            text += f"🔹 <b>Mã ĐH:</b> #{o.id}\n"
            text += f"📦 <b>SP:</b> {o.product_name} ({o.price:,}đ)\n"
            text += f"🎯 <b>Nhận tại:</b> {o.target_username}\n"
            text += f"📈 <b>Trạng thái:</b> {status_str}\n"
            text += "------------------------\n"

    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Quay lại", callback_data="back_main")]])
    await call.message.edit_text(text, reply_markup=kb)

# --- NHẬP GIFTCODE ---
@router.callback_query(F.data == "enter_giftcode")
async def ask_giftcode(call: CallbackQuery, state: FSMContext):
    await state.set_state(UserActionState.enter_giftcode)
    await call.message.edit_text("🎁 Vui lòng nhập mã Giftcode của bạn vào đây:", reply_markup=cancel_user_kb())

@router.message(UserActionState.enter_giftcode)
async def process_giftcode(message: Message, state: FSMContext):
    code_input = message.text.strip()
    async with AsyncSessionLocal() as session:
        # Tìm Giftcode
        gcode = (await session.execute(select(GiftCode).where(GiftCode.code == code_input))).scalar_one_or_none()
        
        if not gcode:
            await message.answer("❌ Mã Giftcode không tồn tại. Thử lại:", reply_markup=cancel_user_kb())
            return
        if gcode.is_used:
            await message.answer("❌ Mã Giftcode này đã được sử dụng. Thử lại:", reply_markup=cancel_user_kb())
            return
            
        # Nếu OK, cộng tiền và đổi trạng thái
        gcode.is_used = True
        user = (await session.execute(select(User).where(User.telegram_id == message.from_user.id))).scalar_one()
        user.balance += gcode.amount
        await session.commit()
        
    await state.clear()
    await message.answer(f"🎉 <b>CHÚC MỪNG!</b>\nBạn đã nạp thành công mã Giftcode.\n💰 Tài khoản được cộng: <b>{gcode.amount:,} VNĐ</b>")
    await cmd_start(message, state) # Quay về menu

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
        await message.answer("❌ Username phải bắt đầu bằng ký tự '@'. Vui lòng nhập lại:", reply_markup=cancel_user_kb())
        return
        
    data = await state.get_data()
    price = data['price']
    p_name = data['product_name']
    
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.telegram_id == message.from_user.id))).scalar_one()
        
        if user.balance < price:
            await message.answer("❌ Số dư của bạn không đủ. Giao dịch bị hủy.")
            await state.clear()
            return
            
        user.balance -= price
        new_order = Order(user_id=message.from_user.id, product_name=p_name, price=price, target_username=username, status="PENDING")
        session.add(new_order)
        await session.commit()
        await session.refresh(new_order) # Lấy ID của order vừa tạo
        order_id = new_order.id

    await state.clear()
    await message.answer(
        f"✅ <b>GIAO DỊCH THÀNH CÔNG!</b>\n\n"
        f"📦 Đã mua: <b>{p_name}</b>\n"
        f"🎯 Nhận quyền tại: <code>{username}</code>\n\n"
        f"⏳ Admin đã nhận được lệnh và sẽ tiến hành transfer cho bạn trong ít phút."
    )
    
    # BẮN BILL CHO ADMIN KÈM NÚT DUYỆT ĐƠN (V3)
    admin_msg = (
        f"🚨 <b>ĐƠN HÀNG MỚI TỪ BOT</b> 🚨\n\n"
        f"🔢 Mã ĐH: <b>#{order_id}</b>\n"
        f"👤 ID Khách: <code>{message.from_user.id}</code>\n"
        f"📦 Sản phẩm: <b>{p_name}</b>\n"
        f"💰 Giá trị: {price:,} VNĐ\n"
        f"🎯 <b>Cần Transfer vào Acc:</b> {username}\n\n"
        f"<i>⚠️ Vui lòng thao tác Transfer trong Group/Kênh xong thì ấn nút bên dưới để báo cho Khách.</i>"
    )
    
    admin_bill_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Xong! Báo Khách Nhận Kênh", callback_data=f"ad_ord_done_{order_id}")],
        [InlineKeyboardButton(text="❌ Lỗi / Hủy & Hoàn Tiền Khách", callback_data=f"ad_ord_fail_{order_id}")]
    ])
    
    try:
        await bot.send_message(chat_id=ADMIN_ID, text=admin_msg, reply_markup=admin_bill_kb)
    except:
        pass


# ==========================================
# 6. XỬ LÝ LỆNH ADMIN (XỊN XÒ PRO MAX V3)
# ==========================================

async def get_admin_dashboard_text():
    async with AsyncSessionLocal() as session:
        total_users = (await session.execute(select(func.count(User.id)))).scalar()
        total_cats = (await session.execute(select(func.count(Category.id)))).scalar()
        total_prods = (await session.execute(select(func.count(Product.id)))).scalar()
        total_orders = (await session.execute(select(func.count(Order.id)))).scalar()
        
        text = (
            f"👑 <b>BẢNG ĐIỀU KHIỂN QUẢN TRỊ VIÊN</b>\n\n"
            f"👥 Tổng User: <b>{total_users}</b>\n"
            f"📂 Danh mục: <b>{total_cats}</b> | 📦 Sản phẩm: <b>{total_prods}</b>\n"
            f"🛒 Tổng Đơn Hàng: <b>{total_orders}</b>\n\n"
            f"<i>Lựa chọn thao tác bên dưới:</i>"
        )
        return text

def super_admin_kb():
    kb = [
        [InlineKeyboardButton(text="➕ Thêm Danh Mục", callback_data="adm_add_cat"),
         InlineKeyboardButton(text="🗑 Xóa Danh Mục", callback_data="adm_del_cat")],
        [InlineKeyboardButton(text="➕ Thêm Sản Phẩm", callback_data="adm_add_prod"),
         InlineKeyboardButton(text="🗑 Xóa Sản Phẩm", callback_data="adm_del_prod")],
        [InlineKeyboardButton(text="🎫 Tạo Mã Giftcode Mới", callback_data="adm_make_giftcode")],
        [InlineKeyboardButton(text="💰 Cộng/Trừ Tiền User", callback_data="adm_money")],
        [InlineKeyboardButton(text="📢 Gửi Thông Báo Toàn Bot", callback_data="adm_broadcast")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await state.clear()
    text = await get_admin_dashboard_text()
    await message.answer(text, reply_markup=super_admin_kb())

@router.callback_query(F.data == "admin_cancel")
async def cancel_admin_action(call: CallbackQuery, state: FSMContext):
    await state.clear()
    text = await get_admin_dashboard_text()
    await call.message.edit_text(text, reply_markup=super_admin_kb())

# --- ADMIN DUYỆT ĐƠN TỪ NÚT BẤM KHI CÓ BILL (V3) ---
@router.callback_query(F.data.startswith("ad_ord_"))
async def admin_process_order(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID: return
    action_parts = call.data.split("_")
    action_type = action_parts[2] # "done" hoặc "fail"
    order_id = int(action_parts[3])
    
    async with AsyncSessionLocal() as session:
        order = (await session.execute(select(Order).where(Order.id == order_id))).scalar_one_or_none()
        if not order:
            await call.answer("Đơn hàng không tồn tại!", show_alert=True)
            return
            
        if order.status != "PENDING":
            await call.answer("Đơn hàng này đã được xử lý từ trước rồi!", show_alert=True)
            return
            
        if action_type == "done":
            order.status = "DONE"
            await session.commit()
            await call.message.edit_text(call.message.text + "\n\n✅ <b>BẠN ĐÃ DUYỆT ĐƠN NÀY (ĐÃ TRANSFER).</b>")
            # Báo cho khách
            try:
                await bot.send_message(order.user_id, f"🎉 <b>TIN VUI TỪ ADMIN!</b>\n\nĐơn hàng <b>#{order.id} ({order.product_name})</b> của bạn đã được Admin xử lý Transfer quyền Owner thành công. Vui lòng check Telegram nhé!")
            except: pass
            
        elif action_type == "fail":
            order.status = "REFUNDED"
            # Hoàn tiền cho User
            user = (await session.execute(select(User).where(User.telegram_id == order.user_id))).scalar_one()
            user.balance += order.price
            await session.commit()
            
            await call.message.edit_text(call.message.text + "\n\n❌ <b>BẠN ĐÃ HỦY ĐƠN VÀ HOÀN TIỀN CHO KHÁCH.</b>")
            # Báo cho khách
            try:
                await bot.send_message(order.user_id, f"⚠️ <b>THÔNG BÁO HỦY ĐƠN HÀNG!</b>\n\nĐơn hàng <b>#{order.id} ({order.product_name})</b> của bạn đã bị hủy do một số lỗi kỹ thuật hoặc hết hàng.\n💰 Hệ thống đã hoàn lại <b>{order.price:,} VNĐ</b> vào số dư của bạn. Thành thật xin lỗi vì sự bất tiện này!")
            except: pass

# --- TẠO GIFTCODE (V3) ---
@router.callback_query(F.data == "adm_make_giftcode")
async def adm_make_giftcode(call: CallbackQuery, state: FSMContext):
    await state.set_state(AdminState.add_giftcode_name)
    await call.message.edit_text("🎫 Nhập CHỮ (Mã) Giftcode bạn muốn tạo (VD: VIP2026, TANTHU...):", reply_markup=cancel_admin_kb())

@router.message(AdminState.add_giftcode_name)
async def adm_ask_gift_amount(message: Message, state: FSMContext):
    await state.update_data(g_code=message.text.strip().upper())
    await state.set_state(AdminState.add_giftcode_amount)
    await message.answer("💰 Nhập SỐ TIỀN được cộng cho mã Giftcode này:", reply_markup=cancel_admin_kb())

@router.message(AdminState.add_giftcode_amount)
async def adm_save_giftcode(message: Message, state: FSMContext):
    try:
        amount = int(message.text.strip())
        data = await state.get_data()
        
        async with AsyncSessionLocal() as session:
            new_gift = GiftCode(code=data['g_code'], amount=amount)
            session.add(new_gift)
            await session.commit()
            
        await message.answer(f"✅ Đã tạo Giftcode thành công!\n\nMã: <code>{data['g_code']}</code>\nTrị giá: <b>{amount:,} VNĐ</b>", reply_markup=super_admin_kb())
        await state.clear()
    except Exception as e:
        await message.answer("❌ Có lỗi xảy ra (có thể mã bị trùng hoặc nhập sai số tiền). Vui lòng thử lại:")

# --- QUẢN LÝ DANH MỤC ---
@router.callback_query(F.data == "adm_add_cat")
async def adm_add_cat(call: CallbackQuery, state: FSMContext):
    await state.set_state(AdminState.add_category_name)
    await call.message.edit_text("📝 Nhập TÊN Danh Mục mới:", reply_markup=cancel_admin_kb())

@router.message(AdminState.add_category_name)
async def adm_save_cat(message: Message, state: FSMContext):
    async with AsyncSessionLocal() as session:
        new_cat = Category(name=message.text.strip())
        session.add(new_cat)
        await session.commit()
    await message.answer(f"✅ Thêm danh mục <b>{message.text}</b> thành công!")
    await cmd_admin(message, state)

@router.callback_query(F.data == "adm_del_cat")
async def adm_del_cat_list(call: CallbackQuery):
    async with AsyncSessionLocal() as session:
        categories = (await session.execute(select(Category))).scalars().all()
    if not categories:
        await call.answer("Chưa có danh mục nào!", show_alert=True)
        return
    kb = [[InlineKeyboardButton(text=f"🗑 Xóa: {c.name}", callback_data=f"delcat_{c.id}")] for c in categories]
    kb.append([InlineKeyboardButton(text="❌ Hủy", callback_data="admin_cancel")])
    await call.message.edit_text("⚠️ <b>Chọn Danh Mục để XÓA:</b>\n<i>(Lưu ý: Xóa danh mục sẽ KHÔNG xóa sản phẩm bên trong nó)</i>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("delcat_"))
async def adm_do_del_cat(call: CallbackQuery):
    c_id = int(call.data.split("_")[1])
    async with AsyncSessionLocal() as session:
        cat = (await session.execute(select(Category).where(Category.id == c_id))).scalar_one_or_none()
        if cat:
            await session.delete(cat)
            await session.commit()
            await call.answer("✅ Xóa thành công!", show_alert=True)
    text = await get_admin_dashboard_text()
    await call.message.edit_text(text, reply_markup=super_admin_kb())

# --- QUẢN LÝ SẢN PHẨM ---
@router.callback_query(F.data == "adm_add_prod")
async def adm_add_prod_cat(call: CallbackQuery, state: FSMContext):
    async with AsyncSessionLocal() as session:
        categories = (await session.execute(select(Category))).scalars().all()
    if not categories:
        await call.answer("❌ Phải tạo Danh Mục trước!", show_alert=True)
        return
    kb = [[InlineKeyboardButton(text=c.name, callback_data=f"pcat_{c.id}")] for c in categories]
    kb.append([InlineKeyboardButton(text="❌ Hủy", callback_data="admin_cancel")])
    await call.message.edit_text("📂 Chọn danh mục cho Sản Phẩm mới:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("pcat_"))
async def adm_add_prod_name(call: CallbackQuery, state: FSMContext):
    await state.update_data(cat_id=int(call.data.split("_")[1]))
    await state.set_state(AdminState.add_product_name)
    await call.message.edit_text("📝 Nhập TÊN sản phẩm:", reply_markup=cancel_admin_kb())

@router.message(AdminState.add_product_name)
async def adm_add_prod_price(message: Message, state: FSMContext):
    await state.update_data(p_name=message.text.strip())
    await state.set_state(AdminState.add_product_price)
    await message.answer("💰 Nhập GIÁ (Số nguyên, vd: 500000):", reply_markup=cancel_admin_kb())

@router.message(AdminState.add_product_price)
async def adm_add_prod_desc(message: Message, state: FSMContext):
    try:
        await state.update_data(p_price=int(message.text.strip()))
        await state.set_state(AdminState.add_product_desc)
        await message.answer("📋 Nhập MÔ TẢ sản phẩm:", reply_markup=cancel_admin_kb())
    except:
        await message.answer("❌ Lỗi: Giá tiền phải là số. Nhập lại:")

@router.message(AdminState.add_product_desc)
async def adm_save_prod(message: Message, state: FSMContext):
    data = await state.get_data()
    async with AsyncSessionLocal() as session:
        new_prod = Product(category_id=data['cat_id'], name=data['p_name'], price=data['p_price'], description=message.text.strip())
        session.add(new_prod)
        await session.commit()
    await message.answer(f"✅ Đã thêm SP: <b>{data['p_name']}</b>")
    await cmd_admin(message, state)

@router.callback_query(F.data == "adm_del_prod")
async def adm_del_prod_list(call: CallbackQuery):
    async with AsyncSessionLocal() as session:
        products = (await session.execute(select(Product))).scalars().all()
    if not products:
        await call.answer("Chưa có sản phẩm nào!", show_alert=True)
        return
    kb = [[InlineKeyboardButton(text=f"🗑 Xóa: {p.name}", callback_data=f"delp_{p.id}")] for p in products]
    kb.append([InlineKeyboardButton(text="❌ Hủy", callback_data="admin_cancel")])
    await call.message.edit_text("⚠️ <b>Chọn Sản Phẩm để XÓA:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("delp_"))
async def adm_do_del_prod(call: CallbackQuery):
    p_id = int(call.data.split("_")[1])
    async with AsyncSessionLocal() as session:
        prod = (await session.execute(select(Product).where(Product.id == p_id))).scalar_one_or_none()
        if prod:
            await session.delete(prod)
            await session.commit()
            await call.answer("✅ Xóa SP thành công!", show_alert=True)
    text = await get_admin_dashboard_text()
    await call.message.edit_text(text, reply_markup=super_admin_kb())

# --- QUẢN LÝ TIỀN & BROADCAST ---
@router.callback_query(F.data == "adm_money")
async def adm_money(call: CallbackQuery, state: FSMContext):
    await state.set_state(AdminState.manage_balance)
    text = (
        "💰 <b>CỘNG/TRỪ TIỀN THỦ CÔNG</b>\n\n"
        "Nhắn tin theo cú pháp sau để cộng/trừ tiền User:\n"
        "👉 Cú pháp: <code>ID_USER SỐ_TIỀN</code>\n\n"
        "<i>Ví dụ cộng 50k:</i> <code>123456789 50000</code>\n"
        "<i>Ví dụ trừ 50k:</i> <code>123456789 -50000</code>"
    )
    await call.message.edit_text(text, reply_markup=cancel_admin_kb())

@router.message(AdminState.manage_balance)
async def adm_exec_money(message: Message, state: FSMContext):
    try:
        parts = message.text.split()
        target_id = int(parts[0])
        amount = int(parts[1])
        
        async with AsyncSessionLocal() as session:
            user = (await session.execute(select(User).where(User.telegram_id == target_id))).scalar_one_or_none()
            if not user:
                await message.answer("❌ User ID này chưa từng chat với Bot.")
                return
            user.balance += amount
            await session.commit()
            
            await bot.send_message(target_id, f"🔔 Admin vừa biến động số dư của bạn: <b>{amount:,} VNĐ</b>")
            await message.answer(f"✅ Đã cộng/trừ <b>{amount:,}đ</b> cho User <code>{target_id}</code> thành công.")
            await cmd_admin(message, state)
    except:
        await message.answer("❌ Cú pháp sai. Hãy nhập ID SỐ_TIỀN (Ví dụ: 123456789 50000)")

@router.callback_query(F.data == "adm_broadcast")
async def adm_broadcast(call: CallbackQuery, state: FSMContext):
    await state.set_state(AdminState.broadcast_msg)
    await call.message.edit_text("📢 Nhập nội dung tin nhắn bạn muốn gửi cho TẤT CẢ User:", reply_markup=cancel_admin_kb())

@router.message(AdminState.broadcast_msg)
async def adm_exec_broadcast(message: Message, state: FSMContext):
    msg_text = message.text
    await message.answer("⏳ Đang tiến hành gửi tin nhắn cho toàn bộ User...")
    
    async with AsyncSessionLocal() as session:
        users = (await session.execute(select(User))).scalars().all()
        
    success = 0
    for u in users:
        try:
            await bot.send_message(u.telegram_id, f"📢 <b>THÔNG BÁO TỪ ADMIN:</b>\n\n{msg_text}")
            success += 1
            await asyncio.sleep(0.05) # Tránh bị Telegram flood limit
        except:
            pass # User đã block bot
            
    await message.answer(f"✅ <b>Hoàn tất!</b> Đã gửi thành công đến {success}/{len(users)} users.")
    await cmd_admin(message, state)


# ==========================================
# 7. FASTAPI CATCH WEBHOOK SEPAY (NẠP TỰ ĐỘNG)
# ==========================================
@app.post("/sepay-webhook")
async def sepay_webhook(request: Request):
    try:
        data = await request.json()
        amount = int(data.get('transferAmount', 0))
        content = str(data.get('content', '')).upper()
        
        match = re.search(r'NAP\s+(\d+)', content)
        if match and amount > 0:
            user_id = int(match.group(1))
            
            async with AsyncSessionLocal() as session:
                user = (await session.execute(select(User).where(User.telegram_id == user_id))).scalar_one_or_none()
                if user:
                    user.balance += amount
                    await session.commit()
                    
                    try:
                        await bot.send_message(
                            chat_id=user_id, 
                            text=f"✅ <b>NẠP TIỀN THÀNH CÔNG</b>\n\nTài khoản của bạn vừa được cộng <b>{amount:,} VNĐ</b> từ MSB!"
                        )
                    except:
                        pass
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
    asyncio.create_task(dp.start_polling(bot))
    logging.info("🚀 Bot Telegram đã khởi động...")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
