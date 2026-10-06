from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any


def _h(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def _join(items: Any) -> str:
    if not isinstance(items, list):
        return str(items or "")
    return ", ".join(str(x) for x in items if str(x).strip())


def _anchors(value: Any) -> str:
    rows = value if isinstance(value, list) else ([value] if value else [])
    out = []
    for row in rows:
        if isinstance(row, dict):
            repo = str(row.get("repo", "")).strip()
            path = str(row.get("path", "")).strip()
            text = f"{repo} — {path}" if repo else path
        else:
            text = str(row)
        if text.strip():
            out.append(f"<li><code>{_h(text)}</code></li>")
    return "<ul>" + "".join(out) + "</ul>" if out else ""


def _input_line(row: dict[str, Any]) -> str:
    name = row.get("ten") or row.get("name") or "?"
    bits = []
    if row.get("kieu") or row.get("type"):
        bits.append(str(row.get("kieu") or row.get("type")))
    if row.get("bat_buoc") is True:
        bits.append("bắt buộc")
    elif row.get("bat_buoc") is False:
        bits.append("tuỳ chọn")
    suffix = f" ({', '.join(bits)})" if bits else ""
    rule = row.get("rang_buoc") or row.get("rule")
    return f"{name}{suffix}" + (f" — {rule}" if rule else "")


def render_html(spec: dict[str, Any]) -> str:
    project = spec.get("du_an", {}) or {}
    modules = spec.get("modules", []) or []
    statuses = sorted({str(f.get("trang_thai") or "ACTIVE") for m in modules for f in m.get("chuc_nang", []) or []})
    confidences = sorted({str(f.get("do_tin_cay") or "") for m in modules for f in m.get("chuc_nang", []) or [] if f.get("do_tin_cay")})

    toc: list[str] = []
    body: list[str] = []
    for mi, module in enumerate(modules, 1):
        mid = f"module-{mi}"
        toc.append(f'<li><a href="#{mid}">{_h(module.get("ten", "Module"))}</a></li>')
        body.append(f'<section id="{mid}" class="module"><h2>{mi}. {_h(module.get("ten", ""))}</h2><p>{_h(module.get("mo_ta", ""))}</p>')
        for fi, feat in enumerate(module.get("chuc_nang", []) or [], 1):
            status = str(feat.get("trang_thai") or "ACTIVE")
            confidence = str(feat.get("do_tin_cay") or "")
            search_blob = " ".join([
                str(module.get("ten", "")), str(feat.get("ten", "")), str(feat.get("mo_ta", "")),
                str(feat.get("phan_quyen", "")), " ".join(map(str, feat.get("luong_xu_ly", []) or [])),
            ]).lower()
            out = feat.get("dau_ra") or {}
            input_rows = feat.get("dau_vao") or []
            inputs = "".join(f"<li>{_h(_input_line(x))}</li>" for x in input_rows if isinstance(x, dict))
            if not inputs and feat.get("dau_vao_mo_ta"):
                inputs = f"<li>{_h(feat.get('dau_vao_mo_ta'))}</li>"
            logic = "".join(f"<li>{_h(x)}</li>" for x in feat.get("luong_xu_ly", []) or [])
            errors = "".join(f"<li>{_h(x)}</li>" for x in out.get("loi", []) or [])
            notes = f'<p class="note"><strong>Ghi chú:</strong> {_h(feat.get("ghi_chu"))}</p>' if feat.get("ghi_chu") else ""
            body.append(f'''<article class="feature" data-module="{_h(module.get('ten',''))}" data-status="{_h(status)}" data-confidence="{_h(confidence)}" data-search="{_h(search_blob)}">
<h3>{mi}.{fi} {_h(feat.get('ten',''))}</h3>
<div class="badges"><span>{_h(status)}</span><span>Độ tin cậy: {_h(confidence)}</span></div>
<p>{_h(feat.get('mo_ta',''))}</p>
<dl><dt>Đối tượng</dt><dd>{_h(_join(feat.get('doi_tuong', [])))}</dd><dt>Phân quyền</dt><dd>{_h(feat.get('phan_quyen',''))}</dd></dl>
<details open><summary>Đầu vào</summary><ul>{inputs}</ul></details>
<details open><summary>Luồng xử lý</summary><ol>{logic}</ol></details>
<details><summary>Đầu ra</summary><p><strong>Thành công:</strong> {_h(out.get('thanh_cong',''))}</p><ul>{errors}</ul></details>
<details><summary>Nguồn xác minh</summary>{_anchors(feat.get('neo'))}</details>{notes}</article>''')
        body.append("</section>")

    api_rows = []
    for a in spec.get("api", []) or []:
        api_rows.append(f'''<tr><td>{_h(a.get('phuong_thuc'))}</td><td><code>{_h(a.get('endpoint'))}</code></td><td>{_h(a.get('chuc_nang'))}</td><td>{_h(a.get('quyen'))}</td><td>{_h(a.get('trang_thai') or 'ACTIVE')}</td></tr>''')

    diagrams = []
    for d in spec.get("diagrams", []) or []:
        diagrams.append(f'''<article class="diagram"><h3>{_h(d.get('title','Sơ đồ'))}</h3><p>{_h(d.get('description',''))}</p><pre class="mermaid">{_h(d.get('mermaid',''))}</pre>{_anchors(d.get('neo'))}</article>''')

    ui_images = []
    for img in spec.get("ui_images", []) or []:
        ui_images.append(f'''<figure class="diagram"><img src="{_h(img.get('path',''))}" alt="{_h(img.get('title','UI'))}"><figcaption>{_h(img.get('caption') or img.get('title',''))}</figcaption></figure>''')

    module_opts = "".join(f'<option value="{_h(m.get("ten",""))}">{_h(m.get("ten",""))}</option>' for m in modules)
    status_opts = "".join(f'<option value="{_h(x)}">{_h(x)}</option>' for x in statuses)
    confidence_opts = "".join(f'<option value="{_h(x)}">{_h(x)}</option>' for x in confidences)

    style = '''
:root{font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#172033;background:#f6f8fb}*{box-sizing:border-box}body{margin:0}.layout{display:grid;grid-template-columns:280px 1fr;min-height:100vh}.sidebar{position:sticky;top:0;height:100vh;overflow:auto;background:#111827;color:#e5e7eb;padding:24px}.sidebar a{color:#dbeafe;text-decoration:none}.sidebar ul{padding-left:18px}.main{padding:32px;max-width:1280px}.hero,.feature,.diagram,.api-wrap{background:white;border:1px solid #e5e7eb;border-radius:14px;padding:20px;margin:0 0 18px;box-shadow:0 2px 8px rgba(15,23,42,.04)}.toolbar{display:grid;grid-template-columns:2fr repeat(3,1fr);gap:10px;margin:18px 0}.toolbar input,.toolbar select{padding:11px;border:1px solid #cbd5e1;border-radius:9px;background:white}.badges{display:flex;gap:8px;flex-wrap:wrap;margin:6px 0 12px}.badges span{font-size:12px;background:#eef2ff;border-radius:999px;padding:4px 9px}.feature[data-status="REMOVED_PENDING_REVIEW"]{border-left:5px solid #b45309;opacity:.86}.feature h3{margin-bottom:6px}dt{font-weight:700}dd{margin:0 0 8px}.note{background:#fff7ed;padding:10px;border-radius:8px}.hidden{display:none!important}table{width:100%;border-collapse:collapse}th,td{padding:10px;border-bottom:1px solid #e5e7eb;text-align:left;vertical-align:top}code{background:#f1f5f9;padding:2px 5px;border-radius:5px}.mermaid{overflow:auto;background:#f8fafc;padding:14px;border-radius:10px}.diagram img{max-width:100%;height:auto;border-radius:8px}@media(max-width:900px){.layout{grid-template-columns:1fr}.sidebar{position:relative;height:auto}.toolbar{grid-template-columns:1fr}.main{padding:18px}}
'''
    script = '''
const q=document.getElementById('q'),fm=document.getElementById('fm'),fs=document.getElementById('fs'),fc=document.getElementById('fc');function apply(){const query=q.value.trim().toLowerCase();document.querySelectorAll('.feature').forEach(el=>{const okQ=!query||el.dataset.search.includes(query),okM=!fm.value||el.dataset.module===fm.value,okS=!fs.value||el.dataset.status===fs.value,okC=!fc.value||el.dataset.confidence===fc.value;el.classList.toggle('hidden',!(okQ&&okM&&okS&&okC));});document.querySelectorAll('.module').forEach(m=>{const any=[...m.querySelectorAll('.feature')].some(x=>!x.classList.contains('hidden'));m.classList.toggle('hidden',!any);});}[q,fm,fs,fc].forEach(x=>x.addEventListener(x.tagName==='INPUT'?'input':'change',apply));
'''
    title = project.get("ten", "Tài liệu đặc tả")
    return f'''<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{_h(title)} — DocumentKit</title><style>{style}</style></head><body><div class="layout"><aside class="sidebar"><h2>DocumentKit</h2><p>{_h(title)}</p><nav><ul>{''.join(toc)}<li><a href="#api">API</a></li><li><a href="#diagrams">Sơ đồ</a></li></ul></nav></aside><main class="main"><section class="hero"><h1>{_h(title)}</h1><p>Đặc tả nghiệp vụ được sinh từ <code>spec.json</code> và bằng chứng mã nguồn đã xác minh.</p></section><div class="toolbar"><input id="q" type="search" placeholder="Tìm chức năng, mô tả, quyền..."><select id="fm"><option value="">Tất cả module</option>{module_opts}</select><select id="fs"><option value="">Tất cả trạng thái</option>{status_opts}</select><select id="fc"><option value="">Tất cả độ tin cậy</option>{confidence_opts}</select></div>{''.join(body)}<section id="api" class="api-wrap"><h2>API</h2><table><thead><tr><th>Method</th><th>Endpoint</th><th>Chức năng</th><th>Quyền</th><th>Trạng thái</th></tr></thead><tbody>{''.join(api_rows)}</tbody></table></section><section id="diagrams"><h2>Sơ đồ</h2>{''.join(diagrams) or '<p>Chưa có sơ đồ.</p>'}{''.join(ui_images)}</section></main></div><script>{script}</script><script type="module">try{{const mermaid=(await import('https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs')).default;mermaid.initialize({{startOnLoad:true,securityLevel:'strict'}});}}catch(e){{console.warn('Mermaid renderer unavailable; Mermaid source remains visible.',e);}}</script></body></html>'''


def write_html(spec_path: Path, output_path: Path) -> None:
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_html(spec), encoding="utf-8")
