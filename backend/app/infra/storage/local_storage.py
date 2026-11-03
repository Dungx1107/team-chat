import os
import shutil
import uuid
from pathlib import Path
from typing import BinaryIO, Tuple
from app.domain.interfaces import IFileStorage

class LocalFileStorage(IFileStorage):
    """Lưu tệp xuống thư mục gắn Docker volume.

    Tên tệp được thay bằng UUID để tránh trùng, tránh lộ tên gốc
    và chặn tấn công path traversal (ví dụ tên tệp dạng "../../etc/passwd").
    """

    def __init__(self, base_dir: str):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _safe_path(self, stored_name: str) -> Path:
        # Chỉ lấy phần tên, loại bỏ mọi thành phần thư mục do client gửi lên
        name = os.path.basename(stored_name)
        path = (self.base_dir / name).resolve()
        if not str(path).startswith(str(self.base_dir.resolve())):
            raise ValueError("Đường dẫn tệp không hợp lệ")
        return path

    def save(self, file_obj: BinaryIO, original_filename: str) -> Tuple[str, int]:
        suffix = Path(original_filename).suffix[:20]
        stored_name = f"{uuid.uuid4().hex}{suffix}"
        target = self._safe_path(stored_name)

        with open(target, "wb") as out:
            shutil.copyfileobj(file_obj, out, length=1024 * 1024)

        return stored_name, target.stat().st_size

    def open_stream(self, stored_name: str) -> BinaryIO:
        return open(self._safe_path(stored_name), "rb")

    def exists(self, stored_name: str) -> bool:
        try:
            return self._safe_path(stored_name).is_file()
        except ValueError:
            return False

    def delete(self, stored_name: str) -> bool:
        try:
            path = self._safe_path(stored_name)
        except ValueError:
            return False
        if path.is_file():
            path.unlink()
            return True
        return False
