# AutoTimelapse Cloud Platform — Tài Liệu Kiến Trúc & Quy Trình Triển Khai

Hệ thống quản lý camera Timelapse công trình tự động, hỗ trợ chụp ảnh định kỳ, lưu trữ nén dữ liệu qua SeaweedFS S3, giao tiếp thiết bị real-time qua MQTT Mosquitto Dynamic Security và giao diện điều khiển React SPA.

---

## 🏗️ 1. Mô Hình Kiến Trúc Tổng Quan (System Architecture)

```
[ Camera Trạm Hardware / Simulator (sim.py) ]
       │                                  │
  MQTT (TCP: 1884)              Presigned S3 PUT (8333)
       │                                  │
       ▼                                  ▼
 ┌───────────────┐               ┌──────────────────┐
 │ atl-mosquitto │               │  seaweed-filer   │
 │ (DynSec ACL)  │               │   (S3 Gateway)   │
 └───────┬───────┘               └────────┬─────────┘
         │                                │
         ▼                                ▼
 ┌──────────────────────────────────────────────────┐
 │                atl-nginx (Proxy)                 │
 │  - Domain: cloud.congnghetimelapse.com           │
 │  - IP Direct: HTTP 444 (Chặn IP trực tiếp)       │
 └───────────────────────┬──────────────────────────┘
                         │
                         ▼
        ┌──────────────────────────────────┐
        │  atl-site (Django Web & REST)    │
        └────────────────┬─────────────────┘
                         │
           ┌─────────────┴─────────────┐
           ▼                           ▼
   ┌──────────────┐           ┌─────────────────┐
   │ atl-postgres │           │    atl-redis    │
   │ (DB Metadata)│           │ (Cache/Celery)  │
   └──────────────┘           └─────────────────┘
```

---

## 📂 2. Cấu Trúc Dự Án Đã Tối Ưu (Project Layout)

```
UI_autotimelapse/                            # Root Layer
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
│   ├── seaweed/                             # SeaweedFS S3 Identities & ACLs
│   │   └── s3.json
│   ├── mosquitto/                           # Mosquitto MQTT Broker Configs
│   │   ├── mosquitto.conf
│   │   └── dynamic-security.json
│   └── nginx/                               # Nginx Reverse Proxy Configs
│       └── conf.d/
│           └── nginx.conf
│
├── data/                                    # Host Data Volumes
│   └── mosquitto/                           # MQTT persistent data & logs
│       ├── data/
│       └── log/
│
└── repo/                                    # Source Code Repositories
    ├── backend/                             # Django 4.2 Source Code
    ├── frontend/                            # React SPA Source Code
    │   └── dist/                            # Production SPA Build Output (Nginx Mount)
    ├── scripts/                             # Operational & Management Scripts
    └── sim.py                               # Camera Telemetry & Photo Simulator
```

---

## 💡 3. Đánh Giá & Phương Án Tách Repos (Multi-Repo Strategy)

Việc tách thư mục tổng thành **3 Repos độc lập** là **RẤT HỢP LÝ** và chuẩn hóa theo tiêu chuẩn sản xuất (Production-grade Architecture):

1. **Repo 1: `infra-autotimelapse` (Hạ tầng Orchestration)**:
   - Chứa `docker-compose.yml`, `environment/`, `config/`, `site/Dockerfile`, `mqtt_service/Dockerfile`, `scripts/`.
   - Giúp SysOps / DevOps quản lý hạ tầng triển khai server độc lập.
2. **Repo 2: `backend-autotimelapse` (Mã nguồn Django)**:
   - Chứa `repo/backend/` (`autotimelapse/`, `core/`, `manage.py`, `requirements.txt`).
   - Giúp đội ngũ Backend phát triển, viết Unit Test và chạy CI/CD tự động.
3. **Repo 3: `frontend-autotimelapse` (Mã nguồn React SPA)**:
   - Chứa `repo/frontend/` (`src/`, `package.json`, `vite.config.ts`).
   - Khi release, CI/CD tự động build sang `dist/` và sync về Nginx server.

---

## 🚀 4. Quy Trình Khởi Tạo & Deploy Từng Bước (Deployment Guide)

### 🔹 Bước 1: Chuẩn bị biến môi trường
Sao chép các file mẫu sang môi trường chính thức:
```bash
cp environment/site.env.example environment/site.env
cp environment/site.env .env
```

### 🔹 Bước 2: Chạy Script Khởi Tạo Dự Án
Script sẽ tự động copy `local_settings.py` và chuẩn bị các thư mục `data/`:
```bash
./scripts/initialize
```

### 🔹 Bước 3: Build & Khởi Chạy Docker Stack
Khởi chạy toàn bộ 11 containers:
```bash
docker compose down
docker compose up -d --build
```

### 🔹 Bước 4: Khởi Tạo Tài Khoản Admin & S3 Bucket Media
1. **Tạo tài khoản Superuser quản trị**:
   ```bash
   ./scripts/manage.py createsuperuser
   ```
2. **Khởi tạo Bucket `media` & Thiết lập Mosquitto DynSec ACL**:
   ```bash
   docker exec atl-site python manage.py shell -c "
   import boto3, os; from django.conf import settings;
   admin_s3 = boto3.client('s3', endpoint_url=settings.SEAWEED['ENDPOINT_URL'], aws_access_key_id='atl_admin_98568b04f027', aws_secret_access_key='MDr62YtQcdK-_DHdiiMbuC6OjFnIjlVWSJT5gDC8qiA');
   admin_s3.create_bucket(Bucket='media');
   print('BUCKET MEDIA CREATED SUCCESSFULLY!')
   "
   ```

### 🔹 Bước 5: Chạy Kiểm Thử Hệ Thống
1. **Kiểm tra MQTT Broker & DynSec ACL**:
   ```bash
   docker exec -i atl-site python3 < scratch/test_mqtt_acl.py
   ```
2. **Kiểm tra Upload Ảnh Presigned S3 Workflow**:
   ```bash
   docker exec -i atl-site python3 < scratch/test_photo_upload_workflow.py
   ```

---

## 🛡️ 5. Phân Quyền & Bảo Mật (Security & Permissions)

- **Direct IP Blocking**: Mọi truy cập vào IP trực tiếp (không qua domain `cloud.congnghetimelapse.com`) bị Nginx từ chối với HTTP Status **444**.
- **Least-Privilege S3 ACL**:
  - Identity `camera-service`: Chỉ có quyền `Write:media`, `Read:media`, `List:media`.
  - Identity `api-service`: Có quyền `Read:media`, `Write:media`, `List:media`, `Delete:media`, `Tagging:media`.
  - Identity `admin`: Duy nhất có quyền `Admin`.
- **Mosquitto Dynamic Security**:
  - Trạm camera `%u` chỉ có quyền publish/subscribe trên topic của chính nó (`camera/%u/*`).

---

