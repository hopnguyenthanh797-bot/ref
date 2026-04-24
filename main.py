import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from trumsmm_api import TrumSmmAPI

BOT_TOKEN = "8743099227:AAGXQH4f9SUndwnCjahZ9b_Tsa-yQUGOq4g"
# Thay API Key sếp copy từ web vào đây
TRUM_API_KEY = "751f5288302b02735a318e2cedf4689e" 

bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
dp = Dispatcher()
api_client = TrumSmmAPI(TRUM_API_KEY)

# --- XỬ LÝ NÚT SẢN PHẨM ---
@dp.callback_query(F.data == "menu_products")
async def show_products(call: CallbackQuery):
    await call.message.edit_text("🔄 Đang tải dữ liệu kho từ hệ thống...")
    
    # Gọi API lấy dịch vụ
    res = await api_client.get_services()
    
    if not res.get("success"):
        return await call.message.edit_text("❌ Lỗi kết nối đến kho hàng. Vui lòng thử lại sau.")
    
    builder = InlineKeyboardBuilder()
    
    # Duyệt qua data JSON từ API để tạo nút bấm
    for category in res.get("data", []):
        cat_name = category.get("category_name")
        for pos in category.get("positions", []):
            pos_id = pos.get("position_id")
            pos_name = pos.get("position_name")
            stock = pos.get("stock")
            price = pos.get("price") # Sếp có thể tự x2 x3 giá này lên để ăn chênh lệch
            
            # Chỉ hiển thị nếu còn hàng
            if stock > 0:
                btn_text = f"📦 {pos_name} | Giá: {price}đ | (Stock: {stock})"
                builder.row(InlineKeyboardButton(text=btn_text, callback_data=f"buy_{pos_id}_{price}"))
                
    builder.row(InlineKeyboardButton(text="⬅️ Quay lại", callback_data="menu_main"))
    
    await call.message.edit_text("🛍 <b>Chọn sản phẩm bạn muốn mua:</b>", reply_markup=builder.as_markup())

# --- XỬ LÝ MUA HÀNG ---
@dp.callback_query(F.data.startswith("buy_"))
async def process_buy(call: CallbackQuery):
    data_parts = call.data.split("_")
    product_id = int(data_parts[1])
    price = int(data_parts[2])
    
    # 1. TODO: Kiểm tra số dư của khách trên hệ thống (Database) của sếp
    # if user_balance < price: return báo lỗi
    
    await call.message.edit_text("⏳ Đang xử lý giao dịch. Vui lòng chờ...")
    
    # 2. Gọi API mua hàng sang hệ thống nguồn
    buy_res = await api_client.buy_product(product_id=product_id, quantity=1)
    
    if buy_res.get("success"):
        # Trừ tiền khách trên DB của sếp ở đây
        
        # API trả về list link download: ["http://api.../download/API_123.txt"]
        download_links = buy_res.get("download", [])
        if download_links:
            file_url = download_links[0]
            
            # Tải nội dung file txt về
            file_content = await api_client.download_file(file_url)
            
            if file_content:
                # Xử lý nội dung file (Ví dụ format nguồn trả về là SĐT|2FA|Session...)
                # Sếp cần tùy biến đoạn này dựa theo định dạng thực tế file tải về
                try:
                    parts = file_content.strip().split("|")
                    phone = parts[0] if len(parts) > 0 else "N/A"
                    two_fa = parts[1] if len(parts) > 1 else "Không có"
                except:
                    phone, two_fa = "Lỗi định dạng", ""

                # Xuất ra giao diện đẹp y hệt ảnh 3 của sếp
                text = (
                    f"✅ <b>Giao dịch thành công!</b>\n\n"
                    f"<b>Session Info</b>\n"
                    f"📱 <b>Phone :</b> <code>{phone}</code>\n"
                    f"🔐 <b>2FA :</b> <code>{two_fa}</code>\n\n"
                    f"⬇️ <b>Bấm nút dưới để nhận tài nguyên/OTP</b>"
                )
                
                builder = InlineKeyboardBuilder()
                builder.row(InlineKeyboardButton(text="✅ Check (Lấy mã)", callback_data=f"check_otp_{product_id}"))
                builder.row(InlineKeyboardButton(text="Tải file Session gốc", url=file_url))
                
                await call.message.edit_text(text, reply_markup=builder.as_markup())
            else:
                await call.message.edit_text("✅ Đã mua nhưng không tải được nội dung tài khoản.")
    else:
        # Lỗi từ web nguồn (vd: Out of stock, Not enough balance trên tài khoản admin của sếp)
        error_msg = buy_res.get("message", "Lỗi không xác định")
        await call.message.edit_text(f"❌ <b>Giao dịch thất bại!</b>\nLý do từ nguồn: {error_msg}\n(Tiền của bạn chưa bị trừ)", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Quay lại", callback_data="menu_products")]]))

async def main():
    print("Bot Reseller đang chạy...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
            
