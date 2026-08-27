# 📡 TÀI LIỆU KỸ THUẬT & GIAO THỨC MQTT CHO MODULE EC25
**Hệ thống AutoTimelapse Dual-Core (EC25 Controller + CM4 Core)**

---

## 1. VAI TRÒ VÀ NHIỆM VỤ CỦA EC25

EC25 hoạt động như **Bộ quản lý nguồn & Hẹn giờ RTC thông minh (Low-Power Power Controller)**:

1. **Duy trì kết nối mạng 4G/LTE**: Cung cấp đường truyền Internet cho toàn trạm (qua giao diện mạng USB `usb0` tới CM4) và kết nối MQTT liên tục về Cloud Server.
2. **Quản lý Nguồn cấp CM4 (MOSFET Power Switch)**:
   * Kích nguồn (Bật MOSFET) cho CM4 khi đến giờ chụp định kỳ theo mốc phút chẵn, hoặc khi nhận lệnh cưỡng bức từ Web UI.
   * Ngắt nguồn (Tắt MOSFET) cho CM4 sau khi CM4 hoàn tất chụp ảnh và shutdown an toàn (nhận diện qua việc ngắt kết nối chip USB).
   * **KHÔNG ngắt nguồn** khi `force_power_on=True` — trạng thái này được persist qua `ec25_state.json` để sống sót qua reboot.
3. **Quản lý Lịch chụp (Schedules) & Chu kỳ (Interval)**:
   * Lưu trữ cấu hình lịch chụp và chu kỳ vào bộ nhớ Flash để không bị mất khi cạn pin.
   * Tính toán thời gian ngủ sâu (Sleep / RTC Alarm) dựa theo lịch và chu kỳ căn mốc chẵn từ phút 00.
4. **Lắng nghe lệnh MQTT từ Server**: Nhận lệnh `power_on_cm4`, `power_off_cm4`, `set_interval`, `set_schedules`, v.v.
5. **Đồng bộ trạng thái `force_power_on`**: Kéo từ Server khi khởi động; nhận event `cycle_capture_done` từ CM4; cập nhật xuống `ec25_state.json`.

---

## 2. THÔNG SỐ KẾT NỐI MQTT BROKER

| Tham số | Giá trị |
| :--- | :--- |
| **MQTT Broker** | `mqtt.congnghetimelapse.com` |
| **Port** | `1883` |
| **Client ID** | `EC25_{CAMERA_CODE}` (VD: `EC25_CAM-KCSHPT`) |
| **Username** | `{CAMERA_CODE}` |
| **Password** | Mật khẩu MQTT riêng cho thiết bị |
| **KeepAlive** | 60 giây |
| **Clean Session** | False |

---

## 3. CÁC TOPIC MQTT CẦN XỬ LÝ

| Hướng | Topic | QoS | Mục đích |
| :--- | :--- | :---: | :--- |
| **EC25 Subscribe** | `camera/{CODE}/cmd` | 1 | Nhận lệnh điều khiển (power_on/off, set_interval, set_schedules…) |
| **EC25 Subscribe** | `camera/{CODE}/status` | 0 | Nhận event từ CM4 (VD: `cycle_capture_done`) |
| **EC25 Publish** | `camera/{CODE}/ack` | 1 | Phản hồi kết quả thực thi lệnh về Server |
| **EC25 Publish** | `camera/{CODE}/status` | 1 | Báo trạng thái Online/Offline (LWT) |
| **EC25 Publish** | `camera/{CODE}/data` | 1 | Telemetry EC25: sóng 4G, trạng thái CM4, `force_power_on` |
| **CM4 Publish** | `camera/{CODE}/data` | 1 | Telemetry CM4: nhiệt độ KK, độ ẩm KK, điện áp pin, solar, CPU, RAM |

> **Lưu ý:** Cả EC25 và CM4 đều publish lên cùng topic `camera/{CODE}/data`, phân biệt nhau qua field `node` (`"ec25"` hoặc `"cm4"`).
> EC25 subscribe `camera/{CODE}/status` để nhận event `cycle_capture_done` từ CM4 agent (publish với `retain=False`).

---

## 4. CHI TIẾT CÁC BẢN TIN CMD TỪ SERVER → EC25 (`camera/{CODE}/cmd`)

### 🔹 4.1. Cưỡng Bức Bật Nguồn CM4 (`power_on_cm4`)

Được gửi khi người dùng bấm **"Cưỡng bức Bật CM4"** trên Web UI (Live View, chỉnh thông số…).

**Server gửi xuống:**
```json
{
  "command": "power_on_cm4",
  "request_id": "req-uuid-001",
  "payload": {}
}
```

**Hành động của EC25:**
1. Đóng MOSFET cấp nguồn cho CM4 ngay lập tức.
2. Set `force_power_on = True` → lưu vào `ec25_state.json`.
3. Gửi ACK về `camera/{CODE}/ack`:

```json
{
  "type": "power_on_cm4",
  "request_id": "req-uuid-001",
  "status": "ok",
  "data": {
    "cm4_power_state": "running",
    "camera_power": "on",
    "force_power_on": true,
    "message": "CM4 is now RUNNING (force-on mode)"
  }
}
```

---

### 🔹 4.2. Tắt Nguồn CM4 (`power_off_cm4`)

**Server gửi xuống:**
```json
{
  "command": "power_off_cm4",
  "request_id": "req-uuid-002",
  "payload": {}
}
```

**Hành động của EC25:**
1. Ngắt MOSFET cắt nguồn CM4.
2. Reset `force_power_on = False` → lưu vào `ec25_state.json`.
3. EC25 trở lại chế độ chu kỳ bình thường.
4. Gửi ACK:

```json
{
  "type": "power_off_cm4",
  "request_id": "req-uuid-002",
  "status": "ok",
  "data": {
    "cm4_power_state": "off",
    "camera_power": "off",
    "force_power_on": false,
    "message": "CM4 is now OFF"
  }
}
```

---

### 🔹 4.3. Cập Nhật Chu Kỳ (`set_interval`)

```json
{
  "command": "set_interval",
  "request_id": "req-uuid-003",
  "payload": {
    "capture_interval_sec": 300
  }
}
```

EC25 lưu chu kỳ vào Flash, tính lại thời điểm ngủ/thức kế tiếp theo mốc phút chẵn.

---

### 🔹 4.4. Cập Nhật Lịch Chụp (`set_schedules`)

```json
{
  "command": "set_schedules",
  "request_id": "req-uuid-004",
  "payload": {
    "schedules": [
      {
        "name": "Ca sáng",
        "start_time": "06:00",
        "end_time": "12:00",
        "interval_sec": 300,
        "days_of_week": [1, 2, 3, 4, 5, 6, 7],
        "is_enabled": true
      }
    ]
  }
}
```

---

## 5. EVENT TỪ CM4 → EC25 (`camera/{CODE}/status`)

Khi CM4 hoàn tất một chu kỳ chụp ảnh, nó publish event lên `status` topic để EC25 đồng bộ trạng thái:

```json
{
  "online": true,
  "node": "cm4",
  "event": "cycle_capture_done",
  "triggered_by": "schedule",
  "taken_at": "2026-08-23T09:00:02.123456+00:00",
  "media_count": 1
}
```

**EC25 xử lý event này:**

| `force_power_on` | Hành động EC25 |
| :---: | :--- |
| `true` | Log: CM4 GIỮ ONLINE, **không ngắt nguồn** theo chu kỳ |
| `false` | Log: CM4 sắp shutdown — EC25 chờ detect USB mất kết nối rồi ngắt MOSFET |

---

## 6. FILE STATE DÙNG CHUNG: `ec25_state.json`

Đường dẫn: `/app/offline_queue/ec25_state.json`

File JSON nhỏ, **cầu nối giữa EC25 và CM4**, persist qua reboot. Cả hai process đều đọc/ghi theo cơ chế merge.

```json
{
  "force_power_on": false,
  "missed_capture_flag": false,
  "last_capture_ts": "2026-08-23T09:00:02+00:00",
  "last_updated_by": "cm4_agent"
}
```

Chỉ có **2 field điều khiển logic** thực sự:

| Field | Ai dùng | Ý nghĩa |
| :--- | :--- | :--- |
| `force_power_on` | **EC25 & CM4** | `true` → CM4 đang bật cưỡng bức, EC25 không được ngắt nguồn sau chu kỳ |
| `missed_capture_flag` | **CM4** | `true` → có mốc chụp bị bỏ lỡ, CM4 sẽ chụp bù ngay khi boot lại |

Các field còn lại (`last_capture_ts`, `last_updated_by`, v.v.) chỉ là **metadata** để debug, không ảnh hưởng logic.

---

## 7. THUẬT TOÁN ĐỒNG BỘ CHU KỲ & PHÂN TÁCH TRẠNG THÁI

### 🔹 7.1. Nguyên Tắc Chu Kỳ Căn Mốc Phút Chẵn (Aligned Intervals)

Tất cả chu kỳ được căn chỉnh theo phút 00 của mỗi giờ (Múi giờ Việt Nam **UTC+7**):

| Chu kỳ | Các mốc chụp trong giờ |
| :---: | :--- |
| 5 phút (300s) | :00, :05, :10, :15, :20, :25, :30, :35, :40, :45, :50, :55 |
| 10 phút (600s) | :00, :10, :20, :30, :40, :50 |
| 15 phút (900s) | :00, :15, :30, :45 |
| 20 phút (1200s) | :00, :20, :40 |
| 30 phút (1800s) | :00, :30 |
| 60 phút (3600s) | :00 (đầu giờ) |

---

### 🔹 7.2. State Machine: Hai Chế Độ Hoạt Động

```
                    ┌──────────────────────────────────────────┐
                    │           ec25_state.json                │
                    │  force_power_on: true/false              │
                    │  missed_capture_flag: true/false         │
                    └───────────────┬──────────────────────────┘
                                    │ đọc/ghi chung
                    ┌───────────────┼──────────────────────────┐
                    │               │                          │
             ┌──────▼──────┐        │               ┌──────────▼────────┐
             │  EC25 Agent │        │               │   CM4 Main Agent  │
             └──────┬──────┘        │               └──────────┬────────┘
                    │               │                          │
     ┌──────────────┼───────────────┼──────────────────────────┼──────────────┐
     │              │               │                          │              │
     │  BOOT EC25:  │               │          BOOT CM4:       │              │
     │  pull_server_│               │          _smart_boot_    │              │
     │  config()    │               │          task()          │              │
     │    │         │               │            │             │              │
     │    ▼         │               │            ▼             │              │
     │  force_on?   │               │     force_on=True?       │              │
     │  ├─ True  ───┼───────────────┼──►  INTERACTIVE MODE     │              │
     │  │  (không   │               │     (giữ online)         │              │
     │  │   cắt)    │               │     clear missed_flag    │              │
     │  └─ False ───┼───────────────┼──►  CYCLE-EC25 MODE      │              │
     │              │               │     ├─ missed_flag=True?  │              │
     │              │               │     │   → chụp bù ngay    │              │
     │              │               │     └─ on_aligned_slot?  │              │
     │              │               │         → chụp ngay      │              │
     └──────────────┘               └──────────────────────────┘
```

---

### 🔹 7.3. Vòng Đời `missed_capture_flag`

```
capture_loop bắt đầu sleep chờ mốc kế tiếp
    │
    ▼
SET missed_capture_flag = True  (lưu ra disk)
    │
    ├──► [CM4 tắt bình thường giữa chu kỳ]
    │         │
    │         ▼
    │    CM4 boot lại (do EC25 timer)
    │         │
    │         ▼
    │    smart_boot_task: đọc flag=True
    │         │
    │         ▼
    │    [MISSED-CAPTURE] → chụp bù ngay
    │         │
    │         ▼
    │    upload_capture() xong
    │         │
    │         ▼
    │    CLEAR missed_capture_flag = False
    │
    └──► [CM4 không bị tắt, sleep xong bình thường]
              │
              ▼
         upload_capture() đúng mốc
              │
              ▼
         CLEAR missed_capture_flag = False
```

---

### 🔹 7.4. Nhận Diện Chế Độ Khi CM4 Boot (`_smart_boot_task`)

```
CM4 khởi động
    │
    ├─[BƯỚC 1] pull_server_config() → lấy force_power_on
    │
    ├─[BƯỚC 2] force_power_on = True?
    │   ├─ YES → operating_mode = "interactive"
    │   │         power_on camera
    │   │         clear missed_capture_flag
    │   │         save ec25_state(force_power_on=True)
    │   │         publish_telemetry() → XONG (giữ online)
    │   └─ NO  → save ec25_state(force_power_on=False)
    │
    ├─[BƯỚC 3] Chờ 3s nhận lệnh MQTT tức thì
    │   ├─ Nhận power_on_cm4 → operating_mode = "interactive"
    │   │   save ec25_state(force_power_on=True) → XONG
    │   └─ Không có → tiếp tục
    │
    ├─[BƯỚC 4] operating_mode = "auto_schedule"
    │           get_active_schedule_slot()
    │
    ├─[BƯỚC 5] missed_capture_flag = True?
    │   ├─ YES & in_schedule → [MISSED-CAPTURE] upload_capture(triggered_by="schedule")
    │   └─ YES & out_schedule → clear flag, publish_telemetry
    │
    ├─[BƯỚC 6] is_active & is_on_aligned_slot(tolerance=300s)?
    │   ├─ YES → [CYCLE-EC25] upload_capture(triggered_by="schedule")
    │   └─ NO  → capture_loop thread sẽ xử lý mốc tiếp theo
    │
    ├─[BƯỚC 7] operating_mode chuyển sang "interactive" trong lúc chụp?
    │   └─ YES → save ec25_state(force_power_on=True) → XONG (giữ online)
    │
    └─[BƯỚC 8] auto_shutdown_after_capture?
        ├─ YES → shutdown_host_cm4() (EC25 sẽ detect USB lost & ngắt MOSFET)
        └─ NO  → daemon mode tiếp tục chạy
```

---

## 8. TELEMETRY `camera/{CODE}/data` — Phân Biệt Theo Node

Cả EC25 và CM4 đều publish lên cùng topic `camera/{CODE}/data`, phân biệt bằng field **`node`**.

### 🔹 8.1. EC25 Publish (`node: "ec25"`) — Khi CM4 đang TẮT

EC25 **không có I2C** nên chỉ gửi được những gì nó thực sự biết:
- Sóng 4G đo qua AT command (`AT+CSQ`)
- Trạng thái CM4 (do chính nó quản lý MOSFET)
- Trạng thái `force_power_on` (từ `ec25_state.json`)

```json
{
  "camera_code": "CAM-KCSHPT",
  "node": "ec25",
  "cm4_power_state": "off",
  "force_power_on": false,
  "sim_active_node": "ec25",
  "sim_signal_dbm": -72,
  "firmware_version": "cm4-power-agent-v2.0",
  "timestamp": "2026-08-23T09:00:00+07:00"
}
```

> ⚠️ EC25 **không gửi** `battery_voltage`, `solar_voltage`, `temperature_c`, `humidity_percent`, `is_charging` — EC25 không có I2C để đọc các cảm biến này. Chỉ CM4 mới đọc được qua bus I2C gắn trực tiếp.

---

### 🔹 8.2. CM4 Publish (`node: "cm4"`) — Khi CM4 đang CHẠY

CM4 đo cảm biến I2C (SHT20 nhiệt độ/độ ẩm không khí, ADS1115 điện áp), CPU, RAM, GPIO camera.

```json
{
  "camera_code": "CAM-KCSHPT",
  "node": "cm4",
  "cm4_power_state": "running",
  "sim_active_node": "cm4",
  "temperature_c": 38.5,
  "humidity_percent": 65,
  "battery_voltage": 12.41,
  "battery_percent": 90,
  "solar_voltage": 17.1,
  "solar_percent": 88,
  "is_charging": true,
  "cpu_percent": 12.4,
  "memory_percent": 34.2,
  "sim_signal_dbm": -69,
  "sim_source": "cm4_modem",
  "camera_gpio_power": true,
  "camera_hw_mode": "real_usb",
  "firmware_version": "cm4-autotimelapse-v2.0",
  "timestamp": "2026-08-23T09:00:05+07:00"
}
```

**Phân bổ cảm biến theo node:**

| Field | EC25 | CM4 | Nguồn |
| :--- | :---: | :---: | :--- |
| `sim_signal_dbm` | ✅ | ✅ | EC25 AT command `AT+CSQ` |
| `cm4_power_state` | ✅ | ✅ | EC25 quản lý MOSFET; CM4 tự báo |
| `force_power_on` | ✅ | ✅ | `ec25_state.json` |
| `battery_voltage` / `battery_percent` | ❌ | ✅ | **ADS1115 I2C — chỉ CM4 đọc được** |
| `solar_voltage` / `solar_percent` | ❌ | ✅ | **ADS1115 I2C — chỉ CM4 đọc được** |
| `temperature_c` | ❌ | ✅ | **SHT20 I2C — chỉ CM4 đọc được** |
| `humidity_percent` | ❌ | ✅ | **SHT20 I2C — chỉ CM4 đọc được** |
| `is_charging` | ❌ | ✅ | **ADS1115 I2C — chỉ CM4 đọc được** |
| `cpu_percent` | ❌ | ✅ | CPU CM4 |
| `memory_percent` | ❌ | ✅ | RAM CM4 |
| `camera_gpio_power` | ❌ | ✅ | GPIO 16 CM4 |

---

## 9. LOG MARKERS ĐỂ TRACE TRẠNG THÁI

Mỗi nhánh quyết định đều có log marker riêng giúp debug nhanh qua file log:

| Marker | File | Ý nghĩa |
| :--- | :---: | :--- |
| `[FORCE-ON]` | CM4 & EC25 | Phát hiện / kích hoạt chế độ cưỡng bức |
| `[CYCLE-EC25]` | CM4 & EC25 | Hoạt động theo chu kỳ EC25 |
| `[MISSED-CAPTURE]` | CM4 | Phát hiện có mốc chụp bị bỏ lỡ, đang chụp bù |
| `[FLAG:SET]` | CM4 | `missed_capture_flag` được đặt = True |
| `[FLAG:CLEAR]` | CM4 | `missed_capture_flag` được xoá = False |
| `[EC25 STATE]` | CM4 & EC25 | Đọc/ghi `ec25_state.json` |
| `[EC25 CONFIG SYNC]` | EC25 | Kéo `force_power_on` từ server thành công |
| `[AUTO SHUTDOWN]` | CM4 | CM4 chuẩn bị shutdown sau chu kỳ |
| `[SMART BOOT]` | CM4 | Bắt đầu logic nhận diện chế độ khi boot |

---

*Tài liệu cập nhật lần cuối: 2026-08-23 — phản ánh cơ chế đồng bộ v2 (missed_capture_flag + ec25_state.json)*
