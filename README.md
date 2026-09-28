# Trọ Tốt - Hệ thống quản lý phòng trọ

Ứng dụng web xây dựng bằng Django để quản lý phòng trọ, hỗ trợ 3 nhóm người dùng:

- Khách thuê
- Chủ trọ
- Quản trị viên hệ thống

Project hiện tập trung vào 3 luồng chính:

- xem và tìm kiếm phòng trọ công khai
- chủ trọ đăng và quản lý tin phòng
- người thuê gửi yêu cầu thuê và theo dõi lịch sử đặt phòng

## 1. Tính năng hiện có

### Người dùng công khai
- xem danh sách phòng trọ
- tìm kiếm theo khu vực, mức giá, loại phòng
- xem chi tiết phòng trọ
- xem ảnh gallery nhiều ảnh
- xem đánh giá và bình luận
- gọi điện hoặc chat Zalo trực tiếp nếu tin đăng có số điện thoại
- xem vị trí phòng trên bản đồ

### Khách thuê 
- đăng ký, đăng nhập
- đặt phòng
- xem `Lịch sử đặt phòng`
- theo dõi trạng thái yêu cầu:
  - `Chờ duyệt`
  - `Đã duyệt`
  - `Từ chối`
  - `Đã hủy`
- hủy yêu cầu khi trạng thái còn `Chờ duyệt`

### Chủ trọ 
- đăng tin phòng
- sửa, xóa tin đăng
- tải nhiều ảnh cho một phòng
- quản lý danh sách bài đăng
- xem dashboard yêu cầu thuê
- duyệt hoặc từ chối yêu cầu thuê
- xem trạng thái `Người thuê hủy`

### Quản trị viên (`ADMIN`)
- dashboard quản trị riêng tại `/system-admin/`
- xem thống kê tổng quan
- quản lý danh sách chủ trọ
- quản lý danh sách người thuê
- quản lý toàn bộ phòng trọ

## 2. Công nghệ sử dụng

- Python
- Django 6
- SQL Server qua `mssql-django` + `pyodbc`
- Tailwind CSS và Bootstrap 5 ở các màn hình khác nhau
- Google Maps / bản đồ nhúng
- Pillow để xử lý upload ảnh

## 3. Cấu trúc chính của project

```text
wephongtro/
├─ manage.py
├─ media/
├─ phongtro/
│  ├─ migrations/
│  ├─ static/
│  ├─ templates/
│  ├─ temlates/
│  ├─ templatetags/
│  ├─ admin.py
│  ├─ forms.py
│  ├─ models.py
│  ├─ tests.py
│  ├─ urls.py
│  └─ views.py
└─ wephongtro/
   ├─ settings.py
   ├─ urls.py
   └─ ...
```

## 4. Model chính

### `UserProfile`
Mở rộng `django.contrib.auth.models.User` bằng trường `role`:
- `tenant`
- `landlord`
- `admin`

### `Phong`
Thông tin phòng trọ:
- tiêu đề
- giá
- diện tích
- địa chỉ
- mô tả
- tiện ích
- nội thất
- số điện thoại liên hệ
- loại phòng
- ảnh đại diện
- tọa độ bản đồ
- trạng thái phòng

### `RoomImage`
Cho phép một phòng có nhiều ảnh gallery.

### `Review`
Đánh giá phòng trọ:
- người đánh giá
- số sao
- nội dung bình luận
- thời gian tạo

### `RoomBooking`
Yêu cầu thuê phòng:
- người gửi yêu cầu
- phòng
- thông tin liên hệ
- thông tin phụ huynh
- ghi chú
- trạng thái booking

## 5. Route chính

### Public
- `/` : trang chủ
- `/danh-sach-phong/` : danh sách phòng công khai
- `/rooms/<id>/` : chi tiết phòng
- `/login/` : đăng nhập
- `/register/` : đăng ký
- `/profile/` : thông tin tài khoản

### Khách thuê
- `/rooms/<id>/book/` : gửi yêu cầu thuê phòng
- `/my-bookings/` : lịch sử đặt phòng
- `/my-bookings/<booking_id>/cancel/` : hủy yêu cầu thuê

### Chủ trọ
- `/dashboard/` : quản lý bài đăng
- `/dashboard/add/` : thêm phòng
- `/dashboard/edit/<pk>/` : sửa phòng
- `/dashboard/delete/<pk>/` : xóa phòng
- `/dashboard/bookings/` : quản lý yêu cầu thuê

### Admin
- `/system-admin/` : dashboard quản trị
- `/system-admin/landlords/`
- `/system-admin/tenants/`
- `/system-admin/rooms/`

### Django Admin mặc định
- `/admin/`

## 6. Yêu cầu môi trường

Cần có sẵn:
- Python 3.12+ hoặc tương đương
- SQL Server / SQL Server Express
- ODBC Driver 18 for SQL Server
- pip

Các package Python cần cài tối thiểu:

```bash
pip install django mssql-django pyodbc pillow
```

Nếu muốn cố định dependency, bạn nên tạo thêm `requirements.txt` riêng cho môi trường deploy.

## 7. Cấu hình database

Project hiện đang cấu hình mặc định SQL Server trong [wephongtro/settings.py](wephongtro/settings.py):

- engine: `mssql`
- database: `quan_ly_phong_tro`
- host: `THUBOY\\SQLEXPRESS`
- driver: `ODBC Driver 18 for SQL Server`

Bạn cần sửa lại phần `DATABASES` cho đúng máy local của mình trước khi chạy.

Ví dụ các điểm cần kiểm tra:
- tên instance SQL Server
- tài khoản đăng nhập SQL
- mật khẩu
- quyền tạo database test nếu chạy test

## 8. Biến môi trường

Project có đọc Google Maps API key từ biến môi trường:

```python
GOOGLE_MAPS_API_KEY = os.getenv('GOOGLE_MAPS_API_KEY', '')
```

Thiết lập trên PowerShell:

```powershell
$env:GOOGLE_MAPS_API_KEY="YOUR_GOOGLE_MAPS_API_KEY"
```

Lưu ý: một số màn hình hiện dùng bản đồ nhúng hoặc iframe, nên API key không phải lúc nào cũng bắt buộc.

## 9. Cách chạy local

### Bước 1: tạo môi trường ảo

```bash
python -m venv .venv
```

### Bước 2: kích hoạt môi trường ảo

PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

### Bước 3: cài dependency

```bash
pip install django mssql-django pyodbc pillow
```

### Bước 4: cấu hình database trong `wephongtro/settings.py`

Sửa lại:
- `NAME`
- `USER`
- `PASSWORD`
- `HOST`
- `OPTIONS.driver`

### Bước 5: migrate

```bash
python manage.py migrate
```

### Bước 6: tạo tài khoản admin Django nếu cần

```bash
python manage.py createsuperuser
```

### Bước 7: chạy server

```bash
python manage.py runserver
```

Truy cập:
- app chính: `http://127.0.0.1:8000/`
- Django admin: `http://127.0.0.1:8000/admin/`

## 10. Kiểm tra nhanh

Kiểm tra cấu hình Django:

```bash
python manage.py check
```

Chạy test:

```bash
python manage.py test phongtro.tests
```

Lưu ý thực tế:
- test hiện dùng luôn database engine mặc định là SQL Server
- nếu SQL Server local không kết nối được, test sẽ fail ngay ở bước tạo test database

## 11. Ghi chú quan trọng trong repo hiện tại

### 1. Có 2 thư mục template
Hiện app đang có cả:
- `phongtro/templates/`
- `phongtro/temlates/`

Đây là trạng thái không lý tưởng. Khi sửa giao diện, nên kiểm tra kỹ đang dùng file nào và đồng bộ nếu cần.

### 2. Role không dùng Custom User trực tiếp
Project hiện không thay `AUTH_USER_MODEL`.
Thay vào đó, role được lưu ở `UserProfile` gắn với `User` mặc định của Django.

### 3. Một số file còn dấu vết lỗi mã hóa tiếng Việt
Trong source vẫn còn vài chuỗi cũ bị lỗi hiển thị khi mở bằng terminal hoặc editor không đúng encoding. Template và logic chính đã được chỉnh nhiều phần, nhưng repo vẫn nên được rà soát thêm nếu muốn làm sạch hoàn toàn.

## 12. Hướng phát triển tiếp theo

Các phần hợp lý để làm tiếp:
- thêm `requirements.txt`
- chuẩn hóa hoàn toàn thư mục template
- hồ sơ người dùng đầy đủ
- thêm reset password / quên mật khẩu
- thêm thông báo khi booking được duyệt hoặc từ chối
- thêm filter nâng cao cho danh sách phòng
- thêm export dữ liệu cho admin
- thêm test cho dashboard chủ trọ và admin

### Hồ sơ người dùng đầy đủ

Cụm tính năng này nên được tách thành một nhánh phát triển riêng vì liên quan cả model, form, view, template và cấu hình email:

- ảnh đại diện
- số điện thoại xác thực
- địa chỉ liên hệ
- đổi mật khẩu
- quên mật khẩu qua email

### Thống kê & Báo cáo (Dành cho Quản trị viên)

Thông tin thống kê được tổng hợp từ dữ liệu phòng trọ, danh sách người dùng và lịch sử các giao dịch đặt phòng. Mục tiêu là giúp quản trị viên theo dõi tình trạng vận hành hệ thống theo thời gian thực và nhìn nhanh các chỉ số kinh doanh quan trọng.

Nội dung báo cáo nên bao gồm:

- biểu đồ cột thể hiện số lượng đặt phòng theo thời gian
- biểu đồ tròn thể hiện tỷ lệ lấp đầy phòng
- thống kê số lượng người dùng theo vai trò
- thống kê số phòng theo trạng thái: `Còn trống`, `Đã thuê`, `Đang sửa chữa`
- thống kê lịch sử yêu cầu đặt phòng theo tháng / quý / năm
- báo cáo doanh thu nếu hệ thống có bổ sung dữ liệu thanh toán hoặc hợp đồng thuê

Giá trị sử dụng:

- giúp chủ trọ và quản trị viên nhìn ra tháng nào có nhu cầu đặt phòng cao điểm
- theo dõi nhanh mức độ lấp đầy của các phòng trọ
- đánh giá hiệu suất khai thác phòng
- hỗ trợ ra quyết định về giá, khuyến mãi và phân bổ phòng trống

Gợi ý mở rộng:

- thêm chức năng sửa / xóa / xuất báo cáo thống kê
- thêm bộ lọc theo thời gian, khu vực, chủ trọ, loại phòng
- thêm xuất Excel / CSV cho các báo cáo quản trị

## 13. Tác giả / mục đích

Project này phù hợp làm:
- đồ án môn học
- demo hệ thống quản lý phòng trọ
- nền tảng để phát triển thêm thành sản phẩm quản lý nhà trọ thực tế

---
