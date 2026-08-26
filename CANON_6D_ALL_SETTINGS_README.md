# 📷 TÀI LIỆU ĐẶC TẢ TOÀN BỘ TÙY CHỌN CÀI ĐẶT CANON EOS 6D (HARDWARE CONTRACT)

> **Thiết bị kiểm thử:** Canon EOS 6D (DSLR Full Frame)  
> **Giao thức điều khiển:** USB PTP qua libgphoto2 (CM4 Agent) & MQTT (Cloud Web UI)  
> **Camera Code:** `CAM-KCSHPT`  
> **Thời gian xuất dữ liệu:** 2026-08-26 (Đã xác minh 100% từ chip máy ảnh thực tế)

---

## 📊 BẢNG TỔNG HỢP TẤT CẢ CÁC THÔNG SỐ (SUMMARY OVERVIEW)

| # | Tên Trường (Field) | Tên Widget gphoto2 | Ghi được? (Writable) | Giá trị hiện tại | Số lượng tùy chọn (Choices) | Mô tả / Gợi ý Timelapse |
|---|---|---|---|---|---|---|
| 1 | **`iso`** | `iso` / `eos-iso` | ✅ Có | `1250` | **26 choices** | Độ nhạy sáng (100 -> 25600) |
| 2 | **`aperture`** | `aperture` / `f-number` | ✅ Có | `5.6` | **16 choices** | Khẩu độ ống kính (f/4 -> f/22) |
| 3 | **`shutter_speed`** | `shutterspeed` | ✅ Có | `1/250` | **52 choices** | Tốc độ màn trập (30s -> 1/4000s) |
| 4 | **`white_balance`** | `whitebalance` | ✅ Có | `Auto` | **9 choices** | Cân bằng trắng (Auto, Daylight...) |
| 5 | **`image_format`** | `imageformat` | ✅ Có | `L` | **35 choices** | Định dạng JPEG (L/M/S) & RAW |
| 6 | **`capture_target`** | `capturetarget` | ✅ Có | `Internal RAM` | **2 choices** | `Internal RAM` (ko thẻ) / `Memory card` |
| 7 | **`drivemode`** | `drivemode` | ✅ Có | `Single` | **6 choices** | Chụp đơn (`Single` / `Single silent`) |
| 8 | **`metering_mode`** | `meteringmode` | ✅ Có | `Evaluative` | **4 choices** | Chế độ đo sáng toàn khung/điểm |
| 9 | **`mirror_lockup`** | `mirrorlock` | ✅ Có | `0` | **2 choices** | Khóa gương lật (`0`=Tắt, `1`=Bật) |
| 10 | **`auto_power_off`** | `autopoweroff` | ✅ Có | `60` | Dynamic (Số giây) | Tự tắt nguồn (`0`=Tắt hẳn, `60`=1 phút) |
| 11 | **`high_iso_nr`** | `highisonr` | ✅ Có | `Off` | **5 choices** | Khử nhiễu ISO cao (`Off`, `Low`...) |
| 12 | **`autofocus`** | `eosremoterelease` | ✅ Có | `None` | **8 choices** | Kích hoạt lấy nét từ xa |
| 13 | **`focus_mode`** | `focusmode` | ✅ Có | `Manual` | **4 choices** | Chế độ lấy nét |
| 14 | **`exposure_compensation`**| `exposurecompensation`| ✅ Có | `0` | **1 choices** | Bù trừ sáng (khi ở Av/Tv) |
| 15 | **`exposure_mode`** | `autoexposuremode` | 🔒 Chỉ đọc | `Manual` | **41 choices** | Bánh xe vật lý trên thân máy (M/Av/Tv/P) |
| 16 | **`battery_level`** | `batterylevel` | 🔒 Chỉ đọc | `100%` | Phân trăm pin | Dung lượng pin thực tế |

---

## 🎯 CHI TIẾT DANH SÁCH CHOICES TỪNG THÔNG SỐ

### 1. ISO (`iso`) — 26 Choices
> Khuyến nghị cho Timelapse ban ngày: `100`, `200`, `400`  
> Khuyến nghị cho Timelapse ban đêm/hoàng hôn: `800`, `1600`, `3200`

`Auto`, `100`, `125`, `160`, `200`, `250`, `320`, `400`, `500`, `640`, `800`, `1000`, `1250`, `1600`, `2000`, `2500`, `3200`, `4000`, `5000`, `6400`, `8000`, `10000`, `12800`, `16000`, `20000`, `25600`

---

### 2. Khẩu độ (`aperture`) — 16 Choices (phụ thuộc Lens lắp trên máy)
> Khuyến nghị cho Timelapse phong cảnh/công trình: `5.6`, `8`, `11` (độ nét sâu nhất)

`4`, `4.5`, `5`, `5.6`, `6.3`, `7.1`, `8`, `9`, `10`, `11`, `13`, `14`, `16`, `18`, `20`, `22`

---

### 3. Tốc độ màn trập (`shutter_speed`) — 52 Choices
> Khuyến nghị cho Timelapse ban ngày: `1/125`, `1/250`, `1/500`, `1/1000`  
> Khuyến nghị cho Timelapse hoàng hôn/phơi đêm: `1`, `2`, `4`, `8`, `15`, `30` (giây)

`30`, `25`, `20`, `15`, `13`, `10.3`, `8`, `6.3`, `5`, `4`, `3.2`, `2.5`, `2`, `1.6`, `1.3`, `1`, `0.8`, `0.6`, `0.5`, `0.4`, `0.3`, `1/4`, `1/5`, `1/6`, `1/8`, `1/10`, `1/13`, `1/15`, `1/20`, `1/25`, `1/30`, `1/40`, `1/50`, `1/60`, `1/80`, `1/100`, `1/125`, `1/160`, `1/200`, `1/250`, `1/320`, `1/400`, `1/500`, `1/640`, `1/800`, `1/1000`, `1/1250`, `1/1600`, `2000`, `1/2500`, `1/3200`, `1/4000`

---

### 4. Cân bằng trắng (`white_balance`) — 9 Choices
> Khuyến nghị cho Timelapse ngoài trời: Đặt cố định `Daylight` hoặc `Cloudy` để tránh hiện tượng nhấp nháy màu (flicker) giữa các khung hình.

- `Auto` (Tự động)
- `Daylight` (Ánh sáng ban ngày - 5200K)
- `Shadow` (Bóng râm - 7000K)
- `Cloudy` (Trời nhiều mây - 6000K)
- `Tungsten` (Đèn dây tóc - 3200K)
- `Fluorescent` (Đèn huỳnh quang - 4000K)
- `Flash` (Đèn flash)
- `Manual` (Tùy chỉnh)
- `Color Temperature` (Độ K)

---

### 5. Định dạng ảnh (`image_format`) — 35 Choices
> Khuyến nghị chuẩn: `L` (Large Fine JPEG ~2.5MB) hoặc `RAW` / `RAW + L` nếu cần hậu kỳ màu sắc cao cấp.

- **JPEG Đơn lẻ:** `L`, `cL`, `M`, `cM`, `S1`, `cS1`, `S2`, `S3`
- **RAW Đơn lẻ:** `RAW` (20MP Full RAW), `mRAW` (11MP Medium RAW), `sRAW` (5MP Small RAW)
- **RAW + JPEG kết hợp:**
  - `RAW + L`, `RAW + cL`, `RAW + M`, `RAW + cM`, `RAW + S1`, `RAW + cS1`, `RAW + S2`, `RAW + S3`
  - `mRAW + L`, `mRAW + cL`, `mRAW + M`, `mRAW + cM`, `mRAW + S1`, `mRAW + cS1`, `mRAW + S2`, `mRAW + S3`
  - `sRAW + L`, `sRAW + cL`, `sRAW + M`, `sRAW + cM`, `sRAW + S1`, `sRAW + cS1`, `sRAW + S2`, `sRAW + S3`

---

### 6. Vị trí lưu ảnh (`capture_target`) — 2 Choices
- **`Internal RAM`** *(Khuyến nghị)*: Lưu ảnh vào bộ nhớ đệm RAM máy ảnh rồi tải ngay qua cáp USB vào CM4. **Không cần cắm thẻ nhớ SD trong máy ảnh**, chống hỏng thẻ khi chụp dài ngày.
- **`Memory card`**: Ghi đồng thời vào thẻ nhớ SD trên thân máy ảnh.

---

### 7. Chế độ chụp (`drivemode`) — 6 Choices
- **`Single`** *(Khuyến nghị)*: Chụp từng tấm đơn lẻ
- **`Single silent`**: Chụp đơn êm (giảm tiếng ồn gương lật)
- **`Continuous`**: Chụp liên tục tốc độ cao
- **`Continuous silent`**: Chụp liên tục êm
- **`Timer 2 sec`**: Hẹn giờ 2 giây
- **`Timer 10 sec`**: Hẹn giờ 10 giây

---

### 8. Chế độ đo sáng (`metering_mode`) — 4 Choices
- **`Evaluative`** *(Khuyến nghị)*: Đo sáng toàn khung hình (chia 63 vùng)
- **`Partial`**: Đo sáng cục bộ (khu vực trung tâm ~8%)
- **`Spot`**: Đo sáng điểm (~3.5% trung tâm)
- **`Center-weighted average`**: Đo sáng trung bình trọng tâm

---

### 9. Khóa gương lật (`mirror_lockup`) — 2 Choices
- `0`: Tắt khóa gương lật *(Khuyến nghị)*
- `1`: Bật khóa gương lật

---

### 10. Tự động tắt nguồn (`auto_power_off`)
- `0`: Tắt hẳn chế độ ngủ *(Khuyến nghị để máy luôn online nhận lệnh)*
- `60`, `120`, `240`, `480`, `900`, `1800` (giây)

---

### 11. Khử nhiễu ISO cao (`high_iso_nr`) — 5 Choices
- `Off` *(Khuyến nghị)*
- `Low`
- `Normal`
- `High`
- `Multi-Shot`

---

### 12. Kích hoạt lấy nét (`autofocus` / `eosremoterelease`) — 8 Choices
- `None`
- `Press Half AF` (Nhấn nửa cò để lấy nét AF)
- `Press Full AF` (Nhấn trọn cò để chụp AF)
- `Press Half MF`
- `Press Full MF`
- `Release Half`
- `Release Full`
- `Release`

---

## 🛠️ HƯỚNG DẪN 3 CÁCH TEST THỦ CÔNG TỪNG THÔNG SỐ

### CÁCH 1: Test Trực Tiếp Qua Web UI
1. Mở Web UI tại `https://cloud.congnghetimelapse.com/cameras`.
2. Bấm vào camera `CAM-KCSHPT` (hoặc icon bánh răng Settings).
3. Bấm nút **`↓ Pull from device`** (máy ảnh sẽ tự động bật nguồn và tải danh sách choices lên form).
4. Chọn thông số bạn muốn kiểm tra (ví dụ: ISO `3200`, Shutter Speed `1/500`, Target `Internal RAM`...).
5. Bấm nút **`Save & send to camera`**.
6. Web sẽ hiển thị thông báo thành công và trạng thái chuyển sang **`✓ In sync`** màu xanh.

---

### CÁCH 2: Test Qua Lệnh MQTT Python (Chạy trên Server)
Chạy lệnh trực tiếp từ server để gửi payload JSON xuống CM4 và kiểm tra phản hồi tức thì:

```bash
docker exec -it atl-site python3 -c "
import json, paho.mqtt.client as mqtt, time

client = mqtt.Client(client_id='manual_tester')
client.username_pw_set('admin', 'WkgY1YWF23CcnvK_dYNsel9C')
client.connect('100.64.0.1', 1883)
client.loop_start()

def on_msg(c, u, msg):
    print('\n📩 PHẢN HỒI TỪ CM4 / CANON 6D:')
    data = json.loads(msg.payload.decode())
    print(json.dumps(data, indent=2, ensure_ascii=False))

client.on_message = on_msg
client.subscribe('camera/CAM-KCSHPT/ack')

# 👉 THAY ĐỔI CÁC THÔNG SỐ BẠN MUỐN TEST TẠI ĐÂY:
payload = {
    'iso': '3200',
    'shutter_speed': '1/500',
    'aperture': '5.6',
    'white_balance': 'Daylight',
    'image_format': 'L',
    'capture_target': 'Internal RAM',
    'drivemode': 'Single',
    'auto_power_off': '0'
}

print('🚀 Đang gửi lệnh set_settings xuống Canon 6D...')
client.publish('camera/CAM-KCSHPT/cmd', json.dumps({
    'command': 'set_settings',
    'request_id': 'req-manual-test',
    'payload': payload
}))

time.sleep(5)
client.loop_stop()
client.disconnect()
"
```

---

### CÁCH 3: Test Local Trực Tiếp Trên Raspberry Pi CM4
SSH vào CM4 và chạy script gphoto2 độc lập:

```bash
ssh autotimelapse@100.64.0.2

# Chạy test trực tiếp bên trong container:
docker exec -it cm4_camera_agent python3 -c "
import gphoto2 as gp

cam = gp.Camera()
cam.init()
config = cam.get_config()

# Đổi ISO sang 3200
iso_w = config.get_child_by_name('iso')
iso_w.set_value('3200')
cam.set_config(config)

# Đọc lại xác minh
config2 = cam.get_config()
print('ISO hiện tại trên máy thật:', config2.get_child_by_name('iso').get_value())
"
```

---

## ⚡ ĐẶC TẢ MẠCH CẦU PHÂN ÁP TRỞ ADS1115 & QUẠT TẢN NHIỆT SẠC (GPIO 19)

### 1. Bảng Hệ Số Cầu Phân Áp Trở (ADC Resistor Dividers):

| Ngõ Đo / Chức Năng | Kênh Phần Cứng | Chân Chip ADS1115 | Điện Trở Trên ($R_1$) | Điện Trở Dưới ($R_2$) | Mã Trở SMD EIA-96 | Công Thức Hệ Số (Scale) | Hệ Số Scale Chuẩn |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Kênh 1 (Dự phòng)** | **Kênh 1** | **AIN0 (Chân 1)** | — | — | — | — | — |
| **Đo 6V / 5V Sạc** | **Kênh 2** | **AIN1 (Chân 2)** | **$20\text{ k}\Omega$** | **$10\text{ k}\Omega$** | `203` / `103` | $\frac{20 + 10}{10} = \frac{30}{10}$ | **`3.0000`** |
| **Đo Năng Lượng Solar** | **Kênh 3** | **AIN2 (Chân 3)** | **$100\text{ k}\Omega$** | **$13\text{ k}\Omega$** | `01D` / `12C` | $\frac{100 + 13}{13} = \frac{113}{13}$ | **`8.6923`** |
| **Đo Điện Áp Pin (Bat)** | **Kênh 4** | **AIN3 (Chân 4)** | **$47\text{ k}\Omega$** | **$4.7\text{ k}\Omega$** | `473` / `472` | $\frac{47 + 4.7}{4.7} = \frac{51.7}{4.7}$ | **`11.0000`** |

#### 📐 Công Thức Tính Điện Áp Thực Tế:
$$V_{in} = V_{\text{ADC\_pin}} \times \text{Scale}$$
- **Pin ($V_{bat}$ - Kênh 4 / AIN3):** $V_{\text{pin}} \times 11.0000 \quad \rightarrow 1.215\text{V} \times 11.0 = \mathbf{13.37\text{V}}$
- **Solar ($V_{solar}$ - Kênh 3 / AIN2):** $V_{\text{pin}} \times 8.6923 \quad \rightarrow 2.400\text{V} \times 8.6923 = \mathbf{20.86\text{V}}$
- **5V Sạc ($V_{in\_5V}$ - Kênh 2 / AIN1):** $V_{\text{pin}} \times 3.0000 \quad \rightarrow 1.667\text{V} \times 3.0 = \mathbf{5.00\text{V}}$

---

### 2. Logic Điều Khiển Quạt Tản Nhiệt Sạc (GPIO 19):

- **Ban ngày (07:00 ➔ 16:00):** Tự động **BẬT QUẠT (GPIO 19 = HIGH)** khi:
  - Kênh ADS 2 $> 4.5\text{V}$ **HOẶC** Điện áp Solar $> 15.0\text{V}$.
- **Ngoại lệ Ban Đêm (ngoài 07:00 - 16:00):** Vẫn **BẬT QUẠT (GPIO 19 = HIGH)** nếu:
  - Kênh ADS 2 $> 4.5\text{V}$ **VÀ** Điện áp Solar $> 15.0\text{V}$ (đang sạc nguồn ngoài ban đêm).
- **Trường hợp còn lại:** Tự động **TẮT QUẠT (GPIO 19 = LOW)**.

