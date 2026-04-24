import aiohttp
import logging

class TrumSmmAPI:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "http://api.trumsmm.com/api"
        # Lưu ý: Trong ảnh API dùng HTTP, nếu bên đó có HTTPS thì sếp đổi thành https nhé

    async def _post(self, endpoint: str, payload: dict = None):
        """Hàm dùng chung để gọi POST request"""
        if payload is None:
            payload = {}
        payload["api_key"] = self.api_key
        
        url = f"{self.base_url}/{endpoint}"
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, json=payload, timeout=15) as response:
                    # Trả về JSON từ API
                    return await response.json()
            except Exception as e:
                logging.error(f"Lỗi gọi API {endpoint}: {e}")
                return {"success": False, "message": str(e)}

    async def get_balance(self):
        """Lấy số dư tài khoản trên web nguồn"""
        return await self._post("balance")

    async def get_services(self):
        """Lấy danh sách chuyên mục và sản phẩm (tự động cập nhật Stock)"""
        return await self._post("services")

    async def buy_product(self, product_id: int, quantity: int = 1):
        """Mua tài nguyên"""
        payload = {
            "product_id": product_id,
            "quantity": quantity
        }
        return await self._post("buy", payload)

    async def download_file(self, file_url: str):
        """Tải file txt tài khoản sau khi mua thành công"""
        async with aiohttp.ClientSession() as session:
            async with session.get(file_url) as response:
                if response.status == 200:
                    return await response.text()
                return None
              
