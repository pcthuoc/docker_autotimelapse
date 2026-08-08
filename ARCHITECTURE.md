# Architecture & System Assessment — AutoTimelapse
> Cập nhật: 2026-08-07

---

## 1. Nguyên tắc cốt lõi

> **VPS = Control Plane only. R2 = Primary Storage. VPS không bao giờ giữ ảnh gốc.**

---

## 2. Kiến trúc Production

```
Camera (CM4)
    │ 1. MQTT → "tôi có ảnh mới"
    ▼
VPS (Control Plane)
    │ 2. ký presigned PUT URL → R2
    │
    │ 3. Camera upload thẳng → R2 (VPS không nhận bytes)
    │                                  ▼
    │                         Cloudflare R2  bucket: media/
    │                           <cam_id>/<date>/<uuid>.jpg
    │
    │ 4. Camera MQTT: "xong, key = cam1/.../abc.jpg"
    ▼
VPS: lưu metadata → PostgreSQL
     sinh thumbnail nhỏ → SeaweedFS (cap 3GB)
```

**Luồng xem ảnh:**
```
Browser → VPS API (auth check) → presigned GET URL → R2
Browser → R2 trực tiếp  (VPS không relay bytes)
```

**Luồng Render / ZIP (light, trên VPS):**
```
Celery:
  1. presigned GET → download frames từ R2 vào /tmp
  2. ffmpeg / zipfile trong /tmp
  3. upload output → R2 bucket: output/  (TTL: video=7d, zip=24h)
  4. xóa /tmp, ghi metadata vào DB
```

---

## 3. Phân bổ disk VPS (45 GB)

| Phần | Cap | Ghi chú |
|---|---|---|
| OS + Docker images | ~5 GB | tĩnh |
| PostgreSQL metadata | ~1 GB | tăng chậm |
| SeaweedFS (thumbnails only) | 3 GB | `-max=3`, không giữ ảnh gốc |
| `/tmp` workspace | 12 GB | render + ZIP ephemeral |
| Buffer an toàn | ~24 GB | headroom |

SeaweedFS 3GB ÷ 80KB/thumb ≈ 37,500 thumbnails. Cleanup thumbnail >30 ngày song song với migrate ảnh lên R2.

---

## 4. Cloudflare R2 — Phân vùng

| Bucket | Nội dung | Lifecycle |
|---|---|---|
| `media` | Ảnh gốc từ camera | Xóa theo vòng đời dự án |
| `output` | ZIP archive | 24 giờ (R2 lifecycle rule) |
| `output` | Video render | 7 ngày (R2 lifecycle rule) |

**Chi phí ước tính — 20 camera × 96 ảnh/ngày × 6MB:**
- Ingest: ~11 GB/ngày
- Lưu trữ 1 năm: ~4 TB → ~$60/tháng ($0.015/GB)
- Egress: **$0** (R2 miễn phí hoàn toàn)

---

## 5. Ranh giới Light / Heavy trên VPS

| Tiêu chí | VPS xử lý (light) | Queue về Local (future) |
|---|---|---|
| Khoảng thời gian render | ≤ 14 ngày | > 14 ngày |
| Số ảnh ZIP | ≤ 500 ảnh | > 500 ảnh |
| Độ phân giải video | ≤ 720p | > 1080p / 4K |
| Số camera/job | ≤ 1 | nhiều camera |

---

## 6. [FUTURE PLAN] Local Machine — Chưa implement

> **Không chạm vào phần này cho đến khi hệ thống có nhu cầu thực tế.**
> Điều kiện: vượt 10 camera active, cần render >30 ngày, hoặc yêu cầu offline.

- **Ground truth**: toàn bộ ảnh gốc, không TTL, không xóa
- **Heavy compute**: render 4K, multi-camera, ZIP toàn dự án
- **Luồng**: R2 cold → sync về local; local render → upload thẳng R2 output

---

## 7. Quy tắc phân loại dữ liệu

| Câu hỏi | YES | NO |
|---|---|---|
| Tái tạo được từ ảnh gốc? | R2 Output (TTL ngắn) | R2 media (lưu trữ) |
| Cần lưu >7 ngày? | R2 media / R2 output 7d | /tmp hoặc R2 output 24h |
| User cần ngay (<5 phút)? | VPS Celery xử lý | Queue về Local Machine |
| Bytes đi qua VPS? | Chỉ thumbnail | ❌ Không bao giờ (ảnh / video / ZIP) |

---

## 8. Redis Cache Plan — 20 Camera × 5 phút/ảnh

**Tải thực tế:** 20 × 12 ảnh/giờ = 240 ảnh/giờ, ~172,800 ảnh trong hot store sau 30 ngày.

| Tầng | Key pattern | TTL | Size ước tính |
|---|---|---|---|
| Presigned URL | `psurl:<hash>` | 51 phút | ~5 MB active |
| Gallery page | `gallery:<cam>:<date>:<page>` | 5 phút | ~14 MB |
| Dashboard latest | `latest_media:<cam_id>` | 60 giây | ~0.1 MB |
| DayStat calendar | `daystat:<cam>:<y>:<m>` | 10 phút | ~0.5 MB |
| Sessions + Celery | — | varies | ~15 MB |
| **Tổng** | | | **~35 MB** |

`maxmemory 128mb` đủ thoải mái. Policy `allkeys-lru` — khi đầy tự evict key ít dùng.

---

## 9. System Assessment — Khoảng trống & Fix

### ✅ P0 — Đã fix

| # | Vấn đề | Fix |
|---|---|---|
| 1 | `CELERY_BEAT_SCHEDULE` không tồn tại | Thêm vào `settings.py` |
| 2 | Signal `post_delete` không xóa S3 object | Thêm `storage.delete_key` vào signal |
| 3 | Redis không `maxmemory` → noeviction | `--maxmemory 128mb --maxmemory-policy allkeys-lru` |
| 4 | SeaweedFS `-max=50` vượt disk | Đổi `-max=20` |
| 5 | `device_auth` timing attack | Đổi sang `secrets.compare_digest` |
| 6 | `CONN_MAX_AGE` thiếu | Thêm `CONN_MAX_AGE=60` vào DATABASES |
| 7 | Resource limits container thiếu | Thêm `deploy.resources.limits` |
| 8 | Django không có `/health/` endpoint | Thêm vào urls.py |

### ⚠ P1 — Cần làm (sprint tiếp)

| # | Vấn đề | Mức độ |
|---|---|---|
| 9 | `DEBUG` default `True` + `SECRET_KEY` hardcode | Config/env |
| 10 | Không có `pg_dump` backup tự động | Cron job |
| 11 | `lru_cache` boto3 không bao giờ refresh | Cần TTL cache hoặc retry |

### 🔵 P2 — Backlog

| # | Vấn đề |
|---|---|
| 12 | Pagination offset → chậm khi >100k records, cần cursor-based |
| 13 | `build_archive_zip` buffer toàn bộ RAM → OOM, cần stream |
| 14 | Upload idempotency — camera retry tạo duplicate Media record |
| 15 | Thumbnail thiếu → fallback ảnh gốc 6MB mỗi gallery request |

### 📋 P3 — Nice-to-have

Flower, Grafana/Prometheus (metrics port đã mở), audit log, per-camera quota, API versioning.
