from abc import ABC, abstractmethod
from typing import Any, Dict, Iterable, Optional


class ICache(ABC):
    """Cổng bộ nhớ đệm key-value có thời hạn.

    Tầng trên chỉ biết interface này, không biết dữ liệu nằm trong RAM của tiến
    trình hay trên Redis. Chạy một worker thì dùng bản trong bộ nhớ; chạy nhiều
    worker thì thay bằng bản Redis mà không sửa nơi dùng.
    """

    @abstractmethod
    def get(self, key: str) -> Optional[Any]:
        """Giá trị còn hạn, hoặc None."""
        pass

    @abstractmethod
    def get_many(self, keys: Iterable[str]) -> Dict[str, Any]:
        """Chỉ trả về những key có và còn hạn."""
        pass

    @abstractmethod
    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        pass

    @abstractmethod
    def delete(self, *keys: str) -> None:
        pass

    @abstractmethod
    def delete_prefix(self, prefix: str) -> None:
        """Xóa mọi key bắt đầu bằng prefix, dùng khi không biết chính xác key nào bị ảnh hưởng."""
        pass
