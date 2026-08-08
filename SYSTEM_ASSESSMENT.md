
Đánh giá chuyên nghiệp — Khoảng trống hệ thống
P0 — Critical (Production Blockers)
1. CELERY_BEAT_SCHEDULE không tồn tại ở bất kỳ đâu
cleanup_expired_archives và bất kỳ periodic task nào chưa bao giờ được lên lịch. Container celery_beat đang chạy nhưng không có gì để làm — ZIP hết hạn không bao giờ bị xóa, storage tích tụ mãi.

2. Signal post_delete Media KHÔNG xóa file trên SeaweedFS/R2
Khi xóa Media record → DB sạch, Redis sạch, nhưng file JPG vẫn nằm trên SeaweedFS mãi mãi. Storage leak không giới hạn.

3. DEBUG mặc định là True, SECRET_KEY hardcode
Nếu site.env thiếu DEBUG=0 → production chạy debug mode → stack trace lộ ra ngoài, static files không cache, performance tệ.

4. Redis không có maxmemory — mặc định noeviction
Khi Redis đầy → block toàn bộ write operation → Celery không thể nhận task → site treo. Không có cảnh báo nào trước khi điều này xảy ra.

5. SeaweedFS -max=50 vượt dung lượng disk thực tế
50 volumes × 1024MB = 50GB nhưng disk chỉ còn ~32GB trống. Hệ thống có thể tự lấp đầy disk mà không có cơ chế nào chặn.

P1 — High (Ảnh hưởng vận hành thực tế)
6. Không có database connection pooling
PostgreSQL mặc định max_connections=100, với 20 camera đồng thời upload + nhiều user → cần PgBouncer hoặc ít nhất set CONN_MAX_AGE.

7. Không có health check endpoint trong Django
Nginx và Docker không có cách nào biết Django đã ready chưa. Khi rolling deploy hoặc container restart, request có thể đến trước Django sẵn sàng → 502 với user.

8. Không có resource limits trên container
celery_render chạy ffmpeg không giới hạn → có thể OOM toàn VPS, kéo chết các container khác cùng lúc.

9. Không có automated PostgreSQL backup
postgres được mount trực tiếp. Không có cron pg_dump, không có point-in-time recovery. Disk lỗi hoặc docker compose down -v nhầm → mất toàn bộ metadata.

10. device_auth so sánh mqtt_password plain text — timing attack
So sánh chuỗi thông thường dừng ngay khi gặp ký tự sai → kẻ tấn công đo thời gian phản hồi để đoán password. Phải dùng secrets.compare_digest().

P2 — Medium (Chất lượng & Hiệu năng dài hạn)
11. Pagination offset sẽ chậm khi dữ liệu lớn
PageNumberPagination dùng OFFSET SQL. Với 20 camera × 96 ảnh/ngày × 365 ngày = 700,800 records/năm → OFFSET 100000 LIMIT 60 sẽ scan 100,060 rows. Cần cursor-based pagination.

12. lru_cache trên boto3 client — không bao giờ refresh
Nếu credentials rotate hoặc connection pool của boto3 bị broken → phải restart container. Nên dùng connection với retry, hoặc TTL cache.

13. build_archive_zip load toàn bộ bytes vào RAM
800 ảnh × 6MB = 4.8GB RAM cùng lúc. Trên VPS LOW profile (2GB RAM) → OOM. Cần stream theo chunk.

14. Upload không có idempotency check
Camera có thể gọi upload_presign 2 lần cho cùng 1 ảnh (retry sau timeout) → 2 Media records với cùng taken_at và camera_id → duplicate ảnh trong gallery.

15. Thumbnail generation không rõ ràng trong pipeline
Code device_api.py cấp thumb_url (presigned PUT) để camera tự upload thumbnail. Nếu camera lỗi, không upload thumbnail → thumb_key trống → effective_thumb_key fallback về ảnh gốc (6MB) cho mỗi gallery thumbnail request. Cần backend tự generate thumb nếu thiếu.

P3 — Low (Quan sát & Vận hành)
Thiếu	Tác dụng khi có
Flower (Celery UI)	Thấy task queue đang tắc, worker dead, task fail
Django /health/	Load balancer / k8s probe biết khi nào unhealthy
Prometheus → Grafana	Metrics port đã mở (9324-9326) nhưng không có consumer
Disk usage alert	Cảnh báo khi SeaweedFS >80% trước khi site chết
Audit log model	Ai xóa ảnh nào, lúc nào — quan trọng với khách hàng doanh nghiệp
Per-camera storage quota	Ngăn 1 camera dùng hết toàn bộ hot store
CONN_MAX_AGE	Tái dùng DB connection thay vì mở/đóng mỗi request
Tóm tắt theo mức độ ưu tiên


P0 (fix ngay):  BEAT_SCHEDULE thiếu
                signal Media không xóa S3 object
                DEBUG default=True / SECRET_KEY hardcode
                Redis không maxmemory
                SeaweedFS -max=50 > disk thực tế

P1 (sprint tới): timing attack device_auth
                 resource limits container
                 Django health endpoint
                 pg_dump backup cron
                 connection pooling (CONN_MAX_AGE tối thiểu)

P2 (backlog):   cursor pagination
                archive ZIP streaming
                upload idempotency
                auto-generate thumbnail nếu thiếu

P3 (nice-to-have): Flower, Grafana, audit log, quota


P3 — Low (Quan sát & Vận hành)
Thiếu	Tác dụng khi có
Flower (Celery UI)	Thấy task queue đang tắc, worker dead, task fail
Django /health/	Load balancer / k8s probe biết khi nào unhealthy
Prometheus → Grafana	Metrics port đã mở (9324-9326) nhưng không có consumer
Disk usage alert	Cảnh báo khi SeaweedFS >80% trước khi site chết
Audit log model	Ai xóa ảnh nào, lúc nào — quan trọng với khách hàng doanh nghiệp
Per-camera storage quota	Ngăn 1 camera dùng hết toàn bộ hot store
CONN_MAX_AGE	Tái dùng DB connection thay vì mở/đóng mỗi request