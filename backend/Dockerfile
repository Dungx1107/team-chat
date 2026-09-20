FROM python:3.11-slim

WORKDIR /app

# Ngăn Python tạo file .pyc và cho phép log in thẳng ra terminal
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Copy và cài đặt các thư viện cần thiết
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Tạo user non-root để an toàn bảo mật
RUN useradd -m -u 1000 appuser && chown -R appuser /app

# Tạo sẵn thư mục uploads với đúng chủ sở hữu.
# Khi Docker gắn named volume lên đường dẫn này, quyền sở hữu của thư mục
# trong image được kế thừa -- nếu bỏ bước này, volume sẽ thuộc root
# và tiến trình chạy dưới appuser không ghi được tệp lên.
RUN mkdir -p /app/uploads && chown -R appuser:appuser /app/uploads

USER appuser

# Copy toàn bộ mã nguồn vào container
COPY --chown=appuser:appuser . .

EXPOSE 8000

# Lệnh khởi chạy FastAPI qua Uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
