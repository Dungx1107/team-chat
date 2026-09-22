from typing import List, Optional
from sqlalchemy import or_
from sqlalchemy.orm import Session
from app.domain.interfaces import IUserRepository
from app.domain.models import User
from app.infra.db.models import UserModel

class UserRepository(IUserRepository):
    def __init__(self, db: Session):
        self.db = db

    def _to_entity(self, model: Optional[UserModel]) -> Optional[User]:
        if not model:
            return None
        return User(
            id=model.id,
            email=model.email,
            username=model.username,
            password_hash=model.password_hash,
            first_name=model.first_name,
            last_name=model.last_name,
            is_active=model.is_active,
            avatar_url=model.avatar_url,
            bio=model.bio,
            status=model.status,
            created_at=model.created_at,
        )

    def get_by_id(self, user_id: int) -> Optional[User]:
        model = self.db.query(UserModel).filter(UserModel.id == user_id).first()
        return self._to_entity(model)

    def get_by_email(self, email: str) -> Optional[User]:
        model = self.db.query(UserModel).filter(UserModel.email == email).first()
        return self._to_entity(model)

    def get_by_username(self, username: str) -> Optional[User]:
        model = self.db.query(UserModel).filter(UserModel.username == username).first()
        return self._to_entity(model)

    def create(self, user: User) -> User:
        model = UserModel(
            email=user.email,
            username=user.username,
            password_hash=user.password_hash,
            first_name=user.first_name,
            last_name=user.last_name,
            is_active=user.is_active,
            avatar_url=user.avatar_url,
            bio=user.bio,
            status=user.status,
            created_at=user.created_at,
        )
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        return self._to_entity(model)

    def update(self, user: User) -> User:
        model = self.db.query(UserModel).filter(UserModel.id == user.id).first()
        if not model:
            raise ValueError("Người dùng không tồn tại")
        model.first_name = user.first_name
        model.last_name = user.last_name
        model.avatar_url = user.avatar_url
        model.bio = user.bio
        model.status = user.status
        model.is_active = user.is_active
        self.db.commit()
        self.db.refresh(model)
        return self._to_entity(model)

    def search(self, keyword: str, limit: int = 20) -> List[User]:
        pattern = f"%{keyword.strip()}%"
        models = (
            self.db.query(UserModel)
            .filter(
                UserModel.is_active.is_(True),
                or_(
                    UserModel.username.ilike(pattern),
                    UserModel.email.ilike(pattern),
                    UserModel.first_name.ilike(pattern),
                    UserModel.last_name.ilike(pattern),
                ),
            )
            .order_by(UserModel.username.asc())
            .limit(limit)
            .all()
        )
        return [self._to_entity(m) for m in models]
