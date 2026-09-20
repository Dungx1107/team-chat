"""Nạp dữ liệu mẫu đủ để demo mọi tính năng.

Điểm quan trọng: script đi qua tầng Service thay vì ghi thẳng bằng ORM,
nhờ vậy các luật nghiệp vụ (chủ phòng phải là OWNER trong bảng thành viên)
được áp dụng đúng như khi người dùng thao tác thật.
"""

from app.infra.db.session import SessionLocal, engine, Base
import app.infra.db.models  # noqa: F401
from app.infra.db.models import UserModel

from app.repositories.user_repo import UserRepository
from app.repositories.refresh_token_repo import RefreshTokenRepository
from app.repositories.room_repo import RoomRepository
from app.repositories.message_repo import MessageRepository

from app.services.auth_service import AuthService
from app.services.room_service import RoomService
from app.services.message_service import MessageService
from app.domain.models import RoomMember

PASSWORD = "password123"

TEST_USERS = [
    {"email": "user1@example.com", "username": "dungx", "first_name": "Xuân Dũng", "last_name": "Nguyễn",
     "bio": "Trưởng nhóm kiến trúc phần mềm.", "status": "Đang làm đồ án"},
    {"email": "user2@example.com", "username": "namtv", "first_name": "Văn Nam", "last_name": "Trần",
     "bio": "Phụ trách backend và cơ sở dữ liệu.", "status": "Rảnh"},
    {"email": "user3@example.com", "username": "anhlh", "first_name": "Hoàng Anh", "last_name": "Lê",
     "bio": "Phụ trách giao diện người dùng.", "status": "Bận họp"},
    {"email": "user4@example.com", "username": "maipt", "first_name": "Phương Mai", "last_name": "Phạm",
     "bio": "Kiểm thử và tài liệu.", "status": None},
]


def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        user_repo = UserRepository(db)
        auth_service = AuthService(user_repo, RefreshTokenRepository(db))
        room_service = RoomService(room_repo=RoomRepository(db), user_repo=user_repo)
        message_service = MessageService(
            message_repo=MessageRepository(db),
            room_repo=RoomRepository(db),
        )

        print("--> Đang khởi tạo dữ liệu mẫu...")

        # 1. Người dùng
        users = {}
        for u in TEST_USERS:
            existing = user_repo.get_by_email(u["email"])
            if existing:
                users[u["username"]] = existing
                print(f" [=] Đã có sẵn: {u['email']}")
                continue

            created = auth_service.register(
                email=u["email"],
                username=u["username"],
                password=PASSWORD,
                first_name=u["first_name"],
                last_name=u["last_name"],
            )
            # Bổ sung phần hồ sơ mà luồng đăng ký chưa nhận
            created.bio = u["bio"]
            created.status = u["status"]
            created = user_repo.update(created)
            users[u["username"]] = created
            print(f" [+] Đã tạo: {u['email']} | username: {u['username']}")

        dungx = users["dungx"]
        namtv = users["namtv"]
        anhlh = users["anhlh"]
        maipt = users["maipt"]

        # 2. Phòng công khai -- ai cũng vào được
        if db.query(UserModel).count() and not RoomRepository(db).list_all(limit=1):
            pass

        existing_rooms = {r.name: r for r in RoomRepository(db).list_visible_to_user(dungx.id, limit=100)}

        if "Phòng Kiến Trúc" not in existing_rooms:
            public_room = room_service.create_room(
                name="Phòng Kiến Trúc",
                owner_id=dungx.id,
                description="Thảo luận chung về môn Kiến trúc phần mềm",
                is_private=False,
            )
            print(f" [+] Phòng công khai: # {public_room.name}")

            # Nam là quản trị viên, Hoàng Anh là thành viên thường
            room_service.add_member(public_room.id, dungx.id, namtv.id)
            room_service.change_member_role(public_room.id, dungx.id, namtv.id, RoomMember.ROLE_ADMIN)
            room_service.add_member(public_room.id, dungx.id, anhlh.id)
            print("     - namtv: ADMIN, anhlh: MEMBER")

            message_service.send_message(public_room.id, dungx.id, "Chào cả nhóm, ta bắt đầu pha 2 nhé.")
            message_service.send_message(public_room.id, namtv.id, "Mình đã xong phần đo hiệu năng trên Kaggle.")
            message_service.send_message(public_room.id, anhlh.id, "Giao diện mới mình đang làm, tối nay đẩy lên.")
        else:
            print(" [=] Đã có phòng công khai")

        # 3. Phòng riêng tư -- chỉ thành viên được mời mới thấy
        if "Nhóm Trưởng" not in existing_rooms:
            private_room = room_service.create_room(
                name="Nhóm Trưởng",
                owner_id=dungx.id,
                description="Trao đổi riêng giữa các trưởng nhóm",
                is_private=True,
            )
            room_service.add_member(private_room.id, dungx.id, namtv.id)
            message_service.send_message(private_room.id, dungx.id, "Phòng này chỉ hai đứa mình thấy thôi.")
            print(f" [+] Phòng riêng tư: # {private_room.name} (dungx + namtv)")
        else:
            print(" [=] Đã có phòng riêng tư")

        print("--> Hoàn tất nạp dữ liệu!")
        print()
        print("    Tài khoản đăng nhập (mật khẩu chung: password123):")
        for u in TEST_USERS:
            print(f"      {u['email']:<22} @{u['username']}")
        print()
        print(f"    maipt ({maipt.email}) cố tình chưa vào phòng nào,")
        print("    dùng để thử tính năng mời thành viên và phòng riêng tư.")

    finally:
        db.close()


if __name__ == "__main__":
    seed()
