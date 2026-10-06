# Cấu trúc `spec.json`

Đây là nguồn sự thật duy nhất. `render_spec.py` đọc file này rồi dựng ra `.md`
và `.xlsx`; vì cùng một nguồn nên hai file không bao giờ lệch nhau, và việc
người dùng chọn định dạng chỉ là một cờ dòng lệnh chứ không phải viết lại lần hai.

Mọi khoá đều không dấu, tiếng Việt viết thường, nối bằng gạch dưới. Mọi **giá
trị** thì viết tiếng Việt có dấu, trừ tên định danh trong mã nguồn (tên hàm,
tên bảng, tên trường, đường dẫn, endpoint) — giữ nguyên để người đọc còn
`grep` được.

## Khung tổng thể

```json
{
  "du_an":            { ... },
  "phan_tich":         { ... },
  "tong_quan_md":     "đoạn văn mô tả hệ thống, chèn vào cuối mục 1",
  "modules":          [ ... ],
  "api":              [ ... ],
  "mo_hinh_du_lieu":  [ ... ],
  "bao_mat":          ["..."],
  "rui_ro":           [ ... ],
  "ghi_chu_md":       "văn xuôi thêm cho mục 5",
  "pham_vi":          { ... }
}
```

## `du_an`

| Khoá | Kiểu | Nội dung |
|---|---|---|
| `ten` | chuỗi | Tên dự án theo README hoặc manifest, không tự đặt tên mới |
| `ngay` | chuỗi | Ngày lập, dạng `YYYY-MM-DD` |
| `commit` | chuỗi | SHA ngắn; để rỗng nếu không phải git repo |
| `nguon` | chuỗi | `FEATURES.md` hoặc `quét trực tiếp mã nguồn` |
| `cong_nghe` | mảng chuỗi | Ngôn ngữ, framework, thư viện chính |
| `kien_truc` | chuỗi | MVC / Clean Architecture / Monolith / Microservices... kèm một câu giải thích |
| `co_so_du_lieu` | chuỗi | Loại DB và cách kết nối |
| `tich_hop` | mảng chuỗi | Dịch vụ bên thứ ba, mỗi dòng `Tên — dùng để làm gì` |
| `diem_khoi_chay` | chuỗi | File khởi chạy và cổng, kèm neo |


## `phan_tich` — metadata phục vụ traceability/incremental

Khối này không cần render cho người đọc cuối, nhưng giúp lần chạy sau biết spec
được tạo theo chiến lược nào và evidence schema nào đang dùng.

```json
{
  "chien_luoc": "cbm-first + symbol-evidence-cache",
  "evidence_schema": "symbol-evidence-v1",
  "repos": {
    "RepitteGlobal-BookingService": {"commit": "abc1234"},
    "RepitteGlobal-AdminPortal": {"commit": "def5678"}
  }
}
```

Không lưu absolute path hoặc cache directory vào `spec.json`; cache là artifact local.

## `modules[]`

Một module = một nhóm chức năng nghiệp vụ. Nếu dựng từ `FEATURES.md` thì mỗi
chức năng trong tài liệu đó thành một module ở đây.

| Khoá | Kiểu | Nội dung |
|---|---|---|
| `ten` | chuỗi | Tên nghiệp vụ, dùng từ vựng của dự án |
| `mo_ta` | chuỗi | Module này phục vụ việc gì, 1–2 câu |
| `doi_tuong` | mảng chuỗi | Ai dùng module này |
| `chuc_nang` | mảng | Các chức năng con, xem dưới |

## `modules[].chuc_nang[]` — phần quan trọng nhất

Đây là thứ phân biệt tài liệu spec với một bản danh sách chức năng. Một chức
năng con thiếu Input / Logic / Output là chức năng **chưa được đặc tả**, dù nó
đã có tên; `validate_spec.py` sẽ báo lỗi.

| Khoá | Kiểu | Nội dung |
|---|---|---|
| `ten` | chuỗi | Tên việc người dùng làm, không phải tên hàm. "Đăng ký tài khoản", không phải `registerHandler` |
| `mo_ta` | chuỗi | 1–2 câu, người không biết code vẫn hiểu |
| `doi_tuong` | mảng chuỗi | Ai được gọi chức năng này |
| `dau_vao` | mảng object | Xem bảng dưới. Không có tham số thì để `[]` và ghi `dau_vao_mo_ta` |
| `dau_vao_mo_ta` | chuỗi | Dùng thay `dau_vao` khi đầu vào không phải dạng trường, ví dụ "file CSV theo mẫu" |
| `luong_xu_ly` | mảng chuỗi | Các bước xử lý theo đúng thứ tự trong mã nguồn |
| `dau_ra` | object | `{"thanh_cong": "...", "loi": ["...", "..."]}` |
| `phan_quyen` | chuỗi | Vai trò được phép, hoặc `Không yêu cầu đăng nhập` |
| `neo` | mảng object | Mỗi neo có dạng `{"repo": "TênRepo", "path": "đường/dẫn.ext:dòng"}`, ít nhất một neo |
| `evidence_refs` | mảng chuỗi | Các key `sym_...` của symbol evidence đã dùng để kết luận chức năng. Khi chạy strict cache validation, mọi ref phải tồn tại và còn khớp source |
| `do_tin_cay` | chuỗi | `cao` / `trung bình` / `thấp` — thấp thì phải nêu lý do trong `ghi_chu` |
| `ghi_chu` | chuỗi | Lỗi, thiếu sót, hành vi gây bất ngờ. Bỏ trống nếu thật sự không có |

### Quy ước `neo` cho single-repo và multi-repo

Dùng **object**, không dùng chuỗi thuần, để một tài liệu có thể chứa neo từ nhiều repository mà không bị mơ hồ:

```json
"neo": [
  {
    "repo": "RepitteGlobal-BookingService",
    "path": "src/controllers/BookingController.php:83"
  }
]
```

- `repo` là tên repository ổn định, thường là tên thư mục Git repo.
- `path` luôn là đường dẫn **tương đối bên trong repo**, kèm `:dòng` hoặc `:dòng-bắt-đầu-dòng-kết-thúc`.
- Không ghi đường dẫn tuyệt đối của máy phát triển vào JSON.
- Với tài liệu multi-repo, mọi neo phải có `repo`.
- `validate_spec.py` hỗ trợ `--workspace <thư_mục_cha>` hoặc nhiều `--repo-root NAME=PATH`.
- Chuỗi neo kiểu cũ vẫn được validator/renderer đọc để tương thích ngược, nhưng khi tạo mới phải dùng object.


### `evidence_refs` và nguyên tắc không đọc lặp

Mỗi endpoint/chức năng vẫn được phân tích riêng, nhưng cùng một function/method
không cần source-analysis lại nếu body hash không đổi. Sau khi trace endpoint, ghi
tất cả symbol evidence thực sự dùng vào:

```json
"evidence_refs": [
  "sym_35f0c0d4a3b7a22f11b1f912",
  "sym_98718d5dcfe0390a1e0c781a"
]
```

- Ref phải bao phủ cả downstream symbol được dùng để kết luận, không chỉ handler đầu tiên.
- `evidence_refs` là traceability nội bộ; renderer không cần đưa chúng vào phần business-facing.
- Không reuse business sentence giữa endpoint chỉ vì chúng dùng chung symbol. Chỉ reuse intrinsic symbol evidence.
- Nếu cache ref stale/missing, chức năng phải được re-trace trước khi strict validation ĐẠT.

### `dau_vao[]`

```json
{"ten": "email", "kieu": "chuỗi", "bat_buoc": true, "rang_buoc": "đúng định dạng email, không trùng với tài khoản đã có"}
```

`rang_buoc` chỉ ghi khi mã nguồn thật sự có kiểm tra. Nếu code không validate
gì cả thì ghi đúng như vậy — "không kiểm tra" là một thông tin quan trọng với
người nghiệm thu, không phải chỗ trống để lấp.

## `api[]`

```json
{"phuong_thuc": "POST", "endpoint": "/api/v1/auth/register", "chuc_nang": "Đăng ký tài khoản",
 "tham_so": "{email, password}", "phan_hoi": "201 {\"success\": true}",
 "quyen": "Không yêu cầu đăng nhập",
 "neo": [{"repo": "RepitteGlobal-BookingService", "path": "src/routes/auth.js:7"}]}
```

`endpoint` phải là đường dẫn đầy đủ gọi được, đã ghép tiền tố mount. Dự án
không có API HTTP thì để mảng rỗng.

## `mo_hinh_du_lieu[]`

```json
{"ten": "orders", "mo_ta": "Đơn hàng và trạng thái vòng đời",
 "neo": [{"repo": "RepitteGlobal-BookingService", "path": "src/models/Order.js:14"}],
 "truong": [{"ten": "status", "kieu": "chuỗi", "rang_buoc": "thuộc 5 giá trị cho trước",
             "y_nghia": "trạng thái đơn: chờ thanh toán, đã trả tiền, giao hàng, huỷ"}]}
```

Chỉ liệt kê trường có ý nghĩa nghiệp vụ. `createdAt`, `_id`, `__v` không cần
trừ khi chúng tham gia vào logic.

## `rui_ro[]`

```json
{"muc_do": "cao", "hang_muc": "Thanh toán", "van_de": "...", "anh_huong": "...",
 "neo": [{"repo": "RepitteGlobal-BookingService", "path": "src/routes/orders.js:34"}],
 "cau_hoi": "Đội cũ có xử lý tay trường hợp này không?"}
```

`muc_do` nhận `cao` / `trung bình` / `thấp` — sheet Rủi ro tô màu theo giá trị
này nên viết đúng chính tả. `cau_hoi` là chỗ đặt những gì mã nguồn không trả
lời được; để trống nếu không có gì phải hỏi.

Ba loại nội dung thuộc về đây: lỗi thật đọc được trong mã nguồn, chỗ thiếu
(không validate, không try/catch, truy vấn N+1), và đoạn mã không rõ chức năng
— thư viện lạ, code bị làm rối. Loại thứ ba phải ghi nhận chứ không được đoán
bừa; đó chính là lý do có cột `cau_hoi`.

## `pham_vi`

```json
{"da_quet": ["..."], "bo_qua": ["..."], "chua_ro": ["..."], "ma_chet": ["..."]}
```

Mục này làm cho phần còn lại đáng tin. Người đọc phát hiện ra một lỗ hổng mà
bạn đã tự khai thì vẫn tin phần còn lại; phát hiện ra một lỗ hổng bị giấu thì
không tin gì nữa.

## Quy ước chung

- Không để chữ mẫu trong ngoặc vuông, `{VIẾT_HOA}`, `TODO` — `validate_spec.py`
  coi đó là lỗi.
- Không viết câu rỗng kiểu "xử lý logic nghiệp vụ", "thao tác với dữ liệu".
  Nếu không biết nó làm gì thì để `do_tin_cay` là `thấp` và nêu lý do.
- Mỗi neo trỏ vào dòng **bắt đầu** của đoạn mã liên quan, không phải dòng giữa. Với multi-repo, luôn ghi cả `repo` và `path`.
