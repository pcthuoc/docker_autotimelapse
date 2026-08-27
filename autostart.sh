#!/bin/sh
### BEGIN INIT INFO
# Provides:          autotimelapse
# Required-Start:    $local_fs $network
# Required-Stop:     $local_fs $network
# Default-Start:     2 3 4 5
# Default-Stop:      0 1 6
# Short-Description: AutoTimelapse CM4 Power & MQTT Agent
### END INIT INFO

DAEMON=/usrdata/MQTT_Client
CONFIG=/usrdata/mqtt_config.json
PIDFILE=/var/run/mqtt_client.pid
LOGFILE=/tmp/mqtt_client.log

case "$1" in
    start)
        echo "🚀 Đang khởi động AutoTimelapse CM4 Agent..."
        if [ -x "$DAEMON" ] && [ -f "$CONFIG" ]; then
            # Ghi log tạm thời lên RAM (/tmp - không tốn Flash, tự xóa khi tắt nguồn)
            start-stop-daemon -S -b -m -p "$PIDFILE" -a /bin/sh -- -c "$DAEMON -c $CONFIG > $LOGFILE 2>&1"
            echo "✅ AutoTimelapse Agent đã chạy nền (PID: $(cat $PIDFILE 2>/dev/null), Log trên RAM: $LOGFILE)!"
        else
            echo "❌ Không tìm thấy $DAEMON hoặc $CONFIG"
        fi
        ;;
    stop)
        echo "🛑 Đang dừng AutoTimelapse CM4 Agent..."
        killall -9 MQTT_Client 2>/dev/null
        rm -f "$PIDFILE"
        echo "✅ Đã dừng AutoTimelapse Agent."
        ;;
    restart)
        $0 stop
        sleep 2
        $0 start
        ;;
    status)
        if pidof MQTT_Client >/dev/null 2>&1; then
            echo "🟢 AutoTimelapse Agent đang CHẠY NỀN (PID: $(pidof MQTT_Client))"
        else
            echo "🔴 AutoTimelapse Agent ĐÃ DỪNG"
        fi
        ;;
    log)
        echo "📄 Đang theo dõi LOG TRỰC TIẾP (Bấm Ctrl+C để thoát xem log):"
        if [ -f "$LOGFILE" ]; then
            tail -f -n 40 "$LOGFILE"
        else
            echo "ℹ️ Đang chờ tạo log tại $LOGFILE..."
            tail -f "$LOGFILE" 2>/dev/null
        fi
        ;;
    *)
        echo "Cách dùng: $0 {start|stop|restart|status|log}"
        exit 1
        ;;
esac

exit 0
