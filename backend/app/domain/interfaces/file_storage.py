from abc import ABC, abstractmethod
from typing import BinaryIO, Tuple

class IFileStorage(ABC):
    """Cổng lưu trữ tệp.

    Tầng nghiệp vụ không biết tệp nằm trên đĩa, trên MinIO hay trên S3.
    Muốn đổi sang MinIO ở Pha 2 chỉ cần viết một lớp cài đặt mới.
    """

    @abstractmethod
    def save(self, file_obj: BinaryIO, original_filename: str) -> Tuple[str, int]:
        """Lưu tệp, trả về (tên_đã_lưu, dung_lượng_byte)."""
        pass

    @abstractmethod
    def open_stream(self, stored_name: str) -> BinaryIO:
        pass

    @abstractmethod
    def exists(self, stored_name: str) -> bool:
        pass

    @abstractmethod
    def delete(self, stored_name: str) -> bool:
        pass
