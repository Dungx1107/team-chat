from abc import ABC, abstractmethod
from typing import Any, Dict

class IEventPublisher(ABC):
    """Cổng phát sự kiện realtime ra ngoài.

    Tầng nghiệp vụ chỉ biết tới interface này, hoàn toàn không biết
    bên dưới là WebSocket, Redis Pub/Sub hay message queue nào.
    Nhờ vậy tầng Service vẫn không phụ thuộc framework (Dependency Inversion),
    và ở Pha 2 có thể thay WebSocket bằng Redis mà không sửa một dòng nghiệp vụ nào.
    """

    @abstractmethod
    def publish_to_room(self, room_id: int, event: str, payload: Dict[str, Any]) -> None:
        pass

    @abstractmethod
    def publish_to_user(self, user_id: int, event: str, payload: Dict[str, Any]) -> None:
        pass


class NullEventPublisher(IEventPublisher):
    """Bản cài đặt rỗng, dùng khi chạy unit test tầng Service."""

    def publish_to_room(self, room_id: int, event: str, payload: Dict[str, Any]) -> None:
        return None

    def publish_to_user(self, user_id: int, event: str, payload: Dict[str, Any]) -> None:
        return None
