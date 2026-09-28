from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


class UserProfile(models.Model):
    class Role(models.TextChoices):
        TENANT = "tenant", "Khách thuê"
        LANDLORD = "landlord", "Chủ trọ"
        ADMIN = "admin", "Quản trị viên hệ thống"

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.TENANT)
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, default="")
    phone_verified = models.BooleanField(default=False)
    contact_address = models.CharField(max_length=255, blank=True, default="")

    def __str__(self):
        return f"{self.user.username} - {self.get_role_display()}"


class Phong(models.Model):
    class RoomStatus(models.TextChoices):
        AVAILABLE = "available", "Còn trống"
        RENTED = "rented", "Đang thuê"
        MAINTENANCE = "maintenance", "Đang sửa chữa"

    # Chu so huu tin dang
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="rooms", null=True, blank=True)

    # Tieu de tin phong tro
    title = models.CharField(max_length=200, default="Phong moi")

    # Gia thue theo VND/thang
    price = models.DecimalField(max_digits=12, decimal_places=0, default=0)

    # Dien tich phong (m2)
    area = models.DecimalField(max_digits=6, decimal_places=2, default=0)

    # Dia chi chi tiet de tim theo khu vuc
    address = models.CharField(max_length=255, default="")

    # Mo ta chung hien thi cong khai
    description = models.TextField(blank=True, default="")

    # Tien ich va noi that de hien thi thanh section rieng
    amenities = models.TextField(blank=True, default="")
    furnishings = models.TextField(blank=True, default="")

    # So dien thoai chu nha (chi hien thi khi da dang nhap)
    owner_phone = models.CharField(max_length=20, blank=True, default="")

    # Loai phong
    room_type = models.CharField(max_length=100, default="Phong thuong")

    # Hinh anh dai dien phong
    image = models.ImageField(upload_to="rooms/", blank=True, null=True)

    # Thoi diem tao tin dang
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    # Trang thai con trong hay khong
    is_available = models.BooleanField(default=True)
    status = models.CharField(max_length=20, choices=RoomStatus.choices, default=RoomStatus.AVAILABLE)

    # Toa do Google Map
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    def save(self, *args, **kwargs):
        # Dong bo voi field cu de khong vo luong cu
        self.is_available = self.status == self.RoomStatus.AVAILABLE
        super().save(*args, **kwargs)

    def average_rating(self):
        return self.review_set.aggregate(avg=models.Avg("rating"))["avg"] or 0

    def review_count(self):
        return self.review_set.count()

    def primary_image_url(self):
        if self.image:
            return self.image.url
        first_gallery_image = self.gallery_images.order_by("sort_order", "id").first()
        if first_gallery_image and first_gallery_image.image:
            return first_gallery_image.image.url
        return "https://images.unsplash.com/photo-1522708323590-d24dbb6b0267?auto=format&fit=crop&w=1400&q=80"

    def __str__(self):
        return self.title


class RoomImage(models.Model):
    room = models.ForeignKey(Phong, on_delete=models.CASCADE, related_name="gallery_images")
    image = models.ImageField(upload_to="rooms/gallery/")
    caption = models.CharField(max_length=255, blank=True, default="")
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return f"{self.room.title} - H?nh {self.id}"


class Review(models.Model):
    room = models.ForeignKey(Phong, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    rating = models.IntegerField()
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.username} - {self.room.title} ({self.rating})"


class RoomBooking(models.Model):
    class BookingStatus(models.TextChoices):
        PENDING = "pending", "Chờ duyệt"
        APPROVED = "approved", "Đã duyệt/Đã cọc"
        CANCELED = "canceled", "Từ chối"
        WITHDRAWN = "withdrawn", "Đã hủy"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="room_bookings")
    room = models.ForeignKey(Phong, on_delete=models.CASCADE, related_name="bookings")
    tenant_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20)
    father_name = models.CharField(max_length=150)
    father_phone = models.CharField(max_length=20)
    mother_name = models.CharField(max_length=150)
    mother_phone = models.CharField(max_length=20)
    note = models.TextField(blank=True, default="")
    status = models.CharField(max_length=20, choices=BookingStatus.choices, default=BookingStatus.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.username} - {self.room.title} ({self.get_status_display()})"
