# `spec.json` schema — DocumentKit v1.1

`spec.json` is the source of truth. HTML, Markdown and optional XLSX are deterministic renderings of it.

## Top-level shape

```json
{
  "du_an": {},
  "phan_tich": {},
  "tong_quan_md": "",
  "modules": [],
  "api": [],
  "mo_hinh_du_lieu": [],
  "bao_mat": [],
  "rui_ro": [],
  "diagrams": [],
  "ui_images": [],
  "ghi_chu_md": "",
  "pham_vi": {}
}
```

## `phan_tich`

DocumentKit may add an exact source snapshot:

```json
{
  "chien_luoc": "cbm-first + symbol-evidence-cache",
  "source_snapshot": {
    "RepitteGlobal-BookingService": "full-commit-sha",
    "RepitteGlobal-ManagementService": "full-commit-sha"
  }
}
```

This records which commits were held stable while generating a published specification.

## Active function

```json
{
  "doc_id": "doc_...",
  "ten": "Huỷ booking",
  "mo_ta": "...",
  "doi_tuong": ["Hotel Admin"],
  "dau_vao": [],
  "dau_vao_mo_ta": "...",
  "luong_xu_ly": ["..."],
  "dau_ra": {"thanh_cong": "...", "loi": []},
  "phan_quyen": "Hotel Admin của hotel sở hữu booking",
  "neo": [{"repo": "BookingService", "path": "src/file.ts:10-50"}],
  "evidence_refs": ["sym_..."],
  "do_tin_cay": "cao",
  "ghi_chu": ""
}
```

Strict validation requires Input, ordered Logic, Output, authorization, anchors, valid evidence refs and confidence.

## Removed function

Historical functionality is retained:

```json
{
  "doc_id": "doc_...",
  "ten": "Legacy export",
  "mo_ta": "...",
  "trang_thai": "REMOVED_PENDING_REVIEW",
  "removal_reason": "Route removed from source",
  "removed_commit": "optional sha",
  "neo": [{"repo": "Repo", "path": "old/file.ts:10"}],
  "evidence_refs": ["sym_old..."]
}
```

For removed items, old source files/ranges/evidence may no longer resolve. Those historical references do not block publication.

## API row

```json
{
  "phuong_thuc": "POST",
  "endpoint": "/api/bookings/{id}/cancel",
  "chuc_nang": "Huỷ booking",
  "tham_so": "...",
  "phan_hoi": "...",
  "quyen": "Hotel Admin",
  "neo": [{"repo": "BookingService", "path": "routes/api.php:55"}],
  "evidence_refs": ["sym_..."]
}
```

Every active discovered HTTP route with a deterministic method+path must be represented by an active API row. Removed API rows use `REMOVED_PENDING_REVIEW` instead of being silently deleted.

## Data model

```json
{
  "ten": "bookings",
  "mo_ta": "...",
  "neo": [{"repo": "BookingService", "path": "app/Models/Booking.php:10"}],
  "evidence_refs": ["sym_..."],
  "truong": []
}
```

## Risk

```json
{
  "muc_do": "cao",
  "hang_muc": "Booking",
  "van_de": "...",
  "anh_huong": "...",
  "neo": [{"repo": "BookingService", "path": "app/Services/BookingService.php:100"}],
  "evidence_refs": ["sym_..."],
  "cau_hoi": ""
}
```

## Mermaid diagram

Diagrams are optional and must be useful + source-backed.

```json
{
  "id": "booking-cancel-flow",
  "type": "business_flow",
  "title": "Luồng huỷ booking",
  "description": "...",
  "mermaid": "flowchart TD\nA[Request] --> B{Authorized?}",
  "neo": [{"repo": "BookingService", "path": "app/Services/BookingService.php:100-180"}],
  "evidence_refs": ["sym_..."]
}
```

Typical `type` values:

- `architecture`
- `business_flow`
- `state`

## Verified UI image

Only use when a real interface/image is available and verified. Never fabricate screenshots.

```json
{
  "title": "Booking cancellation screen",
  "path": "assets/booking-cancel.png",
  "caption": "...",
  "verified": true,
  "neo": [{"repo": "AdminPortal", "path": "src/pages/Booking.vue:1-200"}],
  "evidence_refs": ["sym_..."]
}
```

## Evidence identity

Cache identity remains:

```text
repo + relative path + qualified symbol
```

The evidence entry stores a SHA-256 hash of the exact source range. Active refs must exist and match current source before strict validation passes.
