#!/usr/bin/env bash
# ==============================================================================
# AutoTimelapse Headscale Management Helper Script
# ==============================================================================
set -e

CONTAINER="headscale"

function show_help() {
    echo "======================================================================"
    echo " 🌐 AutoTimelapse Headscale CLI Helper"
    echo "======================================================================"
    echo " Cách sử dụng: ./headscale.sh <lệnh> [tham số]"
    echo ""
    echo " Lệnh Quản lý Máy / Nodes:"
    echo "   nodes                   Liệt kê toàn bộ máy đang kết nối và IP VPN"
    echo "   register <key> [user_id] Đăng ký máy thủ công bằng Machine Key"
    echo "   delete <node_id>        Xóa 1 máy khỏi mạng VPN (vd: ./headscale.sh delete 1)"
    echo ""
    echo " Lệnh Quản lý Pre-Auth Keys (Dành cho 10-20 máy kết nối tự động):"
    echo "   key [user_id] [exp]     Tạo Reusable Key 365 ngày (vd: ./headscale.sh key 1 8760h)"
    echo "   keys [user_id]          Xem danh sách Pre-Auth Keys đã cấp"
    echo ""
    echo " Lệnh Quản lý Người dùng / Namespaces:"
    echo "   user list               Xem danh sách User"
    echo "   user create <name>      Tạo User mới (vd: ./headscale.sh user create camera)"
    echo "   user delete <name>      Xóa User"
    echo ""
    echo " Lệnh Web UI & API:"
    echo "   ui-key                  Tạo API Key để đăng nhập Headscale Web UI (Port 9080)"
    echo "   routes                  Xem danh sách Subnet Routes"
    echo ""
    echo " Lệnh Tiện ích:"
    echo "   logs                    Xem logs thời gian thực của Headscale"
    echo "   restart                 Khởi động lại dịch vụ Headscale & Web UI"
    echo "======================================================================"
}

CMD="$1"
shift || true

case "$CMD" in
    nodes|list)
        docker exec "$CONTAINER" headscale nodes list "$@"
        ;;
    register)
        if [ -z "$1" ]; then
            echo "❌ Cú pháp: ./headscale.sh register <machine-key> [user_id]"
            exit 1
        fi
        USER_ID="${2:-1}"
        docker exec "$CONTAINER" headscale nodes register --user "$USER_ID" --key "$1"
        ;;
    delete|rm)
        if [ -z "$1" ]; then
            echo "❌ Cú pháp: ./headscale.sh delete <node_id>"
            exit 1
        fi
        docker exec "$CONTAINER" headscale nodes delete -i "$1" -f
        ;;
    key)
        USER_INPUT="${1:-1}"
        EXPIRY="${2:-8760h}"
        if ! [[ "$USER_INPUT" =~ ^[0-9]+$ ]]; then
            USER_ID="1"
        else
            USER_ID="$USER_INPUT"
        fi
        echo "🔑 Đang tạo Reusable Pre-Auth Key cho User ID $USER_ID (hạn $EXPIRY)..."
        docker exec "$CONTAINER" headscale preauthkeys create --user "$USER_ID" --reusable --expiration "$EXPIRY"
        ;;
    keys)
        USER_INPUT="${1:-1}"
        if ! [[ "$USER_INPUT" =~ ^[0-9]+$ ]]; then
            USER_ID="1"
        else
            USER_ID="$USER_INPUT"
        fi
        docker exec "$CONTAINER" headscale preauthkeys list --user "$USER_ID"
        ;;
    user)
        SUB_CMD="$1"
        shift || true
        case "$SUB_CMD" in
            list)
                docker exec "$CONTAINER" headscale users list
                ;;
            create|add)
                if [ -z "$1" ]; then
                    echo "❌ Cú pháp: ./headscale.sh user create <username>"
                    exit 1
                fi
                docker exec "$CONTAINER" headscale users create "$1"
                ;;
            delete|rm)
                if [ -z "$1" ]; then
                    echo "❌ Cú pháp: ./headscale.sh user delete <username>"
                    exit 1
                fi
                docker exec "$CONTAINER" headscale users delete "$1" -f
                ;;
            *)
                echo "❌ Cú pháp: ./headscale.sh user [list|create|delete]"
                ;;
        esac
        ;;
    ui-key|apikey)
        echo "🌐 Đang tạo API Key cho Headscale Web UI (hạn 1 năm)..."
        docker exec "$CONTAINER" headscale apikeys create --expiration 8760h
        ;;
    routes)
        docker exec "$CONTAINER" headscale routes list
        ;;
    logs)
        docker logs -f "$CONTAINER"
        ;;
    restart)
        docker compose -f /root/UI_autotimelapse/headscale/docker-compose.yml restart
        ;;
    *)
        show_help
        ;;
esac
