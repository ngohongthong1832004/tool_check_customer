#!/usr/bin/env python3
# -*- coding: utf-8 -*-


import os
import re
import json
import time
import argparse
from glob import glob

import pandas as pd
from rapidfuzz import fuzz


# ==========================
# CONFIG
# ==========================

DATA_FOLDER = "./data"
MAPPING_FILE = "mapping.json"
OUT_BASE = "./search_results_canhan"
FUZZY_NAME_THRESHOLD = 85


# ==========================
# NORMALIZERS
# ==========================

def norm_code(x):
    if x is None or pd.isna(x):
        return ""
    return str(x).strip().upper()

def normalize_phone(x):
    if x is None or pd.isna(x):
        return ""
    s = re.sub(r"[^\d]", "", str(x))
    if s.startswith("84") and len(s) >= 10:
        s = "0" + s[2:]
    return s

def normalize_plate(x):
    if x is None or pd.isna(x):
        return ""
    s = str(x).upper()
    s = re.sub(r"[\s\.\-]", "", s)
    return s

def normalize_name(x):
    if x is None or pd.isna(x):
        return ""
    s = str(x).lower() 
    s = re.sub(r"\s+", " ", s)
    return s.strip()

def normalize_id_no(x):
    if x is None or pd.isna(x):
        return ""
    s = str(x).strip()
    s = re.sub(r"[\s\.\-]", "", s)
    return s

def normalize_tax_no(x):
    if x is None or pd.isna(x):
        return ""
    s = str(x).strip()
    s = re.sub(r"[\s\.\-]", "", s)
    return s


# ==========================
# MAPPING
# ==========================

def load_mapping():
    if not os.path.exists(MAPPING_FILE):
        print("⚠ Không tìm thấy", MAPPING_FILE, "-> chỉ auto-guess mapping đơn giản.")
        return {}
    with open(MAPPING_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    mapping_per_file = data.get("mapping_per_file", {})
    print(f"✅ Đã load mapping cho {len(mapping_per_file)} file từ {MAPPING_FILE}")
    return mapping_per_file


def build_effective_mapping_for_file(fname, df, mapping_from_json):
    """
    mapping_from_json: mapping lấy từ file mapping.json (per file)
    df: DataFrame của file đang xét

    Trả về mapping cuối cùng: { original_col : target_field }
    target_field gồm:
      - tax_no, id_no, chassis_no, engine_no, tel, number_plate, customer_name, customer_code
    """
    mapping = dict(mapping_from_json.get(fname, {}))  # copy

    for col in df.columns:
        if col in mapping:
            continue
        low = col.lower().replace(" ", "").replace("_", "").replace(".", "")
        # id / tax
        if low == "dmsidcardno":
            mapping[col] = "id_no"
        elif low == "taxregnodms":
            mapping[col] = "tax_no"
        # chassis / engine / tel / name / plate / customer_code
        elif "chassis" in low:
            mapping[col] = "chassis_no"
        elif "engine" in low:
            mapping[col] = "engine_no"
        elif low in ("tel","telephone","phone") or "mobile" in low:
            mapping[col] = "tel"
        elif "numberplate" in low or "plate" in low:
            mapping[col] = "number_plate"
        elif "customername" in low or "customernamedms" in low:
            mapping[col] = "customer_name"
        elif "customercode" in low:
            mapping[col] = "customer_code"
    return mapping


def get_mapped_value(mapping, row, target_fields):
    for col, mapped in mapping.items():
        if mapped in target_fields and col in row.index:
            v = row[col]
            if v is not None and str(v).strip() != "":
                return v
    return None


def extract_identifiers(mapping, row):
    """
    Lấy tất cả định danh (đã normalize) từ 1 dòng.
    """
    out = {}
    v = get_mapped_value(mapping, row, ["tax_no"])
    out["tax_no"] = normalize_tax_no(v) if v is not None else ""
    v = get_mapped_value(mapping, row, ["id_no"])
    out["id_no"] = normalize_id_no(v) if v is not None else ""
    v = get_mapped_value(mapping, row, ["chassis_no"])
    out["chassis_no"] = norm_code(v) if v is not None else ""
    v = get_mapped_value(mapping, row, ["engine_no"])
    out["engine_no"] = norm_code(v) if v is not None else ""
    v = get_mapped_value(mapping, row, ["tel"])
    out["tel"] = normalize_phone(v) if v is not None else ""
    v = get_mapped_value(mapping, row, ["number_plate"])
    out["number_plate"] = normalize_plate(v) if v is not None else ""
    v = get_mapped_value(mapping, row, ["customer_code"])
    out["customer_code"] = norm_code(v) if v is not None else ""
    return out


# ==========================
# MATCHING
# ==========================

def row_match_primary(row, mapping, raw_query, qtype):
    """
    So khớp trực tiếp theo query (PHASE 1)
    """
    if qtype == "tax":
        qv = normalize_tax_no(raw_query)
        v = get_mapped_value(mapping, row, ["tax_no"])
        if v and normalize_tax_no(v) == qv:
            return True, "tax_exact"

    elif qtype == "id":
        qv = normalize_id_no(raw_query)
        v = get_mapped_value(mapping, row, ["id_no"])
        if v and normalize_id_no(v) == qv:
            return True, "id_exact"

    elif qtype == "chassis":
        qv = norm_code(raw_query)
        v = get_mapped_value(mapping, row, ["chassis_no"])
        if v and norm_code(v) == qv:
            return True, "chassis_exact"

    elif qtype == "engine":
        qv = norm_code(raw_query)
        v = get_mapped_value(mapping, row, ["engine_no"])
        if v and norm_code(v) == qv:
            return True, "engine_exact"

    elif qtype == "tel":
        qv = normalize_phone(raw_query)
        v = get_mapped_value(mapping, row, ["tel"])
        if v and normalize_phone(v) == qv:
            return True, "tel_exact"

    elif qtype == "name":
        qv = normalize_name(raw_query)
        v = get_mapped_value(mapping, row, ["customer_name"])
        if v:
            sim = fuzz.token_sort_ratio(normalize_name(v), qv)
            if sim >= FUZZY_NAME_THRESHOLD:
                return True, f"name_fuzzy({sim})"

    elif qtype == "auto":
        # ưu tiên tax -> id -> chassis -> engine -> tel -> name
        for t in ["tax","id","chassis","engine","tel","name"]:
            ok, reason = row_match_primary(row, mapping, raw_query, t)
            if ok:
                return True, reason

    return False, None


def row_match_secondary(row_ids, anchors):
    """
    So khớp phase 2: dùng bộ định danh anchors (tập hợp từ phase1)
    row_ids: dict từ extract_identifiers()
    anchors: dict field -> set(values)

    Trả về (True/False, reason)
    """
    # Thứ tự ưu tiên
    order = [
        ("chassis_no", "link_chassis"),
        ("engine_no", "link_engine"),
        ("number_plate", "link_plate"),
        ("tel", "link_tel"),
        ("tax_no", "link_tax"),
        ("id_no", "link_id"),
        ("customer_code", "link_customer_code"),
    ]
    for field, reason in order:
        val = row_ids.get(field, "")
        if val and val in anchors.get(field, set()):
            return True, reason
    return False, None


# ==========================
# MAIN
# ==========================

def main():
    parser = argparse.ArgumentParser(description="Search 1 customer across Excel files (cascading by chassis/engine/plate/tel).")
    parser.add_argument("--query", "-q", required=True, help="Giá trị dùng để tìm (tax/id/tel/chassis/...)")
    parser.add_argument("--type", "-t", choices=["tax","id","tel","chassis","engine","name","auto"], default="auto", help="Loại tìm (khuyên dùng auto)")
    args = parser.parse_args()

    raw_query = args.query.strip()
    qtype = args.type

    # slug cho thư mục output
    slug = re.sub(r"[^0-9a-zA-Z]+", "_", raw_query)[:80] or "query"
    out_folder = os.path.join(OUT_BASE, slug)
    per_file_folder = os.path.join(out_folder, "per_file")
    os.makedirs(per_file_folder, exist_ok=True)

    # load mapping
    mapping_per_file = load_mapping()

    # liệt kê file
    files = []
    for ext in ("*.xlsx","*.xls","*.xlsm"):
        files.extend(glob(os.path.join(DATA_FOLDER, ext)))
    files = sorted(files)
    n_files = len(files)

    if not files:
        print("⚠ Không tìm thấy file Excel nào trong", DATA_FOLDER)
        return

    print(f"\n=== BẮT ĐẦU TÌM '{raw_query}' (type={qtype}) TRONG {n_files} FILE ===\n")

    # anchor sets từ phase1
    anchors = {
        "tax_no": set(),
        "id_no": set(),
        "chassis_no": set(),
        "engine_no": set(),
        "tel": set(),
        "number_plate": set(),
        "customer_code": set(),
    }

    # lưu kết quả
    combined_rows = []
    summary_rows = []
    matched_keys = set()  # (fname, index) để tránh trùng

    total_start = time.time()

    # ========== PHASE 1: tìm trực tiếp ==========
    print(">>> PHASE 1: Tìm trực tiếp theo query\n")

    phase1_matches_per_file = {}

    for idx, path in enumerate(files, start=1):
        fname = os.path.basename(path)
        print(f"[P1 {idx}/{n_files}] Đang đọc file: {fname} ...", flush=True)
        t0 = time.time()

        try:
            df = pd.read_excel(path, engine="openpyxl")
        except Exception:
            df = pd.read_excel(path)

        mapping = build_effective_mapping_for_file(fname, df, mapping_per_file)

        matches = []
        for ridx, row in df.iterrows():
            ok, reason = row_match_primary(row, mapping, raw_query, qtype)
            if ok:
                key = (fname, int(ridx))
                matched_keys.add(key)
                row_dict = row.to_dict()
                row_dict["_file"] = fname
                row_dict["_match_reason"] = reason
                row_dict["_phase"] = "phase1"
                matches.append(row_dict)
                combined_rows.append(row_dict)

                # gom anchors
                ids = extract_identifiers(mapping, row)
                for field, val in ids.items():
                    if val:
                        anchors[field].add(val)

        phase1_matches_per_file[fname] = matches
        elapsed = time.time() - t0
        print(f"    -> xong file {fname}: {len(matches)} dòng match (phase1), thời gian {elapsed:.2f} giây\n", flush=True)

    print(">>> PHASE 1 HOÀN TẤT.")
    print("Anchors thu được:")
    for k, s in anchors.items():
        print(f"  - {k}: {len(s)} giá trị")
    print("\n")

    # ========== PHASE 2: tìm theo định danh (chassis/engine/plate...) ==========
    print(">>> PHASE 2: Tìm theo bộ định danh (chassis/engine/plate/tel/...) trên toàn bộ file\n")

    phase2_matches_per_file = {fname: [] for fname in [os.path.basename(p) for p in files]}

    for idx, path in enumerate(files, start=1):
        fname = os.path.basename(path)
        print(f"[P2 {idx}/{n_files}] Đang đọc file: {fname} ...", flush=True)
        t0 = time.time()

        try:
            df = pd.read_excel(path, engine="openpyxl")
        except Exception:
            df = pd.read_excel(path)

        mapping = build_effective_mapping_for_file(fname, df, mapping_per_file)

        new_matches = []
        for ridx, row in df.iterrows():
            key = (fname, int(ridx))
            if key in matched_keys:
                continue  # đã match ở phase1

            ids = extract_identifiers(mapping, row)
            ok, reason = row_match_secondary(ids, anchors)
            if ok:
                matched_keys.add(key)
                row_dict = row.to_dict()
                row_dict["_file"] = fname
                row_dict["_match_reason"] = reason
                row_dict["_phase"] = "phase2"
                new_matches.append(row_dict)
                combined_rows.append(row_dict)

        phase2_matches_per_file[fname].extend(new_matches)
        elapsed = time.time() - t0
        print(f"    -> xong file {fname}: {len(new_matches)} dòng match (phase2), thời gian {elapsed:.2f} giây\n", flush=True)

    # ========== GHI KẾT QUẢ PER-FILE ==========
    print(">>> Đang ghi file kết quả per_file/ ...")

    for path in files:
        fname = os.path.basename(path)
        try:
            df = pd.read_excel(path, engine="openpyxl")
        except Exception:
            df = pd.read_excel(path)

        out_file_path = os.path.join(
            per_file_folder,
            fname.replace(".xlsx","").replace(".xls","").replace(".xlsm","") + "__matches.xlsx"
        )

        # ghép phase1 + phase2 (theo file)
        rows = []
        rows.extend(phase1_matches_per_file.get(fname, []))
        rows.extend(phase2_matches_per_file.get(fname, []))

        if rows:
            pd.DataFrame(rows).to_excel(out_file_path, index=False)
        else:
            # file rỗng nhưng giữ header để bạn dễ xem
            df.iloc[0:0].to_excel(out_file_path, index=False)

        summary_rows.append({
            "file": fname,
            "phase1_matches": len(phase1_matches_per_file.get(fname, [])),
            "phase2_matches": len(phase2_matches_per_file.get(fname, [])),
            "total_matches": len(phase1_matches_per_file.get(fname, [])) + len(phase2_matches_per_file.get(fname, []))
        })

    # ========== GHI COMBINED & SUMMARY ==========
    if combined_rows:
        pd.DataFrame(combined_rows).to_excel(os.path.join(out_folder, "combined_matches.xlsx"), index=False)
    else:
        pd.DataFrame().to_excel(os.path.join(out_folder, "combined_matches.xlsx"), index=False)

    pd.DataFrame(summary_rows).to_csv(os.path.join(out_folder, "summary.csv"), index=False)

    total_elapsed = time.time() - total_start
    print(f"=== HOÀN THÀNH trong {total_elapsed:.2f} giây ===")
    print("Thư mục kết quả:", out_folder)
    print(" - per_file/: 7 file kết quả (giữ nguyên cột gốc, lọc theo phase1+phase2)")
    print(" - combined_matches.xlsx: gộp tất cả bản ghi match, có cột _match_reason, _phase")
    print(" - summary.csv: số bản ghi match / file (phase1, phase2, total)")


if __name__ == "__main__":
    main()
