#!/usr/bin/env python3
"""
print_tree.py — In cấu trúc thư mục dự án dưới dạng cây.

Cách dùng:
    python3 print_tree.py                  # in cây từ thư mục hiện tại
    python3 print_tree.py /path/to/dir     # in cây từ thư mục chỉ định
    python3 print_tree.py -d 4             # giới hạn độ sâu 4
    python3 print_tree.py -a               # hiện cả file ẩn (.gitignore, .env...)
    python3 print_tree.py -f               # chỉ in thư mục, bỏ qua file
    python3 print_tree.py -o tree.txt      # ghi ra file thay vì stdout
"""

import argparse
import os
import sys
from pathlib import Path


# ============================================================
# CẤU HÌNH: các thư mục / file sẽ bị bỏ qua
# ============================================================

# Thư mục thư viện, cache, build... — bỏ qua mặc định
IGNORED_DIRS = {
    # Python
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".tox", ".eggs", "*.egg-info", ".venv", "venv", "env", ".env",
    "site-packages", "dist", "build",
    # Node / JS
    "node_modules", ".next", ".nuxt", ".svelte-kit", ".turbo",
    ".parcel-cache", ".cache", "coverage", ".nyc_output",
    # Git / IDE
    ".git", ".svn", ".hg", ".idea", ".vscode", ".vs",
    # Khác
    ".DS_Store", "target", "out", "bin", "obj",
    ".terraform", ".serverless",
}

# Phần mở rộng file — bỏ qua mặc định (rác, log, cache)
IGNORED_FILE_EXTS = {
    ".pyc", ".pyo", ".pyd",
    ".log",
    ".swp", ".swo",
    ".tmp",
    ".lock",
}

# File cụ thể — bỏ qua mặc định
IGNORED_FILES = {
    ".DS_Store",
    "Thumbs.db",
    "desktop.ini",
    ".gitignore",  # nếu muốn hiện thì bỏ dòng này
}

# Ký tự vẽ cây
BRANCH = "├── "
LAST   = "└── "
PIPE   = "│   "
SPACE  = "    "


# ============================================================
# HÀM CHÍNH
# ============================================================

def should_ignore_dir(name: str) -> bool:
    """Trả True nếu thư mục cần bỏ qua."""
    return name in IGNORED_DIRS


def should_ignore_file(name: str) -> bool:
    """Trả True nếu file cần bỏ qua."""
    if name in IGNORED_FILES:
        return True
    ext = os.path.splitext(name)[1].lower()
    return ext in IGNORED_FILE_EXTS


def list_entries(path: Path, show_hidden: bool, files_only_dir: bool):
    """
    Trả về (dirs, files) đã sắp xếp, đã lọc.
    dirs: list[Path], files: list[Path]
    """
    try:
        entries = list(path.iterdir())
    except PermissionError:
        return [], []

    dirs, files = [], []
    for entry in entries:
        name = entry.name

        # Bỏ qua file/thư mục ẩn nếu không bật -a
        if not show_hidden and name.startswith("."):
            continue

        if entry.is_dir():
            if not should_ignore_dir(name):
                dirs.append(entry)
        elif entry.is_file():
            if files_only_dir:
                continue
            if not should_ignore_file(name):
                files.append(entry)

    # Sắp xếp: thư mục trước, file sau, alphabet (case-insensitive)
    dirs.sort(key=lambda p: p.name.lower())
    files.sort(key=lambda p: p.name.lower())
    return dirs, files


def print_tree(
    root: Path,
    prefix: str = "",
    max_depth: int | None = None,
    current_depth: int = 0,
    show_hidden: bool = False,
    files_only_dir: bool = False,
    out=sys.stdout,
):
    """In cây đệ quy."""
    if max_depth is not None and current_depth >= max_depth:
        return

    dirs, files = list_entries(root, show_hidden, files_only_dir)
    entries = dirs + files  # đã sắp xếp sẵn

    for i, entry in enumerate(entries):
        is_last = (i == len(entries) - 1)
        connector = LAST if is_last else BRANCH

        # Nhãn hiển thị: thêm dấu "/" cho thư mục
        label = entry.name + ("/" if entry.is_dir() else "")
        print(f"{prefix}{connector}{label}", file=out)

        if entry.is_dir():
            extension = SPACE if is_last else PIPE
            print_tree(
                entry,
                prefix=prefix + extension,
                max_depth=max_depth,
                current_depth=current_depth + 1,
                show_hidden=show_hidden,
                files_only_dir=files_only_dir,
                out=out,
            )


def main():
    parser = argparse.ArgumentParser(
        description="In cấu trúc thư mục dự án dưới dạng cây.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Thư mục gốc (mặc định: thư mục hiện tại).",
    )
    parser.add_argument(
        "-d", "--depth",
        type=int,
        default=None,
        help="Độ sâu tối đa (mặc định: không giới hạn).",
    )
    parser.add_argument(
        "-a", "--all",
        action="store_true",
        help="Hiện cả file/thư mục ẩn (bắt đầu bằng dấu chấm).",
    )
    parser.add_argument(
        "-f", "--folders-only",
        action="store_true",
        help="Chỉ in thư mục, bỏ qua file.",
    )
    parser.add_argument(
        "-o", "--output",
        default=None,
        help="Ghi kết quả ra file (mặc định: in ra stdout).",
    )
    args = parser.parse_args()

    root = Path(args.path).resolve()
    if not root.exists():
        print(f"Lỗi: đường dẫn không tồn tại: {root}", file=sys.stderr)
        sys.exit(1)
    if not root.is_dir():
        print(f"Lỗi: không phải thư mục: {root}", file=sys.stderr)
        sys.exit(1)

    # Mở output
    if args.output:
        out_file = open(args.output, "w", encoding="utf-8")
        out = out_file
    else:
        out = sys.stdout

    try:
        # In tên thư mục gốc
        print(f"{root.name}/", file=out)
        print_tree(
            root,
            prefix="",
            max_depth=args.depth,
            current_depth=0,
            show_hidden=args.all,
            files_only_dir=args.folders_only,
            out=out,
        )
    finally:
        if args.output:
            out_file.close()
            print(f"Đã ghi vào: {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()