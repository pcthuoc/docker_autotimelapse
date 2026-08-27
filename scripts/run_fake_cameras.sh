#!/usr/bin/env bash
# ==============================================================================
# Script điều khiển 3 Camera Giả lập (Fake Multi-Camera Simulator)
# Tự động gửi Telemetry, Ảnh Timelapse và Phản hồi Live View cho 3 Camera Quốc Tử Giám
#
# Cách dùng:
#   ./scripts/run_fake_cameras.sh start   -> Khởi chạy ngầm (Reboot/Kill sẽ tự mất)
#   ./scripts/run_fake_cameras.sh stop    -> Dừng giả lập
#   ./scripts/run_fake_cameras.sh status  -> Kiểm tra trạng thái
#   ./scripts/run_fake_cameras.sh logs    -> Xem nhật ký thời gian thực
# ==============================================================================

CONTAINER_NAME="fake_cameras_simulator"
IMAGE_NAME="atl-site:latest"
NETWORK_NAME="ui_autotimelapse_app-net"
SCRIPT_PATH="/root/UI_autotimelapse/repo/backend/fake_cameras_simulator.py"

case "$1" in
  start)
    if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
      echo "⚠️  Simulator đang chạy rồi (Container: ${CONTAINER_NAME})"
      exit 0
    fi

    echo "🚀 Đang khởi chạy 5 Camera giả lập (Quốc Tử Giám + Hưng Miếu) trong nền..."
    docker run -d \
      --name "${CONTAINER_NAME}" \
      --rm \
      --network "${NETWORK_NAME}" \
      --network "ui_autotimelapse_seaweed-net" \
      -v "/root/UI_autotimelapse/repo/backend:/app" \
      -e "MQTT_BROKER=mosquitto" \
      -e "MQTT_PORT=1883" \
      -e "SERVER_BASE=http://site:8000" \
      -e "CAPTURE_INTERVAL=60" \
      -e "TELEMETRY_INTERVAL=30" \
      "${IMAGE_NAME}" \
      python /app/fake_cameras_simulator.py

    sleep 2
    if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
      echo "✅ Đã khởi chạy thành công 3 Camera giả lập!"
      echo "👉 Xem log bằng: ./scripts/run_fake_cameras.sh logs"
      echo "👉 Dừng bằng:     ./scripts/run_fake_cameras.sh stop"
    else
      echo "❌ Lỗi khởi động container. Xem log:"
      docker logs "${CONTAINER_NAME}"
    fi
    ;;

  stop)
    echo "🛑 Đang dừng và dọn dẹp giả lập..."
    docker stop "${CONTAINER_NAME}" 2>/dev/null || true
    echo "✅ Đã dừng giả lập."
    ;;

  status)
    if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
      echo "🟢 Simulator ĐANG CHẠY (Container: ${CONTAINER_NAME})"
      docker ps --filter "name=${CONTAINER_NAME}" --format "table {{.ID}}\t{{.Names}}\t{{.Status}}\t{{.RunningFor}}"
    else
      echo "⚪ Simulator ĐÃ TẮT."
    fi
    ;;

  logs)
    docker logs -f "${CONTAINER_NAME}"
    ;;

  *)
    echo "Cách dùng: $0 {start|stop|status|logs}"
    exit 1
    ;;
esac
