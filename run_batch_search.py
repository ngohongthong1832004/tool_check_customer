#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script để chạy tìm kiếm hàng loạt
Cách dùng: python run_batch_search.py
"""

import subprocess
import sys
from datetime import datetime


# ===========================================
# CẤU HÌNH: SỬA Ở ĐÂY
# ===========================================

# Danh sách các giá trị cần tìm
QUERIES = [
    "0305311225",
    "3502522319", 
    "1101815829",
    "0315190604",
    "0304043037",
]

# Loại tìm kiếm: tax, id (CMND), tel, chassis, engine, name
SEARCH_TYPE = "tax"

# ===========================================


def run_search(query, search_type):
    """Chạy lệnh tìm kiếm cho 1 query"""
    cmd = [
        sys.executable,  # python
        "./search_customer_cascade.py",
        "--query", query,
        "--type", search_type
    ]
    
    print(f"  → Chạy lệnh: {' '.join(cmd)}")
    
    result = subprocess.run(cmd, capture_output=False, text=True)
    return result.returncode == 0


def main():
    total = len(QUERIES)
    success_count = 0
    failed_queries = []
    
    print(f"\n{'='*60}")
    print(f"BẮT ĐẦU TÌM KIẾM HÀNG LOẠT: {total} mã")
    print(f"Loại tìm kiếm: {SEARCH_TYPE}")
    print(f"Thời gian bắt đầu: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")
    
    for idx, query in enumerate(QUERIES, start=1):
        print(f"\n[{idx}/{total}] Đang tìm: {query}")
        print("-" * 60)
        
        success = run_search(query, SEARCH_TYPE)
        
        if success:
            print(f"  ✓ Hoàn thành: {query}")
            success_count += 1
        else:
            print(f"  ✗ Lỗi khi tìm: {query}")
            failed_queries.append(query)
        
        print()
    
    # Tóm tắt
    print(f"\n{'='*60}")
    print(f"HOÀN TẤT TẤT CẢ")
    print(f"{'='*60}")
    print(f"Tổng số: {total}")
    print(f"Thành công: {success_count}")
    print(f"Thất bại: {len(failed_queries)}")
    
    if failed_queries:
        print(f"\nCác mã bị lỗi:")
        for q in failed_queries:
            print(f"  - {q}")
    
    print(f"\nThời gian kết thúc: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
