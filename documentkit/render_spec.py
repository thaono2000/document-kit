#!/usr/bin/env python3
"""render_spec.py - render spec.json into review/export formats (Markdown and optional XLSX).

One source of truth, deterministic outputs. The model writes the facts once into
spec.json; this script lays them out. That is why the two files can never
disagree with each other, and why choosing a format is a flag rather than a
second round of writing.

Usage:
    python render_spec.py spec.json --md SPEC.md
    python render_spec.py spec.json --xlsx SPEC.xlsx
    python render_spec.py spec.json --md SPEC.md --xlsx SPEC.xlsx
    python render_spec.py spec.json --md-dir docs/specs --md SPEC.md   # split per module

The xlsx writer needs openpyxl. If it is missing the script writes one CSV per
sheet next to the requested path and says so, rather than failing.
"""

import argparse
import csv
import json
import os
import sys

# Console Windows mac dinh cp1252 se lam vo tieng Viet khi in ra man hinh.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


SEVERITY_ORDER = {"cao": 0, "trung bình": 1, "trung binh": 1, "thấp": 2, "thap": 2}
SEVERITY_FILL = {"cao": "FFF2DEDE", "trung bình": "FFFCF3CF", "trung binh": "FFFCF3CF"}


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def load(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def bullets(items, indent=""):
    return "\n".join("{}- {}".format(indent, i) for i in items)


def join(items, sep=", "):
    return sep.join(str(i) for i in items if str(i).strip())


def iter_anchors(value):
    if value is None or value == "":
        return []
    return value if isinstance(value, list) else [value]


def anchor_text(anchor):
    """Human-readable anchor; supports canonical object and legacy string."""
    if isinstance(anchor, dict):
        repo = str(anchor.get("repo", "")).strip()
        path = str(anchor.get("path", "")).strip()
        return "{} — {}".format(repo, path) if repo else path
    return str(anchor)


def anchors_text(value, sep=", "):
    return sep.join(anchor_text(a) for a in iter_anchors(value) if anchor_text(a).strip())


def cell(value):
    """Flatten a JSON value into something a spreadsheet cell can hold."""
    if value is None:
        return ""
    if isinstance(value, list):
        parts = []
        for v in value:
            if isinstance(v, dict):
                parts.append(format_input(v) if "ten" in v or "name" in v else json.dumps(v, ensure_ascii=False))
            else:
                parts.append(str(v))
        return "\n".join(parts)
    if isinstance(value, dict):
        return "\n".join("{}: {}".format(k, v) for k, v in value.items())
    return str(value)


def format_input(f):
    """One input field as a single readable line."""
    name = f.get("ten") or f.get("name") or "?"
    bits = [b for b in (f.get("kieu") or f.get("type"), ) if b]
    required = f.get("bat_buoc")
    if required is True:
        bits.append("bắt buộc")
    elif required is False:
        bits.append("tuỳ chọn")
    rule = f.get("rang_buoc") or f.get("rule")
    head = "`{}`".format(name)
    if bits:
        head += " ({})".format(join(bits))
    return head + (" — " + rule if rule else "")


def md_table(headers, rows):
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join([" --- "] * len(headers)) + "|"]
    for r in rows:
        cells = [str(c).replace("\n", "<br>").replace("|", "\\|") for c in r]
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out)


def feature_iter(spec):
    for mi, module in enumerate(spec.get("modules", []), 1):
        for fi, feat in enumerate(module.get("chuc_nang", []), 1):
            yield mi, fi, module, feat


# --------------------------------------------------------------------------
# markdown
# --------------------------------------------------------------------------

def render_feature_md(num, feat):
    out = ["  - **{} {}**".format(num, feat.get("ten", "(chưa đặt tên)"))]

    def field(label, value):
        if value:
            out.append("    - **{}:** {}".format(label, value))

    field("Trạng thái", feat.get("trang_thai"))
    field("Mô tả", feat.get("mo_ta"))
    field("Đối tượng sử dụng", join(feat.get("doi_tuong", [])))

    inputs = feat.get("dau_vao") or []
    if inputs:
        out.append("    - **Dữ liệu đầu vào (Input):**")
        for f in inputs:
            out.append("      - " + format_input(f))
    elif feat.get("dau_vao_mo_ta"):
        field("Dữ liệu đầu vào (Input)", feat["dau_vao_mo_ta"])

    steps = feat.get("luong_xu_ly") or []
    if steps:
        out.append("    - **Luồng xử lý (Logic):**")
        for i, s in enumerate(steps, 1):
            out.append("      {}. {}".format(i, s))

    ra = feat.get("dau_ra") or {}
    if ra:
        out.append("    - **Kết quả đầu ra (Output):**")
        if ra.get("thanh_cong"):
            out.append("      - Thành công: {}".format(ra["thanh_cong"]))
        for err in ra.get("loi", []):
            out.append("      - Lỗi: {}".format(err))

    field("Phân quyền", feat.get("phan_quyen"))
    anchors = feat.get("neo") or []
    if anchors:
        field("Neo mã nguồn", ", ".join("`{}`".format(anchor_text(a)) for a in iter_anchors(anchors)))
    field("Độ tin cậy", feat.get("do_tin_cay"))
    field("Ghi chú", feat.get("ghi_chu"))
    return "\n".join(out)


def render_module_md(mi, module, heading_level=3):
    h = "#" * heading_level
    out = ["{} 2.{}. Module {}".format(h, mi, module.get("ten", "(chưa đặt tên)")), ""]
    if module.get("mo_ta"):
        out.append("- **Mô tả:** {}".format(module["mo_ta"]))
    if module.get("doi_tuong"):
        out.append("- **Đối tượng sử dụng:** {}".format(join(module["doi_tuong"])))
    out.append("- **Các chức năng con & Logic chi tiết:**")
    out.append("")
    for fi, feat in enumerate(module.get("chuc_nang", []), 1):
        out.append(render_feature_md("2.{}.{}".format(mi, fi), feat))
        out.append("")
    return "\n".join(out)


def render_md(spec, split_dir=None, md_path=None):
    p = spec.get("du_an", {})
    name = p.get("ten", "DỰ ÁN")
    out = ["# TÀI LIỆU ĐẶC TẢ KỸ THUẬT (TECHNICAL SPECIFICATION) — {}".format(name.upper()), ""]

    meta = ["Lập ngày {}".format(p.get("ngay", "?"))]
    if p.get("commit"):
        meta.append("commit `{}`".format(p["commit"]))
    if p.get("nguon"):
        meta.append("nguồn: {}".format(p["nguon"]))
    out += ["> " + " · ".join(meta),
            ">",
            "> Mỗi chức năng đều kèm neo mã nguồn dạng `repo — đường/dẫn.ext:dòng` — đó là",
            "> nơi mô tả được đọc ra. Mục nào ghi độ tin cậy **thấp** nghĩa là bằng chứng",
            "> chưa đủ chắc chắn; hãy đọc ghi chú và coi đó là điểm cần xác nhận.",
            ""]

    # ---- 1. Tổng quan
    out += ["## 1. Tổng quan dự án (Overview)", ""]
    for label, key in (("Công nghệ sử dụng", "cong_nghe"), ("Kiến trúc", "kien_truc"),
                       ("Cơ sở dữ liệu", "co_so_du_lieu"), ("Tích hợp bên ngoài", "tich_hop"),
                       ("Điểm khởi chạy", "diem_khoi_chay")):
        v = p.get(key)
        if v:
            out.append("- **{}:** {}".format(label, join(v) if isinstance(v, list) else v))
    if spec.get("tong_quan_md"):
        out += ["", spec["tong_quan_md"]]
    out.append("")

    # ---- 2. Chức năng
    out += ["## 2. Danh sách các chức năng cốt lõi (Core Features)", ""]
    rows = []
    for mi, module in enumerate(spec.get("modules", []), 1):
        rows.append(["2.{}".format(mi), module.get("ten", ""),
                     str(len(module.get("chuc_nang", []))),
                     join(module.get("doi_tuong", [])),
                     module.get("mo_ta", "")[:90]])
    if rows:
        out += [md_table(["#", "Module", "Số chức năng", "Đối tượng", "Mô tả ngắn"], rows), ""]

    modules = spec.get("modules", [])
    if split_dir:
        os.makedirs(split_dir, exist_ok=True)
        for mi, module in enumerate(modules, 1):
            fname = "{:02d}-{}.md".format(mi, slugify(module.get("ten", "module")))
            body = "# Module {}: {}\n\n".format(mi, module.get("ten", "")) + \
                   render_module_md(mi, module, heading_level=2)
            module_path = os.path.join(split_dir, fname)
            with open(module_path, "w", encoding="utf-8") as fh:
                fh.write(body + "\n")
            if md_path:
                base_dir = os.path.dirname(os.path.abspath(md_path))
                link = os.path.relpath(os.path.abspath(module_path), start=base_dir)
            else:
                link = module_path
            out.append("- [2.{}. {}]({})".format(mi, module.get("ten", ""),
                                                 link.replace(os.sep, "/")))
        out.append("")
    else:
        for mi, module in enumerate(modules, 1):
            out.append(render_module_md(mi, module))

    # ---- 3. API
    apis = spec.get("api", [])
    out += ["## 3. Đặc tả API / Điểm cuối kết nối (API Specifications)", ""]
    if apis:
        out.append(md_table(
            ["Phương thức", "Endpoint", "Chức năng", "Tham số (Params/Body)", "Phản hồi", "Quyền", "Neo mã nguồn"],
            [[a.get("phuong_thuc", ""), "`{}`".format(a.get("endpoint", "")), a.get("chuc_nang", ""),
              cell(a.get("tham_so")), cell(a.get("phan_hoi")), a.get("quyen", ""),
              "`{}`".format(anchors_text(a.get("neo")))] for a in apis]))
    else:
        out.append("*Dự án không có API HTTP, hoặc không tìm thấy endpoint nào.*")
    out.append("")

    # ---- 4. Dữ liệu
    out += ["## 4. Mô hình Dữ liệu (Data Models / Schema)", ""]
    models = spec.get("mo_hinh_du_lieu", [])
    if models:
        for m in models:
            out.append("### 4.{}. `{}`".format(models.index(m) + 1, m.get("ten", "")))
            if m.get("mo_ta"):
                out += ["", m["mo_ta"]]
            if m.get("neo"):
                out += ["", "Neo mã nguồn: `{}`".format(anchors_text(m["neo"]))]
            out += ["", md_table(["Trường", "Kiểu", "Ràng buộc", "Ý nghĩa"],
                                 [[f.get("ten", ""), f.get("kieu", ""), f.get("rang_buoc", ""),
                                   f.get("y_nghia", "")] for f in m.get("truong", [])]), ""]
    else:
        out += ["*Không xác định được mô hình dữ liệu từ mã nguồn.*", ""]

    # ---- 5. Sơ đồ
    out += ["## 5. Sơ đồ (Diagrams)", ""]
    diagrams = spec.get("diagrams", []) or []
    if diagrams:
        for i, d in enumerate(diagrams, 1):
            out.append("### 5.{}. {}".format(i, d.get("title", "Sơ đồ")))
            if d.get("description"):
                out += ["", str(d["description"])]
            if d.get("neo"):
                out += ["", "Neo mã nguồn: `{}`".format(anchors_text(d.get("neo")))]
            if d.get("mermaid"):
                out += ["", "```mermaid", str(d["mermaid"]).rstrip(), "```", ""]
    else:
        out += ["*Chưa có sơ đồ đã được xác minh.*", ""]

    # ---- 6. Lưu ý kỹ thuật
    out += ["## 6. Lưu ý kỹ thuật & Ràng buộc (Constraints & Technical Notes)", ""]
    if spec.get("bao_mat"):
        out += ["### 6.1. Bảo mật", "", bullets([x.get("noi_dung", "") if isinstance(x, dict) else x for x in spec["bao_mat"]]), ""]
    risks = spec.get("rui_ro", [])
    if risks:
        risks = sorted(risks, key=lambda r: SEVERITY_ORDER.get(str(r.get("muc_do", "")).lower(), 9))
        out += ["### 6.2. Rủi ro & tồn đọng", "",
                md_table(["Mức độ", "Hạng mục", "Vấn đề", "Ảnh hưởng", "Neo mã nguồn"],
                         [[r.get("muc_do", ""), r.get("hang_muc", ""), r.get("van_de", ""),
                           r.get("anh_huong", ""), "`{}`".format(anchors_text(r.get("neo")))] for r in risks]), ""]
    if spec.get("ghi_chu_md"):
        out += [spec["ghi_chu_md"], ""]

    # ---- 7. Phạm vi
    pv = spec.get("pham_vi", {})
    out += ["## 7. Phạm vi & độ tin cậy", ""]
    for label, key in (("Đã phân tích", "da_quet"), ("Bỏ qua", "bo_qua"),
                       ("Chưa xác định được", "chua_ro"), ("Mã nguồn chết / không dùng", "ma_chet")):
        v = pv.get(key)
        if v:
            out += ["- **{}:**".format(label), bullets(v if isinstance(v, list) else [v], "  "), ""]

    return "\n".join(out).rstrip() + "\n"


def slugify(s):
    import re
    import unicodedata
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").replace("đ", "d").replace("Đ", "D")
    return re.sub(r"-+", "-", re.sub(r"[^a-zA-Z0-9]+", "-", s)).strip("-").lower() or "module"


# --------------------------------------------------------------------------
# xlsx
# --------------------------------------------------------------------------

def sheet_data(spec):
    """Return [(sheet name, headers, rows, column widths)] - shared by xlsx and the CSV fallback."""
    p = spec.get("du_an", {})
    overview = [
        ["Tên dự án", p.get("ten", "")],
        ["Ngày lập", p.get("ngay", "")],
        ["Commit", p.get("commit", "")],
        ["Nguồn phân tích", p.get("nguon", "")],
        ["Công nghệ sử dụng", cell(p.get("cong_nghe"))],
        ["Kiến trúc", cell(p.get("kien_truc"))],
        ["Cơ sở dữ liệu", cell(p.get("co_so_du_lieu"))],
        ["Tích hợp bên ngoài", cell(p.get("tich_hop"))],
        ["Điểm khởi chạy", cell(p.get("diem_khoi_chay"))],
        ["Số module", str(len(spec.get("modules", [])))],
        ["Số chức năng", str(sum(len(m.get("chuc_nang", [])) for m in spec.get("modules", [])))],
        ["Số endpoint", str(len(spec.get("api", [])))],
        ["Số rủi ro ghi nhận", str(len(spec.get("rui_ro", [])))],
    ]

    features = []
    for mi, fi, module, f in feature_iter(spec):
        ra = f.get("dau_ra") or {}
        features.append([
            "2.{}.{}".format(mi, fi),
            module.get("ten", ""),
            f.get("ten", ""),
            f.get("trang_thai", "ACTIVE"),
            f.get("mo_ta", ""),
            join(f.get("doi_tuong", [])),
            # Excel không hiểu dấu backtick của Markdown, bỏ đi cho dễ đọc.
            (cell(f.get("dau_vao")) or f.get("dau_vao_mo_ta", "")).replace("`", ""),
            "\n".join("{}. {}".format(i, s) for i, s in enumerate(f.get("luong_xu_ly", []), 1)),
            join(([("Thành công: " + ra["thanh_cong"])] if ra.get("thanh_cong") else [])
                 + ["Lỗi: " + e for e in ra.get("loi", [])], "\n"),
            f.get("phan_quyen", ""),
            anchors_text(f.get("neo"), "\n"),
            f.get("do_tin_cay", ""),
            f.get("ghi_chu", ""),
        ])

    apis = [[a.get("phuong_thuc", ""), a.get("endpoint", ""), a.get("chuc_nang", ""),
             cell(a.get("tham_so")), cell(a.get("phan_hoi")), a.get("quyen", ""), anchors_text(a.get("neo"))]
            for a in spec.get("api", [])]

    models = []
    for m in spec.get("mo_hinh_du_lieu", []):
        for f in m.get("truong", []):
            models.append([m.get("ten", ""), f.get("ten", ""), f.get("kieu", ""),
                           f.get("rang_buoc", ""), f.get("y_nghia", ""), anchors_text(m.get("neo"))])

    risks = [[r.get("muc_do", ""), r.get("hang_muc", ""), r.get("van_de", ""),
              r.get("anh_huong", ""), anchors_text(r.get("neo")), r.get("cau_hoi", "")]
             for r in sorted(spec.get("rui_ro", []),
                             key=lambda r: SEVERITY_ORDER.get(str(r.get("muc_do", "")).lower(), 9))]

    return [
        ("Tổng quan", ["Hạng mục", "Nội dung"], overview, [26, 90]),
        ("Chức năng", ["Mã", "Module", "Chức năng", "Trạng thái", "Mô tả", "Đối tượng", "Đầu vào",
                       "Luồng xử lý", "Đầu ra", "Phân quyền", "Neo mã nguồn", "Độ tin cậy", "Ghi chú"],
         features, [9, 22, 26, 24, 44, 16, 38, 46, 32, 16, 28, 11, 38]),
        ("API", ["Phương thức", "Endpoint", "Chức năng", "Tham số", "Phản hồi", "Quyền", "Neo mã nguồn"],
         apis, [12, 34, 30, 34, 30, 16, 28]),
        ("Dữ liệu", ["Bảng / Collection", "Trường", "Kiểu", "Ràng buộc", "Ý nghĩa", "Neo mã nguồn"],
         models, [22, 22, 16, 24, 40, 28]),
        ("Rủi ro", ["Mức độ", "Hạng mục", "Vấn đề", "Ảnh hưởng", "Neo mã nguồn", "Câu hỏi cho team"],
         risks, [10, 20, 46, 40, 28, 40]),
    ]


def render_xlsx(spec, path):
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter
    except ImportError as exc:
        raise RuntimeError("XLSX output was requested but openpyxl is not installed") from exc

    wb = Workbook()
    wb.remove(wb.active)
    header_fill = PatternFill("solid", fgColor="FF1F3864")
    header_font = Font(bold=True, color="FFFFFFFF", size=11)
    wrap_top = Alignment(wrap_text=True, vertical="top")

    for title, headers, rows, widths in sheet_data(spec):
        ws = wb.create_sheet(title)
        ws.append(headers)
        for c in range(1, len(headers) + 1):
            cellobj = ws.cell(row=1, column=c)
            cellobj.fill = header_fill
            cellobj.font = header_font
            cellobj.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
        for r in rows:
            ws.append(r)
        for i, w in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(i)].width = w
        for row in ws.iter_rows(min_row=2):
            for c in row:
                c.alignment = wrap_top
        ws.freeze_panes = "A2"
        ws.row_dimensions[1].height = 28
        if rows:
            ws.auto_filter.ref = "A1:{}{}".format(get_column_letter(len(headers)), len(rows) + 1)
        if title == "Rủi ro":
            for row in ws.iter_rows(min_row=2, max_col=1):
                fill = SEVERITY_FILL.get(str(row[0].value or "").lower())
                if fill:
                    for c in ws[row[0].row]:
                        c.fill = PatternFill("solid", fgColor=fill)

    wb.save(path)
    return [path]


def render_csv_fallback(spec, path):
    base = os.path.splitext(path)[0]
    written = []
    for title, headers, rows, _w in sheet_data(spec):
        out = "{}-{}.csv".format(base, slugify(title))
        with open(out, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(headers)
            w.writerows(rows)
        written.append(out)
    print("openpyxl không có sẵn - đã ghi {} file CSV thay cho xlsx.".format(len(written)))
    print("Cài bằng: py -3 -m pip install openpyxl")
    return written


# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Render spec.json thành SPEC.md và/hoặc SPEC.xlsx.")
    ap.add_argument("spec")
    ap.add_argument("--md", help="đường dẫn file Markdown cần ghi")
    ap.add_argument("--xlsx", help="đường dẫn file Excel cần ghi")
    ap.add_argument("--md-dir", help="tách mỗi module ra một file trong thư mục này")
    args = ap.parse_args()

    if not args.md and not args.xlsx:
        sys.exit("Cần ít nhất một trong hai: --md hoặc --xlsx")
    if not os.path.isfile(args.spec):
        sys.exit("không tìm thấy: {}".format(args.spec))

    spec = load(args.spec)
    written = []

    if args.md:
        os.makedirs(os.path.dirname(os.path.abspath(args.md)), exist_ok=True)
        with open(args.md, "w", encoding="utf-8") as fh:
            fh.write(render_md(spec, args.md_dir, args.md))
        written.append(args.md)
    if args.xlsx:
        os.makedirs(os.path.dirname(os.path.abspath(args.xlsx)), exist_ok=True)
        written += render_xlsx(spec, args.xlsx)

    n_mod = len(spec.get("modules", []))
    n_feat = sum(len(m.get("chuc_nang", [])) for m in spec.get("modules", []))
    print("Đã ghi {} module / {} chức năng / {} endpoint / {} rủi ro".format(
        n_mod, n_feat, len(spec.get("api", [])), len(spec.get("rui_ro", []))))
    for w in written:
        print("  " + os.path.abspath(w).replace(os.sep, "/"))


if __name__ == "__main__":
    main()
