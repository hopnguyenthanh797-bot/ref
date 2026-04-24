import asyncio
import re
import math
from datetime import datetime
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

# --- CẤU HÌNH PHÂN TRANG ---
ITEMS_PER_PAGE = 8  # Số sản phẩm hiển thị trên 1 trang (giống video)

# --- FSM CHO ADMIN ---
class AdminStates(StatesGroup):
    waiting_for_user_id = State()
    waiting_for_amount = State()
    waiting_for_markup = State()
    waiting_for_guide = State()
    waiting_for_bank = State()

# --- HELPER: TÍNH TOÁN VIP ---
def get_vip_info(total_deposit: int):
    tiers = [
        (0, "Member", 0, 500000),
        (500000, "VIP 1", 5, 2000000),
        (2000000, "VIP 2", 10, 10000000),
        (10000000, "VIP 3", 15, 50000000)
    ]
    current_tier = tiers[0]
    for tier in tiers:
        if total_deposit >= tier[0]:
            current_tier = tier
    
    rank_name = current_tier[1]
    discount = current_tier[2]
    next_target = current_tier[3]
    
    if total_deposit >= tiers[-1][3]:
        progress = 100
        bar = "██████████"
        remain = 0
    else:
        progress = int((total_deposit / next_target) * 100)
        filled = int(progress / 10)
        bar = "█" * filled + "▒" * (10 - filled)
        remain = next_target - total_deposit
        
    return rank_name, discount, progress, bar, remain

# ==========================================
# GIAO DIỆN CHÍNH & CÁ NHÂN
# ==========================================
async def get_main_menu_markup():
    settings = await db.get_settings()
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🛍 Sản phẩm", callback_data="menu_categories"),
        InlineKeyboardButton(text="🏦 Nạp tiền", callback_data="menu_deposit")
    )
    builder.row(
        InlineKeyboardButton(text="📚 Hướng Dẫn", url=settings['guide_link']),
        InlineKeyboardButton(text="📸 Cá Nhân", callback_data="menu_profile")
    )
    builder.row(
        InlineKeyboardButton(text="🌐 Ngôn ngữ", callback_data="ignore_btn"),
        InlineKeyboardButton(text="⚠️ Điều khoản", callback_data="ignore_btn")
    )
    if config.ADMIN_IDS:
        builder.row(InlineKeyboardButton(text="⚙️ Admin Panel", callback_data="admin_panel"))
    return builder.as_markup()

@dp.message(Command("start"))
async def start_cmd(message: Message, state: FSMContext):
    await state.clear()
    user = await db.get_user(message.from_user.id, message.from_user.full_name)
    text = (
        f"👋 <b>Chào mừng {message.from_user.full_name} đến với Shop Telegram!</b>\n\n"
        f"UserID: <code>{user['user_id']}</code> gửi khi Nạp Tiền\n"
        f"---------------------\n"
        f"💰 Số Dư: <b>{user['balance']:,} đ</b>\n"
        f"---------------------\n"
        f"⚠️ Vui lòng xem hướng dẫn trước khi mua hàng!"
    )
    markup = await get_main_menu_markup()
    await message.answer(text, reply_markup=markup)

@dp.callback_query(F.data == "menu_main")
async def back_main(call: CallbackQuery, state: FSMContext):
    await call.answer() # Khử lỗi treo
    await state.clear()
    user = await db.get_user(call.from_user.id, call.from_user.full_name)
    text = (
        f"👋 <b>Chào mừng {call.from_user.full_name} đến với Shop Telegram!</b>\n\n"
        f"UserID: <code>{user['user_id']}</code> gửi khi Nạp Tiền\n"
        f"---------------------\n"
        f"💰 Số Dư: <b>{user['balance']:,} đ</b>\n"
        f"---------------------\n"
        f"⚠️ Vui lòng xem hướng dẫn trước khi mua hàng!"
    )
    markup = await get_main_menu_markup()
    await call.message.edit_text(text, reply_markup=markup)

@dp.callback_query(F.data == "menu_profile")
async def show_profile(call: CallbackQuery):
    await call.answer() # Khử lỗi treo
    user = await db.get_user(call.from_user.id, call.from_user.full_name)
    rank, discount, progress, bar, remain = get_vip_info(user['total_deposit'])
    
    try:
        reg_date = datetime.fromisoformat(user['created_at'].replace("Z", "+00:00"))
        days_diff = (datetime.now(reg_date.tzinfo) - reg_date).days
        date_str = reg_date.strftime("%d.%m.%Y")
    except:
        date_str, days_diff = "N/A", 0

    items_bought = user['total_spent'] // 5000 if user['total_spent'] > 0 else 0

    text = (
        f"📌 <b>Thông tin tài khoản</b>\n\n"
        f"🆔 <b>ID:</b> <code>{user['user_id']}</code>\n"
        f"📌 <b>Tên:</b> {user['full_name']}\n\n"
        f"💰 Số dư: <b>{user['balance']:,} đ</b>\n"
        f"🎯 Cấp bậc: <b>{rank}</b>\n"
        f"🎁 Giảm giá: <b>{discount}%</b>\n"
        f"💵 Tổng nạp: <b>{user['total_deposit']:,} đ</b>\n\n"
        f"📊 <b>Tiến độ lên VIP</b> 🏆\n"
        f"{bar} <b>{progress}%</b>\n"
        f"💠 Còn <b>{remain:,} đ</b> để lên cấp\n\n"
        f"🛍 Sản phẩm đã mua: <b>{items_bought}</b>\n"
        f"💸 Tổng chi: <b>{user['total_spent']:,} đ</b>\n\n"
        f"📅 Ngày đăng ký: <b>{date_str} ({days_diff} day)</b>"
    )
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🏦 Nạp tiền", callback_data="menu_deposit"),
        InlineKeyboardButton(text="🎉 LS Mua hàng", callback_data="menu_history")
    )
    builder.row(
        InlineKeyboardButton(text="🔒 Xem mã bảo mật", callback_data="ignore_btn"),
        InlineKeyboardButton(text="🔄 Đổi mã bảo mật", callback_data="ignore_btn")
    )
    builder.row(InlineKeyboardButton(text="🔓 Khôi phục tài khoản", callback_data="ignore_btn"))
    builder.row(InlineKeyboardButton(text="⬅️ Quay lại", callback_data="menu_main"))
    
    await call.message.edit_text(text, reply_markup=builder.as_markup())

# ==========================================
# PHÂN LOẠI & PHÂN TRANG (PAGINATION)
# ==========================================
@dp.callback_query(F.data == "menu_categories")
async def show_categories(call: CallbackQuery):
    await call.answer("Đang tải danh mục...", show_alert=False)
    
    res = await trum_api.get_services()
    if not res.get("success"):
        return await call.message.edit_text("❌ Lỗi kết nối nguồn.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Quay lại", callback_data="menu_main")]]))
    
    builder = InlineKeyboardBuilder()
    for cat in res.get("data", []):
        cat_id = cat.get("category_id")
        cat_name = cat.get("category_name")
        total_stock = sum([p.get("stock", 0) for p in cat.get("positions", [])])
        
        if total_stock > 0:
            builder.row(InlineKeyboardButton(text=f"📁 {cat_name} | (Stock: {total_stock})", callback_data=f"showcat_{cat_id}_1"))
            
    builder.row(InlineKeyboardButton(text="⬅️ Quay lại", callback_data="menu_main"))
    await call.message.edit_text("🛍 <b>Chọn Danh Mục Sản Phẩm:</b>", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("showcat_"))
async def show_products_in_cat(call: CallbackQuery):
    await call.answer() # Khử lỗi treo
    
    # Data có dạng: showcat_123_1 (trong đó 123 là cat_id, 1 là page)
    parts = call.data.split("_")
    cat_id = int(parts[1])
    page = int(parts[2])
    
    res = await trum_api.get_services()
    settings = await db.get_settings()
    markup_pct = settings['markup_percent']
    
    cat_name_display = "Sản Phẩm"
    active_products = []
    
    # Tìm danh mục và lọc các sản phẩm còn hàng
    for cat in res.get("data", []):
        if cat.get("category_id") == cat_id:
            cat_name_display = cat.get("category_name")
            for pos in cat.get("positions", []):
                if pos.get("stock") > 0:
                    active_products.append(pos)
            break

    # Tính toán phân trang
    total_items = len(active_products)
    total_pages = math.ceil(total_items / ITEMS_PER_PAGE)
    if total_pages == 0: total_pages = 1
    if page > total_pages: page = total_pages
    if page < 1: page = 1

    start_idx = (page - 1) * ITEMS_PER_PAGE
    end_idx = start_idx + ITEMS_PER_PAGE
    current_page_products = active_products[start_idx:end_idx]

    builder = InlineKeyboardBuilder()
    
    # Hiển thị sản phẩm của trang hiện tại
    for pos in current_page_products:
        pos_id = pos.get("position_id")
        pos_name = pos.get("position_name")
        stock = pos.get("stock")
        original_price = pos.get("price")
        sell_price = int(original_price + (original_price * markup_pct / 100))
        
        btn_text = f"{pos_name} | {sell_price:,}đ | [{stock}]"
        builder.row(InlineKeyboardButton(text=btn_text, callback_data=f"buy_{pos_id}_{sell_price}"))
    
    # Xây dựng thanh điều hướng phân trang (Giống hệt video sếp gửi)
    nav_row = []
    if total_pages > 1:
        if page > 1:
            nav_row.append(InlineKeyboardButton(text="⬅️", callback_data=f"showcat_{cat_id}_{page-1}"))
        else:
            nav_row.append(InlineKeyboardButton(text="➖", callback_data="ignore_btn"))
            
        nav_row.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="ignore_btn"))
        
        if page < total_pages:
            nav_row.append(InlineKeyboardButton(text="➡️", callback_data=f"showcat_{cat_id}_{page+1}"))
        else:
            nav_row.append(InlineKeyboardButton(text="➖", callback_data="ignore_btn"))
            
        builder.row(*nav_row)

    builder.row(InlineKeyboardButton(text="⬅️ Quay lại Danh Mục", callback_data="menu_categories"))
    
    text = f"🛍 <b>Danh mục: {cat_name_display}</b>\n<i>Chọn sản phẩm:</i>"
    await call.message.edit_text(text, reply_markup=builder.as_markup())

# ==========================================
# MUA HÀNG & LỊCH SỬ
# ==========================================
@dp.callback_query(F.data.startswith("buy_"))
async def process_buy(call: CallbackQuery):
    # Khử lỗi treo & Báo cho người dùng biết bot đang xử lý
    await call.answer("⏳ Đang xử lý giao dịch...", show_alert=False) 
    
    _, pos_id, sell_price = call.data.split("_")
    sell_price = int(sell_price)
    pos_id = int(pos_id)
    
    user = await db.get_user(call.from_user.id, call.from_user.full_name)
    
    # Xử lý Discount từ VIP
    rank, discount, _, _, _ = get_vip_info(user['total_deposit'])
    final_price = int(sell_price - (sell_price * discount / 100))
    
    if user['balance'] < final_price:
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="💳 Nạp Tiền Ngay", callback_data="menu_deposit"))
        builder.row(InlineKeyboardButton(text="⬅️ Quay lại", callback_data="menu_categories"))
        return await call.message.edit_text(f"❌ <b>Số dư không đủ!</b>\nGiá sản phẩm: {final_price:,}đ\nSố dư của bạn: {user['balance']:,}đ", reply_markup=builder.as_markup())
    
    buy_res = await trum_api.buy_product(product_id=pos_id, quantity=1)
    
    if buy_res.get("success"):
        await db.update_balance(user['user_id'], -final_price)
        
        links = buy_res.get("download", [])
        if links:
            file_url = links[0]
            file_content = await trum_api.download_file(file_url)
            
            await db.add_order(user['user_id'], f"Product ID: {pos_id}", final_price, file_content if file_content else file_url)
            
            if file_content:
                parts = file_content.strip().split("|")
                phone = parts[0] if len(parts) > 0 else "N/A"
                two_fa = parts[1] if len(parts) > 1 else "Không"
                
                text = (
                    f"✅ <b>Giao dịch thành công!</b>\n"
                    f"💸 Đã thanh toán: <b>{final_price:,}đ</b>\n\n"
                    f"📱 <b>Phone:</b> <code>{phone}</code>\n"
                    f"🔐 <b>2FA:</b> <code>{two_fa}</code>\n\n"
                    f"<i>Vui lòng tải file bên dưới để xem toàn bộ Session.</i>"
                )
                builder = InlineKeyboardBuilder()
                builder.row(InlineKeyboardButton(text="📥 Tải File Session", url=file_url))
                builder.row(InlineKeyboardButton(text="⬅️ Về Trang Chủ", callback_data="menu_main"))
                await call.message.edit_text(text, reply_markup=builder.as_markup())
            else:
                await call.message.edit_text(f"✅ Đã mua thành công. Tải tài nguyên:\n{file_url}")
    else:
        text = f"❌ <b>Thất bại từ nguồn:</b>\n{buy_res.get('message')}\n<i>Tiền chưa bị trừ.</i>"
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="⬅️ Thử lại", callback_data="menu_categories"))
        await call.message.edit_text(text, reply_markup=builder.as_markup())

@dp.callback_query(F.data == "menu_history")
async def show_history(call: CallbackQuery):
    await call.answer()
    orders = await db.get_history(call.from_user.id)
    if not orders:
        text = "Chưa có giao dịch nào gần đây."
    else:
        text = "🕒 <b>Lịch sử mua hàng (5 đơn gần nhất):</b>\n\n"
        for od in orders:
            dt = datetime.fromisoformat(od['created_at'].replace("Z", "+00:00")).strftime("%d/%m %H:%M")
            text += f"📦 <b>{od['product_name']}</b> - {od['price']:,}đ\n"
            text += f"🗓 {dt}\n"
            short_data = od['resource_data'][:40] + "..." if len(od['resource_data']) > 40 else od['resource_data']
            text += f"🔑 <code>{short_data}</code>\n➖➖➖➖➖➖\n"

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⬅️ Quay lại", callback_data="menu_profile"))
    await call.message.edit_text(text, reply_markup=builder.as_markup())

# ==========================================
# NẠP TIỀN & SEPAY WEBHOOK
# ==========================================
@dp.callback_query(F.data == "menu_deposit")
async def show_deposit(call: CallbackQuery):
    await call.answer()
    settings = await db.get_settings()
    user_id = call.from_user.id
    
    text = (
        f"🏦 <b>HỆ THỐNG NẠP TIỀN TỰ ĐỘNG</b>\n\n"
        f"Vui lòng chuyển khoản chính xác nội dung bên dưới, hệ thống sẽ cộng tiền trong 1-3 phút.\n\n"
        f"💳 Thông tin Bank: <b>{settings['bank_info']}</b>\n"
        f"📝 Nội dung CK: <code>NAP {user_id}</code>\n\n"
        f"<i>(Chạm vào nội dung để copy)</i>"
    )
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⬅️ Quay lại", callback_data="menu_main"))
    await call.message.edit_text(text, reply_markup=builder.as_markup())

@app.post("/sepay-webhook")
async def sepay_webhook(request: Request):
    try:
        data = await request.json()
        amount = int(data.get("transferAmount", 0))
        content = data.get("content", "").upper()
        
        match = re.search(r'NAP\s*(\d+)', content)
        if match and amount > 0:
            user_id = int(match.group(1))
            new_balance = await db.update_balance(user_id, amount, is_deposit=True)
            try:
                await bot.send_message(
                    chat_id=user_id, 
                    text=f"🎉 <b>NẠP TIỀN THÀNH CÔNG!</b>\n\nBạn vừa được cộng <b>{amount:,}đ</b> vào tài khoản.\nSố dư hiện tại: <b>{new_balance:,}đ</b>"
                )
            except Exception:
                pass
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

# ==========================================
# ADMIN PANEL
# ==========================================
@dp.callback_query(F.data == "admin_panel")
async def admin_menu(call: CallbackQuery):
    if call.from_user.id not in config.ADMIN_IDS:
        return await call.answer("❌ Cấm!", show_alert=True)
    
    await call.answer("Đang lấy thông tin nguồn...", show_alert=False)
    balance_res = await trum_api.get_balance()
    admin_balance = balance_res.get("balance", 0) if balance_res.get("success") else "Lỗi API"
    settings = await db.get_settings()
    
    text = (
        f"⚙️ <b>ADMIN PANEL</b>\n"
        f"🏦 Nguồn TrumSMM: <b>{admin_balance:,} đ</b>\n"
        f"📈 Lãi: <b>{settings['markup_percent']}%</b>\n"
        f"📚 Link Hướng dẫn: {settings['guide_link']}\n"
        f"💳 Bank: {settings['bank_info']}"
    )
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="💸 Cộng tiền", callback_data="admin_add_money"), InlineKeyboardButton(text="📈 Chỉnh Lãi", callback_data="admin_set_markup"))
    builder.row(InlineKeyboardButton(text="📚 Sửa Link Hướng Dẫn", callback_data="admin_set_guide"))
    builder.row(InlineKeyboardButton(text="💳 Sửa Ngân Hàng", callback_data="admin_set_bank"))
    builder.row(InlineKeyboardButton(text="⬅️ Trở về User", callback_data="menu_main"))
    
    await call.message.edit_text(text, reply_markup=builder.as_markup())

@dp.callback_query(F.data == "admin_set_guide")
async def set_guide(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.edit_text("Nhập link bài Hướng dẫn mới (VD: https://t.me/post):")
    await state.set_state(AdminStates.waiting_for_guide)

@dp.message(AdminStates.waiting_for_guide)
async def finish_guide(message: Message, state: FSMContext):
    await db.update_setting("guide_link", message.text)
    await message.answer("✅ Đã cập nhật Link Hướng dẫn!")
    await state.clear()

@dp.callback_query(F.data == "admin_set_bank")
async def set_bank(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.edit_text("Nhập thông tin Ngân hàng mới (VD: MSB | 123456 | ADMIN):")
    await state.set_state(AdminStates.waiting_for_bank)

@dp.message(AdminStates.waiting_for_bank)
async def finish_bank(message: Message, state: FSMContext):
    await db.update_setting("bank_info", message.text)
    await message.answer("✅ Đã cập nhật STK Ngân hàng!")
    await state.clear()

@dp.callback_query(F.data == "admin_set_markup")
async def set_markup(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.edit_text("Nhập % lãi mới:")
    await state.set_state(AdminStates.waiting_for_markup)

@dp.message(AdminStates.waiting_for_markup)
async def finish_markup(message: Message, state: FSMContext):
    await db.update_setting("markup_percent", int(message.text))
    await message.answer("✅ Đã cập nhật lãi suất!")
    await state.clear()

@dp.callback_query(F.data == "admin_add_money")
async def add_money(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.edit_text("Nhập UserID:")
    await state.set_state(AdminStates.waiting_for_user_id)

@dp.message(AdminStates.waiting_for_user_id)
async def add_money_step2(message: Message, state: FSMContext):
    await state.update_data(target_user=message.text)
    await message.answer("Nhập số tiền:")
    await state.set_state(AdminStates.waiting_for_amount)

@dp.message(AdminStates.waiting_for_amount)
async def finish_add_money(message: Message, state: FSMContext):
    data = await state.get_data()
    user_id = int(data['target_user'])
    amount = int(message.text)
    new_bal = await db.update_balance(user_id, amount, is_deposit=True)
    await message.answer(f"✅ Đã cộng {amount:,}đ. Số dư mới: {new_bal:,}đ")
    try:
        await bot.send_message(user_id, f"🎉 Admin đã cộng {amount:,}đ vào tài khoản!")
    except:
        pass
    await state.clear()

# Bắt các nút chưa có chức năng (Chống lỗi treo)
@dp.callback_query(F.data == "ignore_btn")
async def ignore_callback(call: CallbackQuery):
    await call.answer("Chức năng đang phát triển!", show_alert=False)

# ==========================================
# KHỞI CHẠY RENDER
# ==========================================
async def start_telegram_bot():
    print("🚀 Bot Reseller VIP đang khởi động...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

@app.on_event("startup")
async def on_startup():
    asyncio.create_task(start_telegram_bot())

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=config.PORT, log_level="info")
