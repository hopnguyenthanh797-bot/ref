import aiohttp
import logging
from config import config

class TrumSmmAPI:
    def __init__(self):
        self.api_key = config.TRUMSMM_API_KEY
        self.base_url = config.TRUMSMM_URL

    async def _post(self, endpoint: str, payload: dict = None):
        if payload is None:
            payload = {}
        payload["api_key"] = self.api_key
        url = f"{self.base_url}/{endpoint}"
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, json=payload, timeout=15) as response:
                    return await response.json()
            except Exception as e:
                logging.error(f"API Error ({endpoint}): {e}")
                return {"success": False, "message": str(e)}

    async def get_balance(self):
        return await self._post("balance")

    async def get_services(self):
        # Hàm này sẽ được gọi mỗi khi khách xem sản phẩm -> Đảm bảo stock chuẩn 100%
        return await self._post("services")

    async def buy_product(self, product_id: int, quantity: int = 1):
        payload = {"product_id": product_id, "quantity": quantity}
        return await self._post("buy", payload)

    async def download_file(self, file_url: str):
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(file_url, timeout=10) as response:
                    if response.status == 200:
                        return await response.text()
            except Exception as e:
                logging.error(f"Download Error: {e}")
        return None

trum_api = TrumSmmAPI()
