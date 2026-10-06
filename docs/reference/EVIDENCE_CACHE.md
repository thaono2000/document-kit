# Symbol-level Evidence Cache

Cache này tồn tại để tránh đọc và phân tích **cùng một function/method nhiều
lần** khi nhiều endpoint cùng gọi nó. Nó không nhóm endpoint và không bỏ bớt
coverage.

Nguyên tắc:

> Mỗi endpoint vẫn được trace và compose riêng. Chỉ phần phân tích hành vi nội
> tại của symbol được reuse khi source body chưa đổi.

## Cache cái gì

Cache **intrinsic symbol behavior**, ví dụ:

```json
{
  "inputs": ["user", "hotelId"],
  "behavior": [
    "Super Admin được phép tiếp tục",
    "User có hotel_id khác hotelId thì bị từ chối"
  ],
  "outputs": ["true khi hợp lệ"],
  "errors": ["ForbiddenException khi không có quyền"],
  "side_effects": [],
  "calls": [],
  "notes": [],
  "confidence": "high"
}
```

Không cache câu phụ thuộc endpoint như:

> "Người dùng chỉ được hủy booking của hotel mình quản lý"

vì cùng function kiểm tra quyền có thể được dùng ở create/update/cancel với ý
nghĩa nghiệp vụ khác nhau. Câu business-level phải được compose lại trong
context của từng endpoint.

## Cache key và tính hợp lệ

Logical key được tạo từ:

```text
repo + relative path + qualified symbol
```

Mỗi entry giữ SHA-256 của **exact source body/range**. Cache chỉ HIT khi:

- cùng logical symbol;
- `analysis_version` vẫn tương thích;
- source body hiện tại có cùng hash.

Nếu symbol chỉ đổi số dòng nhưng body giữ nguyên, `get-symbol` với range mới do
CBM resolve sẽ vẫn HIT và cập nhật location metadata.

## Workflow một symbol

1. CBM resolve `repo/path/symbol/start/end`.
2. Chạy:

```bash
python <skill>/scripts/evidence_cache.py get-symbol \
  --cache-dir <cache> \
  --repo-name <Repo> --repo-root <repo-root> \
  --path <relative-file> --symbol '<Qualified::symbol>' \
  --start <line> --end <line>
```

3. `status=hit` → reuse `entry.analysis`, không đọc source lại.
4. `miss/stale` → đọc full symbol source, phân tích, ghi file JSON nhỏ rồi:

```bash
python <skill>/scripts/evidence_cache.py put-symbol ... \
  --analysis symbol-analysis.json
```

5. Ghi `key` trả về vào `chuc_nang[].evidence_refs` của `spec.json`.
6. Mọi symbol trong call chain đã dùng để kết luận endpoint đều phải được đưa
   vào `evidence_refs`, không chỉ controller/service đầu tiên.

## Cache đặt ở đâu

Khuyên dùng cache local ngoài source repo, ví dụ:

```text
~/.cache/report-skill/<workspace-name>/
```

để không làm bẩn repo và vẫn sống qua nhiều Cursor session. Không commit cache
nếu không có nhu cầu đặc biệt.

## Incremental update

Ở lần cập nhật tiếp theo:

1. CBM `detect_changes` trên repo đã đổi.
2. So sánh current external surface ở repo thay đổi để bắt route/job/consumer
   mới hoặc bị xoá.
3. Chạy `incremental_plan.py` để tìm chức năng hiện có đang tham chiếu cache
   stale/missing.
4. Lấy **hợp** của ba tập trên làm phạm vi phải xác minh lại.
5. Re-trace từng endpoint bị ảnh hưởng. Symbol không đổi sẽ cache HIT; symbol
   đổi sẽ được đọc và cache lại.
6. Cập nhật `spec.json`, rồi chạy validator ở strict evidence mode.

Không được chỉ dựa vào cache audit để kết luận toàn hệ thống không đổi: một
endpoint mới chưa tồn tại trong spec sẽ không có `evidence_refs` cũ để audit.

## Audit

```bash
python <skill>/scripts/evidence_cache.py audit \
  --cache-dir <cache> --workspace <parent-of-repos>
```

Audit dùng range đã cache nên có thể tạo false-stale khi code chỉ dịch dòng.
Điều đó an toàn: dùng CBM resolve symbol hiện tại rồi chạy `get-symbol`; nếu body
thật không đổi, cache sẽ HIT lại.

## Strict validation

```bash
python <skill>/scripts/validate_spec.py spec.json \
  --workspace <parent-of-repos> \
  --cache-dir <cache> \
  --yeu-cau-evidence
```

Khi bật cờ này, mọi chức năng phải có evidence refs và mọi ref phải tồn tại,
không stale, đúng source hiện tại.
