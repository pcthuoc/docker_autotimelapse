# AutoTimelapse Cloud Platform — Hạ Tầng & Quy Trình Triển Khai

Hệ thống quản lý camera Timelapse công trình tự động, hỗ trợ chụp ảnh định kỳ, lưu trữ nén dữ liệu qua SeaweedFS S3, giao tiếp thiết bị real-time qua MQTT Mosquitto Dynamic Security và giao diện điều khiển React SPA.

---

## 🏗️ 1. Mô Hình Tách 3 Repositories GitHub (Multi-Repo Strategy)

Dự án được phân tách thành **3 Repositories độc lập** và liên kết với nhau qua **Git Submodules** (tất cả đều sử dụng chuẩn URL SSH):

1. **Repo Hạ Tầng Orchestration (`docker_autotimelapse`)**:
   - URL Git SSH: `git@github.com:pcthuoc/docker_autotimelapse.git`
   - Chứa: `docker-compose.yml`, `environment/`, `config/`, `site/Dockerfile`, `mqtt_service/Dockerfile`, `scripts/`, `README.md`.
2. **Repo Backend (`be_autotimelapse`)**:
   - URL Git SSH: `git@github.com:pcthuoc/be_autotimelapse.git`
   - Thư mục local: `repo/backend/` (Django REST API, Celery, MQTT Service).
3. **Repo Frontend (`fe_autotimelapse`)**:
   - URL Git SSH: `git@github.com:pcthuoc/fe_autotimelapse.git`
   - Thư mục local: `repo/frontend/` (React SPA, Vite, Tailwind CSS, `dist/`).

---

## 📂 2. Cấu Trúc Dự Án & Lưu Trữ Dữ Liệu (`./data/`)

```
docker_autotimelapse/                        # Root Infra Repo
├── docker-compose.yml                       # Multi-container Orchestration Stack
├── .env                                     # Environment variables (Gitignored)
├── environment/                             # Environment Templates
│   ├── site.env                             # Active env configuration
│   ├── site.env.example                     # Env template
│   └── local_settings.py.example            # Django local settings template
│
├── site/                                    # Django Web Docker Context
│   └── Dockerfile
├── mqtt_service/                            # MQTT Worker Docker Context
│   └── Dockerfile
│
├── config/                                  # Centralized Configurations
│   ├── seaweed/                             # SeaweedFS S3 Identities & ACLs (s3.json)
│   ├── mosquitto/                           # Mosquitto MQTT Broker Configs
│   └── nginx/                               # Nginx Reverse Proxy Configs
│
├── data/                                    # Persistent Local Data Mounts (Gitignored)
│   ├── postgres/                            # PostgreSQL Database Files
│   ├── seaweed/                             # SeaweedFS Storage Files (master, volume, filer)
│   └── mosquitto/                           # MQTT persistent data & logs
│
└── repo/                                    # Source Code Repositories (Git Submodules)
    ├── backend/                             # Django 4.2 Source Code
    ├── frontend/                            # React SPA Source Code
    │   └── dist/                            # Production SPA Build Output (Nginx Mount)
    ├── scripts/                             # Operational & Management Scripts
    └── sim.py                               # Camera Telemetry & Photo Simulator
```

---

## 🚀 3. Quy Trình Chạy Lệnh Build Hệ Thống Từ Đầu (Step-by-Step Commands)

### 1️⃣ Lệnh 1: Xóa Sạch Container & Data Cũ
```bash
docker compose down -v && docker rm -f $(docker ps -a -q) 2>/dev/null || true && rm -rf data/*
```

### 2️⃣ Lệnh 2: Khởi Tạo Cấu Trúc Dự Án & Tệp Môi Trường
```bash
./scripts/initialize
```

### 3️⃣ Lệnh 3: Build & Khởi Chạy Toàn Bộ Docker Stack
```bash
docker compose up -d --build
```

### 4️⃣ Lệnh 4: Tạo Tài Khoản Admin `pcthuoc` & Bucket S3 `media`
```bash
# Tạo Superuser pcthuoc (Mật khẩu: AdminPass2026!)
docker exec atl-site python manage.py shell -c "from django.contrib.auth.models import User; u, created = User.objects.get_or_create(username='pcthuoc', defaults={'email': 'pcthuoch@gmail.com', 'is_staff': True, 'is_superuser': True}); u.set_password('AdminPass2026!'); u.is_staff = True; u.is_superuser = True; u.is_active = True; u.save(); print('SUPERUSER PCTHUOC CREATED!')"

# Tạo Bucket media trên SeaweedFS S3
docker exec atl-site python manage.py shell -c "import boto3; admin_s3 = boto3.client('s3', endpoint_url='http://seaweed-filer:8333', aws_access_key_id='atl_admin_98568b04f027', aws_secret_access_key='MDr62YtQcdK-_DHdiiMbuC6OjFnIjlVWSJT5gDC8qiA'); admin_s3.create_bucket(Bucket='media'); print('BUCKET MEDIA CREATED!')"
```

### 5️⃣ Lệnh 5: Chạy Kiểm Thử Tự Động Toàn Bộ Hệ Thống
```bash
# Kiểm thử Mosquitto Dynamic Security ACL & Topic Isolation
docker exec -i atl-site python3 < scratch/test_mqtt_acl.py

# Kiểm thử Luồng Upload Ảnh Presigned S3 Workflow
docker exec -i atl-site python3 < scratch/test_photo_upload_workflow.py
```

---

## 📤 4. Lệnh Push Đồng Bộ 3 Repositories Lên GitHub (SSH)

```bash
# 1. Push Repo Backend (be_autotimelapse)
cd /root/UI_autotimelapse/repo/backend
git push -u origin master

# 2. Push Repo Frontend (fe_autotimelapse)
cd /root/UI_autotimelapse/repo/frontend
git push -u origin master

# 3. Push Repo Infra Orchestration (docker_autotimelapse)
cd /root/UI_autotimelapse
git push -u origin master
```

---

## 🛡️ 5. Phân Quyền & Bảo Mật (Security & Permissions)

- **Chặn IP Trực Tiếp**: Nginx chặn từ chối truy cập qua IP trực tiếp (không Host header) bằng `HTTP Status 444`.
- **Least-Privilege S3 ACL**:
  - `camera-service`: Chỉ có quyền `Write:media`, `Read:media`, `List:media`.
  - `api-service`: Có quyền `Read:media`, `Write:media`, `List:media`, `Delete:media`, `Tagging:media`.
  - `admin`: Duy nhất có quyền `Admin`.
- **Mosquitto Dynamic Security**: Trạm camera `%u` chỉ có quyền publish/subscribe trên topic riêng `camera/%u/*`.

---

## ⚡ 6. Kế Hoạch Kiến Trúc Phần Cứng 2 Lõi (ESP32-S3 + CM4) & Luồng Nguồn

Hệ thống hỗ trợ cơ chế hoạt động **2 Lõi vật lý**: **ESP32-S3** (Watchdog/Quản lý nguồn Always-On) và **Raspberry Pi CM4** (Lõi đo đạc Telemetry, Chụp ảnh & Xử lý chính).

```
                       ┌─────────────────────────────────────────┐
                       │              MQTT BROKER                │
                       └────▲───────────────────────────────▲────┘
                            │                               │
                Heartbeat & Bật CM4 Cmd               Telemetry, Camera Config,
                            │                         S3 Upload & Live View
                            │                               │
┌───────────────────────────┴──────────┐       ┌────────────┴─────────────────────┐
│             ESP32-S3                 │       │        Raspberry Pi CM4          │
│   (Always-On / Power Watchdog)       │       │    (Compute, Telemetry & Sensor) │
├──────────────────────────────────────┤       ├──────────────────────────────────┤
│ - Trạng thái Online/Offline trạm     │       │ - Đo Pin, Solar, Điện áp, Nguồn  │
│ - Bật / Tắt nguồn CM4 (MOSFET/Relay) │       │ - Đo Nhiệt độ, Độ ẩm môi trường  │
│ - Lắng nghe lệnh Bật CM4 từ Server   │       │ - Điều khiển Nikon D5300 (gphoto)│
│ - Quản lý SIM UART khi CM4 ngắt nguồn│       │ - Presigned Upload S3 (SeaweedFS)│
│ - Báo trạng thái CM4 Power (ON/OFF)  │       │ - Stream Live View realtime      │
└──────────────────┬───────────────────┘       └──────────────────┬───────────────┘
                   │                                              │
                   │ UART (Khi CM4 OFF)               USB (Khi CM4 ON)
                   └───────────────────┐     ┌────────────────────┘
                                       ▼     ▼
                                 ┌──────────────┐
                                 │  MODULE SIM  │
                                 │ (4G/LTE Cat4)│
                                 └──────────────┘
```

### 1️⃣ Nguyên Lý Phân Chia Nhiệm Vụ 2 Lõi
- **ESP32-S3 (Always-On Core / Power Watchdog)**:
  - Ăn nguồn cực thấp (~uA/mA). Chạy liên tục để giữ nhịp tim của trạm.
  - Trạng thái **ONLINE/OFFLINE** tổng quan của Camera trên Web Dashboard **ăn theo ESP32-S3**.
  - Lắng nghe lệnh từ Server (`power_on_cm4`, `capture_now`, `open_config`). Bật/Tắt nguồn MOSFET cấp điện cho CM4.
  - Sử dụng module SIM qua bus **UART** khi CM4 đang ngắt nguồn (`CM4_POWER_STATE = OFF`).

- **Raspberry Pi CM4 (Compute & Telemetry Core)**:
  - **Đo đạc Pin, Solar, Điện áp, Nhiệt độ/Độ ẩm & Thông số SIM**: Các cảm biến ADC/SIM nối trực tiếp với CM4. Khi CM4 bật lên, nó đo đạc và gửi bản tin Telemetry chuẩn xác lên Server.
  - Được cấp nguồn khi: Đến chu kỳ chụp ảnh định kỳ, khi mở Modal Config chỉnh thông số hoặc khi chạy Live View.
  - Khi CM4 bật lên, ESP32-S3 nhả bus UART để CM4 kết nối module SIM qua cổng **USB** (tốc độ cao).
  - Thực thi chụp ảnh qua `python-gphoto2`, upload ảnh S3/SeaweedFS và stream Live View.
  - Báo hoàn tất và thực hiện **Graceful Shutdown**, ESP32-S3 ngắt nguồn MOSFET và lấy lại bus UART.

### 2️⃣ Quy Trình Mở Modal Config & Tự Động Bật Nguồn CM4 (`power_on_cm4`)
1. Trước khi người dùng được phép chỉnh sửa thông số (ISO, Khẩu độ, Tốc độ, Chu kỳ chụp, SIM), **CM4 BẮT BUỘC PHẢI Ở TRẠNG THÁI ONLINE**.
2. Trên Camera Card & Modal Config hiển thị rõ trạng thái lõi CM4:
   - `💤 OFF (Đang ngủ)` | `⚡ POWERING_ON (Đang bật nguồn...)` | `🟢 ONLINE (Sẵn sàng)` | `🔄 SHUTTING_DOWN`
3. Khi mở Config / Chỉnh thông số:
   - Nếu CM4 đang `OFF`: Hệ thống **tự động gửi lệnh MQTT `power_on_cm4`** tới ESP32-S3.
   - Giao diện tạm thời khóa form và hiển thị `⚡ Đang kích nguồn CM4...`
   - ESP32-S3 nhận lệnh $\rightarrow$ Bật MOSFET cấp điện cho CM4.
   - CM4 khởi động (~10s), đo cảm biến Pin/Solar/Môi trường, đọc thông số máy ảnh Nikon D5300 và báo status `cm4_power_state = running`.
   - Ngay khi CM4 báo `running`, giao diện tự động mở khóa toàn bộ form cho phép người dùng xem & lưu cài đặt.
4. Khi đóng Modal Config (hoặc sau 5 phút không thao tác): CM4 báo Shutdown, ESP32-S3 ngắt nguồn MOSFET để tiết kiệm pin.

### 3️⃣ Dữ Liệu Lưu Trữ Phía Backend (`CameraDevice`)
- `esp32_last_seen_at`: Thời điểm ESP32-S3 báo tín hiệu sống gần nhất (xác định trạng thái Online/Offline trạm).
- `esp32_firmware`: Phiên bản Firmware của ESP32-S3.
- `cm4_power_state`: Trạng thái nguồn CM4 (`off`, `powering_on`, `running`, `shutting_down`).
- `cm4_last_seen_at`: Lần cuối CM4 gửi Telemetry / Thực thi nhiệm vụ.
- `sim_active_node`: Nút đang giữ module SIM (`esp32` via UART / `cm4` via USB).


