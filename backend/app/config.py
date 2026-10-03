import json
import logging

from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "Team Chat API"
    DATABASE_URL: str = "postgresql://postgres:postgres_password@db:5432/teamchat_db"
    JWT_SECRET_KEY: str = "super-secret-key-change-it-in-production-min-32-chars"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    GOOGLE_CLIENT_ID: str = (
        "869671892121-o2un8vci63vtdpio7rgv5spdv525vo1u.apps.googleusercontent.com"
    )

    # Nơi lưu tệp đính kèm và ảnh đại diện (gắn Docker volume)
    UPLOAD_DIR: str = "/app/uploads"
    MAX_UPLOAD_BYTES: int = 25 * 1024 * 1024

    # Danh sách origin được phép gọi API; "*" chỉ dùng khi phát triển
    CORS_ORIGINS: str = "*"

    # Quá bao lâu không nhận được gì từ một client thì coi như kết nối đã chết.
    # Client gửi ping mỗi 30 giây, nên 90 giây cho phép lỡ 3 nhịp mới cắt --
    # đủ rộng cho tab chạy nền bị trình duyệt làm chậm bộ đếm thời gian.
    WS_IDLE_TIMEOUT_SECONDS: int = 90

    # Máy chủ giúp hai trình duyệt tìm đường kết nối khi gọi.
    #
    #   STUN chỉ giúp mỗi bên biết địa chỉ công khai của mình để nối thẳng.
    #   Đủ dùng trong cùng mạng LAN và phần lớn mạng gia đình.
    #
    #   TURN là máy chủ trung gian chuyển tiếp âm thanh/hình ảnh, cần khi hai bên
    #   ở hai mạng khác nhau mà không nối thẳng được (4G, mạng công ty, trường học).
    #   TURN bắt buộc có tài khoản, nên khai báo theo một trong hai cách:
    #
    #     Cách ngắn (khuyên dùng trong .env), các mục cách nhau bằng dấu phẩy:
    #       ICE_SERVERS=stun:stun.l.google.com:19302,turn:vd.com:3478|user|pass
    #
    #     Cách JSON, khi cần nhiều url cho cùng một máy chủ:
    #       ICE_SERVERS=[{"urls":["turn:vd.com:3478","turn:vd.com:3478?transport=tcp"],
    #                     "username":"user","credential":"pass"}]
    ICE_SERVERS: str = "stun:stun.l.google.com:19302"

    @property
    def ice_server_list(self) -> list:
        raw = (self.ICE_SERVERS or "").strip()
        if not raw:
            return []

        if raw.startswith("["):
            return self._parse_ice_json(raw)
        return self._parse_ice_shorthand(raw)

    @staticmethod
    def _parse_ice_json(raw: str) -> list:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            logging.warning("ICE_SERVERS không phải JSON hợp lệ, bỏ qua: %s", exc)
            return []
        if not isinstance(data, list):
            logging.warning("ICE_SERVERS dạng JSON phải là một danh sách, bỏ qua")
            return []

        servers = []
        for item in data:
            if isinstance(item, dict) and item.get("urls"):
                servers.append(item)
            else:
                logging.warning("Bỏ qua mục ICE thiếu trường urls: %r", item)
        return servers

    @staticmethod
    def _parse_ice_shorthand(raw: str) -> list:
        """Mỗi mục là 'url' hoặc 'url|username|credential'."""
        servers = []
        for entry in raw.split(","):
            entry = entry.strip()
            if not entry:
                continue
            parts = [p.strip() for p in entry.split("|")]
            server = {"urls": parts[0]}
            if len(parts) >= 3:
                server["username"] = parts[1]
                server["credential"] = parts[2]
            elif len(parts) == 2:
                logging.warning(
                    "Mục ICE %r thiếu mật khẩu, TURN cần đủ 'url|username|credential'",
                    entry,
                )
            servers.append(server)
        return servers

    class Config:
        env_file = ".env"
        extra = "ignore"

    @property
    def cors_origin_list(self) -> list:
        if self.CORS_ORIGINS.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

settings = Settings()
