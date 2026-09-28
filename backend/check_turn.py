"""Kiểm tra cấu hình STUN/TURN đang khai báo trong .env có dùng được không.

Chạy:  docker compose exec backend python check_turn.py

Vì sao cần: khi TURN sai thông tin đăng nhập hoặc không kết nối được, cuộc gọi
vẫn hiện "đang kết nối" rồi im lặng thất bại -- rất khó đoán nguyên nhân. Script
này gửi thẳng một yêu cầu tới máy chủ theo giao thức STUN/TURN để biết chắc.
"""

import os
import re
import secrets
import socket
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.config import settings  # noqa: E402

MAGIC_COOKIE = 0x2112A442
BINDING_REQUEST = 0x0001
ALLOCATE_REQUEST = 0x0003


def parse_url(url: str):
    """turn:host:3478?transport=tcp -> (scheme, host, port, transport)"""
    m = re.match(r"^(stun|stuns|turn|turns):([^:?]+)(?::(\d+))?(?:\?transport=(\w+))?$", url.strip())
    if not m:
        return None
    scheme, host, port, transport = m.groups()
    default_port = 5349 if scheme in ("stuns", "turns") else 3478
    return scheme, host, int(port or default_port), (transport or "udp").lower()


def build_request(method: int) -> bytes:
    """Gói tin STUN: 2 byte method, 2 byte độ dài, 4 byte magic cookie, 12 byte id."""
    return struct.pack(">HHI", method, 0, MAGIC_COOKIE) + secrets.token_bytes(12)


def probe(host: str, port: int, transport: str, method: int, timeout: float = 4.0):
    """Gửi một gói và chờ phản hồi. Trả về (thành công, mô tả)."""
    try:
        addr_info = socket.getaddrinfo(host, port, proto=socket.IPPROTO_UDP if transport == "udp" else socket.IPPROTO_TCP)
    except socket.gaierror as e:
        return False, f"không phân giải được tên miền ({e.strerror or e})"

    family, socktype, proto, _, sockaddr = addr_info[0]
    sock = socket.socket(family, socket.SOCK_DGRAM if transport == "udp" else socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        request = build_request(method)
        if transport == "udp":
            sock.sendto(request, sockaddr)
            data, _ = sock.recvfrom(2048)
        else:
            sock.connect(sockaddr)
            sock.sendall(request)
            data = sock.recv(2048)
    except socket.timeout:
        return False, "không có phản hồi (quá 4 giây)"
    except OSError as e:
        return False, f"lỗi mạng: {e}"
    finally:
        sock.close()

    if len(data) < 20:
        return False, "phản hồi quá ngắn, không phải STUN/TURN"

    msg_type = struct.unpack(">H", data[:2])[0]
    is_error = (msg_type & 0x0110) == 0x0110
    if method == ALLOCATE_REQUEST and is_error:
        # 401 là phản hồi ĐÚNG: máy chủ đang đòi xác thực, tức TURN có hoạt động
        return True, "máy chủ TURN phản hồi và yêu cầu xác thực (đúng như mong đợi)"
    return True, "máy chủ phản hồi bình thường"


def main() -> int:
    servers = settings.ice_server_list
    print("=" * 62)
    print("KIỂM TRA CẤU HÌNH STUN/TURN")
    print("=" * 62)

    if not servers:
        print("\nICE_SERVERS đang để trống.")
        print("Chỉ gọi được trong cùng mạng LAN. Muốn gọi qua Internet cần khai báo TURN.")
        return 1

    has_turn = False
    failures = 0

    for server in servers:
        urls = server["urls"]
        urls = [urls] if isinstance(urls, str) else urls
        has_login = bool(server.get("username") and server.get("credential"))

        for url in urls:
            parsed = parse_url(url)
            if not parsed:
                print(f"\n  {url}\n     ✗ địa chỉ sai định dạng")
                failures += 1
                continue

            scheme, host, port, transport = parsed
            is_turn = scheme.startswith("turn")
            has_turn = has_turn or is_turn
            method = ALLOCATE_REQUEST if is_turn else BINDING_REQUEST

            print(f"\n  {url}")
            print(f"     loại: {'TURN (chuyển tiếp)' if is_turn else 'STUN (dò địa chỉ)'} · {host}:{port}/{transport}")

            if scheme in ("stuns", "turns"):
                print("     ⚠ dùng TLS, script này chưa kiểm tra được -- hãy thử gọi thật")
                continue

            if host in ("127.0.0.1", "localhost", "::1"):
                print("     ✗ địa chỉ loopback: trình duyệt sẽ lặng lẽ bỏ qua máy chủ này.")
                print("       Dùng IP LAN thật của máy chạy TURN, ví dụ 192.168.1.10")
                failures += 1
                continue

            ok, detail = probe(host, port, transport, method)
            print(f"     {'✓' if ok else '✗'} {detail}")
            if not ok:
                failures += 1

            if is_turn and not has_login:
                print("     ✗ thiếu username/credential -- TURN bắt buộc phải có")
                failures += 1

    print("\n" + "=" * 62)
    if not has_turn:
        print("Chỉ có STUN, chưa có TURN.")
        print("Gọi được trong cùng mạng và phần lớn mạng gia đình, nhưng 4G và")
        print("mạng công ty/trường học thường chặn -- khi đó cuộc gọi sẽ thất bại.")
        return 1
    if failures:
        print(f"Có {failures} vấn đề ở trên, cần sửa trước khi gọi qua Internet.")
        return 1

    print("Cấu hình hợp lệ. Lưu ý: máy chủ phản hồi không đồng nghĩa tài khoản")
    print("đúng mật khẩu -- hãy gọi thử thật, và xem dòng trạng thái trong màn hình")
    print("cuộc gọi để biết media đi thẳng hay qua TURN.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
