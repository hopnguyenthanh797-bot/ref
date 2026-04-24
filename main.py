import asyncio
from fastapi import FastAPI, Request
import uvicorn
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.client.default import DefaultBotProperties

from config import config
from database import db
from api_trumsmm import trum_api

# --- KHỞI TẠO ---
app = FastAPI()
bot = Bot(token=config.BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

# --- FSM CHO ADMIN ---
class AdminStates(StatesGroup):
    waiting_for_user_id = State()
    waiting_for_amount = State()
    waiting_for_markup = State()

# --- RENDER HEALTH CHECK ---
@app.get("/")
async def root():
    return {"status": "Bot is running perfectly"}

# --- GIAO DIỆN NGƯỜI DÙNG ---
def get_main_menu():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🛍 Sản phẩm", callback_data="menu_products"),
        InlineKeyboardButton(text="💰 Nạp tiền", callback_data="menu_deposit")
    )
    builder.row(
        InlineKeyboardButton(text="👤 Cá Nhân", callback_data="menu_profile"),
        InlineKeyboardButton(text="📚 Hướng Dẫn", url="https://t.me/huongdan")
    )
    if config.ADMIN_IDS:
        builder.row(InlineKeyboardButton(text="⚙️ Admin Panel", callback_data="admin_panel"))
    return builder.as_markup()

@dp.message(Command("start"))
async def start_cmd(message: Message, state: FSMContext):
    await state.clear()
    user = await db.get_user(message.from_user.id, message.from_user.full_name)
    text = (
        f"👋 <b>Chào mừng {message.from_user.full_name} đến với Shop!</b>\n\n"
        f"🆔 UserID: <code>{user['user_id']}</code>\n"
        f"💰 Số Dư: <b>{user['balance']:,} đ</b>\n\n"
        f"⚠️ Chọn chức năng bên dưới để bắt đầu."
    )
    await message.answer(text, reply_markup=get_main_menu())

@dp.callback_query(F.data == "menu_main")
async def back_main(call: CallbackQuery, state: FSMContext):
    await state.clear()
    user = await db.get_user(call.from_user.id, call.from_user.full_name)
    text = (
        f"👋 <b>Chào mừng {call.from_user.full_name} đến với Shop!</b>\n\n"
        f"🆔 UserID: <code>{user['user_id']}</code>\n"
        f"💰 Số Dư: <b>{user['balance']:,} đ</b>"
    )
    await call.message.edit_text(text, reply_markup=get_main_menu())

# --- LUỒNG HIỂN THỊ SẢN PHẨM & MUA HÀNG (LIVE STOCK) ---
@dp.callback_query(F.data == "menu_products")
async def show_products(call: CallbackQuery):
    await call.message.edit_text("🔄 Đang lấy dữ liệu kho hàng từ máy chủ mẹ...")
    
    res = await trum_api.get_services()
    if not res.get("success"):
        return await call.message.edit_text("❌ Hệ thống nguồn đang bảo trì. Vui lòng thử lại sau.", 
                                            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Quay lại", callback_data="menu_main")]]))
    
    # Lấy phần trăm ăn chênh lệch do Admin set
    markup_percent = await db.get_markup()
    
    builder = InlineKeyboardBuilder()
    
    for category in res.get("data", []):
        for pos in category.get("positions", []):
            stock = pos.get("stock")
            if stock > 0:
                pos_id = pos.get("position_id")
                pos_name = pos.get("position_name")
                original_price = pos.get("price")
                
                # Tự động tính giá bán chênh lệch
                sell_price = int(original_price + (original_price * markup_percent / 100))
                
                btn_text = f"📦 {pos_name} | {sell_price:,}đ | Kho: {stock}"
                builder.row(InlineKeyboardButton(text=btn_text, callback_data=f"buy_{pos_id}_{sell_price}"))
                
    builder.row(InlineKeyboardButton(text="⬅️ Quay lại", callback_data="menu_main"))
    await call.message.edit_text("🛍 <b>Danh sách sản phẩm (Cập nhật realtime):</b>", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("buy_"))
async def process_buy(call: CallbackQuery):
    _, pos_id, sell_price = call.data.split("_")
    sell_price = int(sell_price)
    pos_id = int(pos_id)
    
    user = await db.get_user(call.from_user.id, call.from_user.full_name)
    
    if user['balance'] < sell_price:
        return await call.answer("❌ Số dư không đủ, vui lòng nạp thêm tiền!", show_alert=True)
    
    await call.message.edit_text("⏳ Đang xử lý giao dịch qua cổng API mẹ...")
    
    # Thực hiện gọi mua hàng
    buy_res = await trum_api.buy_product(product_id=pos_id, quantity=1)
    
    if buy_res.get("success"):
        # Trừ tiền user, cộng vào total_spent
        await db.update_balance(user['user_id'], -sell_price)
        await db.add_spent(user['user_id'], sell_price)
        
        links = buy_res.get("download", [])
        if links:
            file_url = links[0]
            file_content = await trum_api.download_file(file_url)
            
            if file_content:
                parts = file_content.strip().split("|")
                phone = parts[0] if len(parts) > 0 else "N/A"
                two_fa = parts[1] if len(parts) > 1 else "Không"
                
                text = (
                    f"✅ <b>Giao dịch thành công!</b>\n"
                    f"💸 Bạn đã thanh toán: <b>{sell_price:,}đ</b>\n\n"
                    f"📱 <b>Phone:</b> <code>{phone}</code>\n"
                    f"🔐 <b>2FA:</b> <code>{two_fa}</code>\n\n"
                    f"<i>Sử dụng SĐT trên để đăng nhập, sau đó tải file Session để xem toàn bộ thông tin gốc.</i>"
                )
                builder = InlineKeyboardBuilder()
                builder.row(InlineKeyboardButton(text="📥 Tải File Session Gốc", url=file_url))
                builder.row(InlineKeyboardButton(text="⬅️ Về Trang Chủ", callback_data="menu_main"))
                
                await call.message.edit_text(text, reply_markup=builder.as_markup())
            else:
                await call.message.edit_text(f"✅ Đã mua. Tải tài nguyên tại đây:\n{file_url}")
    else:
        error_msg = buy_res.get("message", "Lỗi không xác định")
        text = f"❌ <b>Thất bại từ nguồn:</b>\n{error_msg}\n<i>Tiền của bạn chưa bị trừ.</i>"
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="⬅️ Quay lại danh sách", callback_data="menu_products"))
        await call.message.edit_text(text, reply_markup=builder.as_markup())

# --- ADMIN PANEL SIÊU XỊN ---
@dp.callback_query(F.data == "admin_panel")
async def admin_menu(call: CallbackQuery):
    if call.from_user.id not in config.ADMIN_IDS:
        return await call.answer("❌ Bạn không có quyền truy cập!", show_alert=True)
        
    # Check số dư tài khoản trên web mẹ
    balance_res = await trum_api.get_balance()
    admin_source_balance = balance_res.get("balance", 0) if balance_res.get("success") else "Lỗi API"
    markup = await db.get_markup()
    
    text = (
        f"⚙️ <b>TRUNG TÂM ĐIỀU KHIỂN (ADMIN)</b>\n"
        f"➖➖➖➖➖➖➖➖➖➖\n"
        f"🏦 Số dư trên TrumSMM: <b>{admin_source_balance:,} đ</b>\n"
        f"📈 Tỷ lệ giá chênh lệch: <b>{markup}%</b>\n\n"
        f"Chọn chức năng:"
    )
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="💸 Cộng tiền cho Khách", callback_data="admin_add_money"))
    builder.row(InlineKeyboardButton(text="📈 Chỉnh tỷ lệ lãi (%)", callback_data="admin_set_markup"))
    builder.row(InlineKeyboardButton(text="⬅️ Trở về User", callback_data="menu_main"))
    
    await call.message.edit_text(text, reply_markup=builder.as_markup())

@dp.callback_query(F.data == "admin_set_markup")
async def set_markup_start(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("Nhập số phần trăm lãi bạn muốn ăn (VD: nhập 20 là ăn chênh 20%):")
    await state.set_state(AdminStates.waiting_for_markup)

@dp.message(AdminStates.waiting_for_markup)
async def set_markup_finish(message: Message, state: FSMContext):
    try:
        percent = int(message.text)
        await db.set_markup(percent)
        await message.answer(f"✅ Đã cấu hình giá bán ra: <b>Giá gốc + {percent}%</b>")
        await state.clear()
    except ValueError:
        await message.answer("❌ Vui lòng nhập một số nguyên hợp lệ.")

@dp.callback_query(F.data == "admin_add_money")
async def add_money_start(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("👤 Nhập UserID của khách hàng:")
    await state.set_state(AdminStates.waiting_for_user_id)

@dp.message(AdminStates.waiting_for_user_id)
async def add_money_step2(message: Message, state: FSMContext):
    await state.update_data(target_user=message.text)
    await message.answer("💰 Nhập số tiền muốn cộng (Nhập số âm để trừ):")
    await state.set_state(AdminStates.waiting_for_amount)

@dp.message(AdminStates.waiting_for_amount)
async def add_money_finish(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        user_id = int(data['target_user'])
        amount = int(message.text)
        
        new_balance = await db.update_balance(user_id, amount)
        await message.answer(f"✅ Đã cộng <b>{amount:,}đ</b> cho User <code>{user_id}</code>.\nSố dư mới: <b>{new_balance:,}đ</b>")
        
        # Gửi thông báo cho khách
        try:
            await bot.send_message(user_id, f"🎉 Admin đã cộng <b>{amount:,}đ</b> vào tài khoản của bạn!")
        except Exception:
            pass # Bỏ qua nếu user đã block bot
            
        await state.clear()
    except Exception as e:
        await message.answer(f"❌ Lỗi: {str(e)}")
        await state.clear()

# --- KHỞI CHẠY HỆ THỐNG TRÊN RENDER ---
async def start_telegram_bot():
    print("Bot Reseller đang khởi động...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

@app.on_event("startup")
async def on_startup():
    asyncio.create_task(start_telegram_bot())

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=config.PORT, log_level="info")
                                                   
