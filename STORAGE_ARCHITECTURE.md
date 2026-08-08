┌─────────────────────────────────────────────────────────────────┐
│                    VPS  (Control Plane only)                    │
│                                                                 │
│  Django/API  │  MQTT  │  Celery  │  PostgreSQL  │  Redis        │
│                                                                 │
│  SeaweedFS thu nhỏ:  CHỈ lưu thumbnails  (~3GB max)            │
│  /tmp:               workspace render + ZIP  (12GB)             │
│                                                                 │
│  VPS KHÔNG BAO GIỜ giữ ảnh gốc hay video output                │
└────────┬──────────────────────────────────────┬─────────────────┘
         │ ký presigned PUT/GET URL              │ upload output
         │ VPS không nhận bytes                  │ trực tiếp
         ▼                                       ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Cloudflare R2  (Primary Storage)             │
│                                                                 │
│  bucket: media/          bucket: output/                        │
│  ├─ <cam>/<date>/*.jpg   ├─ zip/<id>.zip      TTL 24h          │
│  ├─ (tất cả ảnh gốc)     └─ video/<id>.mp4    TTL 7d           │
│  └─ lifecycle: xóa sau                                         │
│     hết vòng đời dự án                                         │
└────────┬────────────────────────────────────────────────────────┘
         │ sync về (pull hàng đêm)
         ▼
┌─────────────────────────────────────────────────────────────────┐
│               Local Machine  (Ground Truth)                     │
│  • Toàn bộ ảnh gốc, không TTL, không xóa                       │
│  • Heavy render/ZIP → upload thẳng lên R2 output               │
└─────────────────────────────────────────────────────────────────┘




Camera ──[MQTT]──► VPS: "tôi có ảnh mới"
VPS ──────────────► Camera: "đây là presigned PUT URL → R2"
Camera ──[HTTPS]──► R2 trực tiếp (VPS không nhận 1 byte nào)
Camera ──[MQTT]──► VPS: "upload xong, key = cam1/2026/08/07/abc.jpg"
VPS ──────────────► DB: lưu metadata + tạo thumbnail nhỏ → SeaweedFS
Browser ──► VPS API (auth check)
VPS ──────► Browser: presigned GET URL → R2
Browser ──► R2 trực tiếp (VPS không relay bytes)
Celery worker trên VPS:
  1. Lấy danh sách presigned GET → download frames từ R2 vào /tmp
  2. ffmpeg encode / zip build trong /tmp
  3. Upload output → R2 output bucket trực tiếp
  4. Xóa /tmp
  5. Ghi metadata vào DB (key trên R2)

  ┌──────────────────────────────────────────────┐
│              DISK VPS — 45 GB                │
├──────────────────────┬──────────┬────────────┤
│ Phần                 │ Dung lượng│ Ghi chú   │
├──────────────────────┼──────────┼────────────┤
│ OS + Docker images   │   5 GB   │ tĩnh       │
│ PostgreSQL metadata  │   1 GB   │ tăng chậm  │
│ SeaweedFS thumbnails │   3 GB   │ ~30K thumb │
│ /tmp workspace       │  12 GB   │ render+zip │
│ Buffer               │  24 GB   │ rất thoải  │
└──────────────────────┴──────────┴────────────┘