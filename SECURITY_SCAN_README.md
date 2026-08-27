# Tổng kết quét bảo mật Backend và Frontend

Ngày quét: 11/08/2026  
Phạm vi: `repo/backend/` và `repo/frontend/`  
Phương pháp: Codex Security Standard Scan, phân tích tĩnh và chỉ đọc source hiện tại.

## Kết quả tổng quan

Phát hiện **7 vấn đề bảo mật**:

| Mức độ | Số lượng |
|---|---:|
| High | 1 |
| Medium | 6 |
| Critical | 0 |

Không xác nhận được đường khai thác SQL injection, command injection, SSRF, XSS, unsafe deserialization hoặc path traversal trong các endpoint đang hoạt động.

Các quyết định kiến trúc đã được chấp nhận và không tính là lỗ hổng riêng:

- Camera dùng chung một credential cho MQTT và API upload.
- MQTT TLS hiện tạm hoãn theo kế hoạch triển khai phần cứng.
- Django staff là superadmin toàn hệ thống.
- Ảnh gốc và output ưu tiên Cloudflare R2; SeaweedFS giữ thumbnail/cache hoặc làm storage dự phòng.

## Thứ tự ưu tiên xử lý

1. Khóa ký tự wildcard trong `camera.code`.
2. Ràng buộc upload completion với upload intent do server phát hành.
3. Giới hạn kích thước và quota upload R2/SeaweedFS.
4. Áp dụng `can_download` tại mọi nơi sinh presigned URL.
5. Thu hồi render/ZIP khi membership bị xóa hoặc chuyển tenant.
6. Giới hạn số render/ZIP đang chờ theo tenant và camera.
7. Thu hẹp API tìm kiếm user theo tenant hoặc chuyển sang invitation flow.

## 1. MQTT wildcard phá vỡ cách ly camera

Mức độ: **High**  
CWE: `CWE-639`, `CWE-863`

`camera.code` do tenant admin nhập nhưng chưa bị giới hạn ký tự. Giá trị này được dùng trực tiếp làm MQTT username và thay vào ACL dạng `camera/%u/...`.

Nếu tạo camera có code `+`, ACL có thể trở thành:

```text
camera/+/data
camera/+/status
camera/+/ack
camera/+/cmd
```

Điều này cho phép credential của một camera khớp topic của các camera khác, dẫn đến đọc lệnh MQTT và giả mạo telemetry, trạng thái hoặc ACK xuyên tenant.

Vị trí liên quan:

- `repo/backend/core/api_views/cameras.py:39`
- `repo/backend/core/api_views/cameras.py:137`
- `repo/backend/mqtt_service/device_manager.py:70`
- `repo/backend/mqtt_service/device_manager.py:106`
- `repo/backend/mqtt_service/listener.py:226`

Hướng sửa:

- Dùng validator chung ở model và API, ví dụ `^[A-Za-z0-9_-]+$`.
- Từ chối `+`, `#`, `/`, khoảng trắng và control character.
- Tốt nhất dùng MQTT principal bất biến sinh từ UUID, tách khỏi code hiển thị có thể chỉnh sửa.
- Kiểm tra và xử lý các camera cũ có code không an toàn trước khi đăng ký lại ACL.

## 2. Upload completion có thể replay một object thành nhiều Media

Mức độ: **Medium**  
CWE: `CWE-400`, `CWE-294`

`upload_complete()` nhận `media_id` và `key` từ thiết bị. Endpoint chỉ kiểm tra prefix camera và object có tồn tại, nhưng không yêu cầu một upload intent hợp lệ chứa đúng media ID, key, storage và thời hạn.

Thiết bị có credential hợp lệ có thể dùng một object đã upload, liên tục gửi UUID mới và tạo nhiều bản ghi `Media` cùng trỏ vào một storage key.

Hậu quả:

- Tăng không giới hạn bảng `Media` và thống kê theo ngày.
- Archive/render có thể xử lý lặp lại cùng một object.
- Xóa một Media alias sẽ xóa object storage, làm các alias còn lại bị hỏng.

Vị trí liên quan:

- `repo/backend/core/views/device_api.py:129`
- `repo/backend/core/views/device_api.py:152`
- `repo/backend/core/models/media.py:23`
- `repo/backend/core/signals.py:84`

Hướng sửa:

- Lưu upload intent gồm camera ID, media ID, key, backend, MIME type, kích thước dự kiến và expiry.
- Completion phải atomically consume intent đúng một lần.
- Từ chối completion khi cache/intent không tồn tại hoặc đã hết hạn.
- Thêm uniqueness phù hợp cho `(storage, s3_key)`.

## 3. Presigned upload không giới hạn kích thước và quota

Mức độ: **Medium**  
CWE: `CWE-400`, `CWE-770`

Presigned PUT hiện chỉ ràng buộc bucket, key và `Content-Type`, không ràng buộc số byte. Upload đi thẳng vào R2 hoặc SeaweedFS nên không chịu `client_max_body_size` của Nginx.

Đặc biệt, thumbnail luôn được upload vào SeaweedFS trên VPS. Một camera credential bị lộ có thể upload object rất lớn và làm đầy ổ đĩa VPS. Thiết bị cũng có thể không gọi completion, khiến object trở thành orphan không có metadata để cleanup.

Vị trí liên quan:

- `repo/backend/core/views/device_api.py:73`
- `repo/backend/core/views/device_api.py:99`
- `repo/backend/core/utils/storage.py:236`
- `repo/backend/core/views/device_api.py:152`

Hướng sửa:

- Dùng upload policy có `content-length-range`, hoặc ký chính xác `Content-Length` dự kiến.
- Đặt giới hạn riêng cho original và thumbnail.
- Áp dụng quota byte/object theo camera và theo ngày.
- Xóa ngay object quá kích thước khi completion.
- Có job đối soát và xóa upload intent hết hạn chưa completion.
- Bổ sung filesystem quota cho SeaweedFS và bucket quota/lifecycle cho R2.

## 4. `can_download=false` vẫn nhận URL tải dữ liệu

Mức độ: **Medium**  
CWE: `CWE-862`, `CWE-863`

Model đã định nghĩa `can_download`, và endpoint tải một ảnh có kiểm tra quyền này. Tuy nhiên các API gallery, camera latest, renders và downloads center vẫn tạo presigned URL ảnh gốc, MP4 hoặc ZIP chỉ sau khi kiểm tra quyền xem camera.

Ẩn nút download ở frontend không đủ vì user có thể gọi API trực tiếp và sao chép URL.

Vị trí liên quan:

- `repo/backend/core/models/camera.py:168`
- `repo/backend/core/api_views/media.py:50`
- `repo/backend/core/api_views/cameras.py:176`
- `repo/backend/core/api_views/renders.py:15`
- `repo/backend/core/api_views/downloads.py:94`

Hướng sửa:

- Tạo một helper duy nhất chịu trách nhiệm cấp URL original/output.
- Nếu `can_download=false`, chỉ trả thumbnail hoặc preview đã giảm kích thước.
- Không trả `view_url` của original vì URL này vẫn tải được cùng bytes với `download_url`.
- Kiểm tra đủ gallery, latest, renders, downloads, archive detail và các wrapper còn hoạt động.

## 5. User đã rời tenant vẫn truy cập hoặc xóa artifact cũ

Mức độ: **Medium**  
CWE: `CWE-863`

Quyền của `MediaArchive` và `VideoRender` đang chấp nhận `requested_by` độc lập với membership hiện tại.

Sau khi user bị gỡ khỏi client hoặc chuyển sang client khác, họ vẫn có thể:

- Liệt kê render/ZIP đã yêu cầu trước đây.
- Nhận presigned URL tải output của tenant cũ.
- Xóa render/ZIP và làm signal xóa object storage tương ứng.

Vị trí liên quan:

- `repo/backend/core/models/media.py:189`
- `repo/backend/core/models/media.py:306`
- `repo/backend/core/api_views/renders.py:22`
- `repo/backend/core/api_views/renders.py:117`
- `repo/backend/core/api_views/downloads.py:102`

Hướng sửa:

- `requested_by` chỉ dùng để audit, không dùng như quyền truy cập lâu dài.
- Mọi list/detail/download/delete phải yêu cầu quyền hiện tại với camera/client chứa artifact.
- Khi xóa hoặc chuyển membership, hủy job đang chờ và thu hồi/xóa output không còn được phép truy cập.

## 6. Tenant admin có thể dò user của tenant khác

Mức độ: **Medium**  
CWE: `CWE-200`, `CWE-359`

`api_user_search()` cho phép bất kỳ client admin nào query toàn bộ user đang active. Kết quả trả về ID, username, email và full name mà không lọc tenant hoặc loại staff.

Sau đó, thử invite user đã thuộc tenant khác còn làm lộ tên tenant trong thông báo lỗi.

Vị trí liên quan:

- `repo/backend/core/api_views/users.py:95`
- `repo/backend/core/api_views/clients.py:135`
- `repo/frontend/src/pages/ClientsPage.tsx:487`

Hướng sửa:

- Client admin chỉ được thấy thành viên tenant hiện tại hoặc invitation candidate được định nghĩa rõ.
- Loại staff và user đã thuộc tenant khác khỏi kết quả.
- Tốt hơn là mời bằng email/username chính xác và luôn trả thông báo chung, không xác nhận user hoặc tenant có tồn tại.
- Không trả numeric user ID và PII nếu không cần thiết.
- Thêm minimum query length và throttle phía backend.

## 7. Không giới hạn số lượng render và ZIP đang chờ

Mức độ: **Medium**  
CWE: `CWE-400`, `CWE-770`

Mỗi POST tạo render hoặc archive đều tạo DB row và enqueue một Celery task mới. Không có giới hạn số job pending/processing theo user, tenant hoặc camera và không gộp job trùng.

Một render có thể lấy toàn bộ ảnh trong một năm, chạy 4K và giữ worker tới gần hai giờ. Với render worker concurrency bằng 1, một tenant admin có thể tạo backlog khiến tenant khác phải chờ rất lâu.

Vị trí liên quan:

- `repo/backend/core/api_views/renders.py:68`
- `repo/backend/core/api_views/downloads.py:25`
- `repo/backend/core/tasks.py:219`
- `repo/backend/core/tasks.py:247`

Hướng sửa:

- Đặt giới hạn atomic cho số job pending/processing theo tenant, camera và user.
- Dùng idempotency key hoặc reuse job tương đương đang chờ.
- Giới hạn số frame và tổng byte ước tính trước khi enqueue.
- Cung cấp cancel/revoke task an toàn.
- Thiết lập Redis queue limit, container disk quota và cảnh báo queue depth.

## Các điểm đã kiểm tra và chưa phát hiện lỗi xác thực

- DRF mặc định dùng `SessionAuthentication` và `IsAuthenticated`.
- Login là POST và có CSRF protection.
- Logout yêu cầu session hợp lệ và POST.
- Site/camera/media mutation hiện có kiểm tra tenant/object-level.
- Schedule ID được bind với camera cha.
- Query database dùng Django ORM; chưa tìm thấy SQL injection.
- FFmpeg chạy bằng argv list, không dùng shell, và resolution/FPS được allowlist.
- Temporary path và storage key quan trọng được server sinh.
- React không dùng `dangerouslySetInnerHTML`, `eval` hoặc lưu auth token trong localStorage.
- Cleanup render/archive sử dụng metadata storage/output bucket tương ứng.
- Source hiện tại không còn private key hoặc credential runtime thật được commit trong phạm vi quét.

## Các kiểm tra deployment cần làm thêm

- Nếu `R2_PUBLIC_DOMAIN` đang bật, xác minh original media không trở thành URL public vĩnh viễn.
- Xác minh `/admin/` được khóa bằng Cloudflare Access, WAF hoặc IP allowlist.
- Kiểm tra quota và lifecycle thực tế của R2 và SeaweedFS.
- Kiểm tra Cloudflare/Nginx rate limit dùng đúng IP người dùng thay vì chỉ thấy IP edge Cloudflare.
- Sau khi bật MQTT TLS, kiểm tra lại TCP 1883, WebSocket 8083 và credential đang chạy trên CM4.

## Checklist regression sau khi sửa

- Camera code `+`, `#`, `/`, whitespace và control character phải bị từ chối.
- Credential camera A không publish, subscribe hoặc receive topic camera B.
- Completion thiếu intent, sai key, sai backend hoặc replay phải bị từ chối.
- Upload quá kích thước và vượt quota phải bị chặn hoặc xóa.
- Member `can_download=false` không nhận original, MP4 hoặc ZIP URL từ bất kỳ API nào.
- User bị gỡ membership không còn list, tải hoặc xóa artifact tenant cũ.
- Client admin không tìm thấy staff hoặc user tenant khác.
- Request đồng thời không vượt quá giới hạn job pending/processing.
- Job render trùng được reuse hoặc từ chối thay vì enqueue thêm.

## Báo cáo gốc

- Báo cáo Markdown: `/tmp/codex-security-scans/UI_autotimelapse/standard-h8QnZZ/report.md`
- Findings JSON: `/tmp/codex-security-scans/UI_autotimelapse/standard-h8QnZZ/findings.json`
- SARIF: `/tmp/codex-security-scans/UI_autotimelapse/standard-h8QnZZ/exports/results.sarif`

