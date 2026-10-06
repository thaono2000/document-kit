# CBM-first discovery — dùng graph để tìm đúng code, không dùng graph thay bằng chứng

Mục tiêu của CBM trong skill này là **giảm token khám phá và đọc lặp**, không
phải giảm độ sâu xác minh. Tài liệu đặc tả chỉ được coi là có độ tin cậy cao
khi hành vi đã được đối chiếu với source thật.

## Thứ tự ưu tiên khi codebase-memory-mcp có sẵn

1. `list_projects` — xác nhận repo đã được index.
2. `index_repository` — chỉ khi repo chưa có hoặc người dùng vừa thêm repo mới.
3. `get_graph_schema` — chạy một lần khi cần biết label/edge nào đang có.
4. `get_architecture` — lấy kiến trúc, route, package, boundary tổng thể.
5. `search_graph` — tìm Route/Function/Method/Class liên quan, scope theo `project`.
6. `trace_path` / `trace_call_path` — dựng call chain inbound/outbound.
7. `get_file_outline` — xác định declaration và range trong file khi cần.
8. `get_code_snippet` — lấy **source thật của symbol** để xác minh hành vi.
9. `search_code` — fallback cho framework/dynamic pattern graph chưa resolve.
10. `detect_changes` — bắt buộc ở lần cập nhật incremental.

Không gọi tất cả công cụ theo nghi thức. Dừng discovery ngay khi đã có đủ
route → handler → symbol chain cần đọc.

## Cái gì là discovery, cái gì là evidence

Các kết quả sau chỉ là **discovery evidence**:

- `get_architecture`
- `search_graph`
- `trace_path`
- `detect_changes`
- graph edge như `CALLS`, `HTTP_CALLS`, `CROSS_*`

Chúng cho biết nên đọc ở đâu, nhưng **không đủ** để khẳng định business rule,
validation, error path hoặc side effect.

Một claim về hành vi chỉ được coi là source-verified khi agent đã đọc source
thật qua một trong hai cách:

- `get_code_snippet` trả đầy đủ body của symbol cùng vị trí; hoặc
- mở trực tiếp exact file/range tương ứng.

Nếu snippet bị cắt, dynamic dispatch chưa resolve, code sinh tự động hoặc call
đi ra ngoài phần source đọc được, hạ confidence và nêu gap.

## Multi-repo

Mỗi Git repository là một project CBM riêng. Không gộp nhiều repo thành một
repo giả chỉ để index.

Khi một flow đi qua nhiều repo:

```text
AdminPortal
  -> HTTP endpoint
BookingService
  -> internal HTTP/event
ManagementService
```

hãy trace qua cross-repo edges nếu graph có; ở mỗi repo vẫn lấy source snippet
của symbol thực tế trước khi mô tả hành vi. Mọi neo cuối cùng phải giữ cả
`repo` và `path`.

## Fallback

Nếu CBM không có, index lỗi, hoặc coverage không đủ cho stack hiện tại, quay về
`scan_repo.py`, `extract_surface.py`, grep có kiểm soát và đọc source trực tiếp.

Không được vì CBM thiếu edge mà bỏ qua một entry point đã thấy trong source.

## Source snapshot rule

CBM discovery and source verification run against an exact captured HEAD for every configured repository. DocumentKit re-checks all HEADs immediately before publication; any change aborts the transaction.
