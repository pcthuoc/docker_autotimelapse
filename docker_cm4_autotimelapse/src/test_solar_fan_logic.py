#!/usr/bin/env python3
"""
test_solar_fan_logic.py — Unit test toàn bộ các kịch bản của SolarChargingFanController
"""

import sys
from solar_fan_controller import SolarChargingFanController

def test_suite():
    ctrl = SolarChargingFanController(pin=19)

    test_cases = [
        # (case_name, v_ch2, solar_v, hour, expected_fan)
        ("1. Ban ngày (10h sáng), Kênh 2=5.0V (>4.5V), Solar=18V (>15V)", 5.0, 18.0, 10, True),
        ("2. Ban ngày (12h trưa), Kênh 2=4.8V (>4.5V), Solar=12V (<=15V)", 4.8, 12.0, 12, True),
        ("3. Ban ngày (14h chiều), Kênh 2=3.0V (<=4.5V), Solar=19V (>15V)", 3.0, 19.0, 14, True),
        ("4. Ban ngày (09h sáng), Kênh 2=2.0V (<=4.5V), Solar=10V (<=15V)", 2.0, 10.0, 9, False),
        ("5. Ban đêm (20h tối), Kênh 2=2.0V (<=4.5V), Solar=0V (<=15V)", 2.0, 0.0, 20, False),
        ("6. Ban đêm (23h đêm), Kênh 2=5.0V (>4.5V), Solar=0V (<=15V) - Chưa đủ ngoại lệ", 5.0, 0.0, 23, False),
        ("7. Ban đêm (02h sáng), Kênh 2=2.0V (<=4.5V), Solar=18V (>15V) - Chưa đủ ngoại lệ", 2.0, 18.0, 2, False),
        ("8. NGOẠI LỆ BAN ĐÊM (21h tối), Kênh 2=4.9V (>4.5V) VÀ Solar=17V (>15V)", 4.9, 17.0, 21, True),
        ("9. NGOẠI LỆ BAN ĐÊM (04h sáng), Kênh 2=5.2V (>4.5V) VÀ Solar=16V (>15V)", 5.2, 16.0, 4, True),
        ("10. Biên giờ bắt đầu (07:00), Kênh 2=4.6V (>4.5V)", 4.6, 10.0, 7, True),
        ("11. Biên giờ kết thúc (16:00 -> tính là ngoài giờ), Kênh 2=4.6V, Solar=10V", 4.6, 10.0, 16, False),
    ]

    all_passed = True
    print("=" * 80)
    print("🧪 BẮT ĐẦU KIỂM THỬ TOÀN BỘ MA TRẬN LOGIC QUẠT SẠC GPIO 19")
    print("=" * 80)

    for name, v_ch2, sol_v, hour, expected in test_cases:
        run, reason, _ = ctrl.evaluate(v_ch2, sol_v, custom_hour=hour)
        status = "✅ PASS" if run == expected else "❌ FAIL"
        if run != expected:
            all_passed = False
        print(f"\n{status} | {name}")
        print(f"       Kết quả: Quạt={'BẬT (HIGH)' if run else 'TẮT (LOW)'} (Kỳ vọng: {'BẬT' if expected else 'TẮT'})")
        print(f"       Lý do: {reason}")

    print("\n" + "=" * 80)
    if all_passed:
        print("🎉 TẤT CẢ 11/11 TEST CASES ĐỀU ĐẠT CHUẨN 100%!")
    else:
        print("❌ CÓ TEST CASE THẤT BẠI!")
    print("=" * 80)

if __name__ == "__main__":
    test_suite()
