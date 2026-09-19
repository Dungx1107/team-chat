from typing import Optional
from sqlalchemy.orm import Session
from app.domain.interfaces import IRefreshTokenRepository
from app.domain.models import RefreshToken
from app.infra.db.models import RefreshTokenModel

class RefreshTokenRepository(IRefreshTokenRepository):
    def __init__(self, db: Session):
        self.db = db

    def _to_entity(self, model: Optional[RefreshTokenModel]) -> Optional[RefreshToken]:
        if not model:
            return None
        return RefreshToken(
            id=model.id,
            user_id=model.user_id,
            token_hash=model.token_hash,
            expires_at=model.expires_at,
            is_revoked=model.is_revoked,
            created_at=model.created_at,
        )

    def create(self, refresh_token: RefreshToken) -> RefreshToken:
        model = RefreshTokenModel(
            user_id=refresh_token.user_id,
            token_hash=refresh_token.token_hash,
            expires_at=refresh_token.expires_at,
            is_revoked=refresh_token.is_revoked,
            created_at=refresh_token.created_at,
        )
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        return self._to_entity(model)

    def get_by_token_hash(self, token_hash: str) -> Optional[RefreshToken]:
        model = self.db.query(RefreshTokenModel).filter(RefreshTokenModel.token_hash == token_hash).first()
        return self._to_entity(model)

    def revoke_token(self, token_hash: str) -> None:
        model = self.db.query(RefreshTokenModel).filter(RefreshTokenModel.token_hash == token_hash).first()
        if model:
            model.is_revoked = True
            self.db.commit()

    def revoke_all_user_tokens(self, user_id: int) -> None:
        self.db.query(RefreshTokenModel).filter(
            RefreshTokenModel.user_id == user_id,
            RefreshTokenModel.is_revoked == False
        ).update({"is_revoked": True})
        self.db.commit()
