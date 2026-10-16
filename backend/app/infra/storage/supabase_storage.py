import io
import uuid
from pathlib import Path
from typing import BinaryIO, Tuple
from supabase import create_client, Client
from app.domain.interfaces.file_storage import IFileStorage


class SupabaseFileStorage(IFileStorage):
    """Lưu trữ tệp lên Supabase Storage qua Supabase Python Client."""

    def __init__(self, supabase_url: str, supabase_key: str, bucket_name: str = "teamchat-files"):
        self.client: Client = create_client(supabase_url, supabase_key)
        self.bucket_name = bucket_name

    def save(self, file_obj: BinaryIO, original_filename: str) -> Tuple[str, int]:
        suffix = Path(original_filename).suffix[:20]
        stored_name = f"{uuid.uuid4().hex}{suffix}"

        # Đọc dữ liệu nhị phân từ file stream
        file_obj.seek(0)
        file_bytes = file_obj.read()
        file_size = len(file_bytes)

        # Upload dữ liệu lên Supabase Storage
        self.client.storage.from_(self.bucket_name).upload(
            path=stored_name,
            file=file_bytes,
            file_options={"cache-control": "3600", "upsert": "false"},
        )

        return stored_name, file_size

    def open_stream(self, stored_name: str) -> BinaryIO:
        # Tải file từ Supabase về dạng bytes và bọc vào BytesIO stream để đọc
        data = self.client.storage.from_(self.bucket_name).download(stored_name)
        return io.BytesIO(data)


    def exists(self, stored_name: str) -> bool:
        try:
            # list() lấy danh sách tệp tại thư mục gốc của bucket
            res = self.client.storage.from_(self.bucket_name).list(
                path="",
                options={"search": stored_name}
            )
            return any(item.get("name") == stored_name for item in res)
        except Exception:
            return False

    def delete(self, stored_name: str) -> bool:
        try:
            res = self.client.storage.from_(self.bucket_name).remove([stored_name])
            # res trả về danh sách các object đã xóa thành công
            return len(res) > 0
        except Exception:
            return False