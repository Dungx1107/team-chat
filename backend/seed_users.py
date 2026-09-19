import bcrypt
from app.infra.db.session import SessionLocal
from app.infra.db.models import UserModel, RoomModel

def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

def seed():
    db = SessionLocal()
    hashed_pwd = hash_password("password123")

    test_users = [
        {"email": "user1@example.com", "username": "dungx", "first_name": "Xuân Dũng", "last_name": "Nguyễn"},
        {"email": "user2@example.com", "username": "namtv", "first_name": "Văn Nam", "last_name": "Trần"},
        {"email": "user3@example.com", "username": "anhlh", "first_name": "Hoàng Anh", "last_name": "Lê"},
    ]

    print("--> Đang khởi tạo dữ liệu mẫu...")
    users = []
    for u in test_users:
        existing = db.query(UserModel).filter(UserModel.email == u["email"]).first()
        if not existing:
            user = UserModel(
                email=u["email"],
                username=u["username"],
                first_name=u["first_name"],
                last_name=u["last_name"],
                password_hash=hashed_pwd
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            users.append(user)
            print(f" [+] Đã tạo: {u['email']} | username: {u['username']}")
        else:
            # Cập nhật lại mật khẩu chuẩn nếu tài khoản đã tồn tại từ trước
            existing.password_hash = hashed_pwd
            db.commit()
            users.append(existing)
            print(f" [i] Đã cập nhật mật khẩu cho: {u['email']}")

    default_room = db.query(RoomModel).filter(RoomModel.name == "Phòng Kiến Trúc").first()
    if not default_room and users:
        room = RoomModel(name="Phòng Kiến Trúc", owner_id=users[0].id)
        db.add(room)
        db.commit()
        print(" [+] Đã tạo phòng mặc định: # Phòng Kiến Trúc")

    db.close()
    print("--> Hoàn tất nạp dữ liệu!")

if __name__ == "__main__":
    seed()
