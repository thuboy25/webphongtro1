from django.contrib import admin

from .models import Phong, Review, RoomBooking, UserProfile


@admin.register(Phong)
class PhongAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "price", "area", "address", "room_type", "status", "is_available")
    list_filter = ("status", "room_type")
    search_fields = ("title", "address", "room_type")


@admin.register(RoomBooking)
class RoomBookingAdmin(admin.ModelAdmin):
    list_display = ("id", "tenant_name", "user", "room", "phone", "father_phone", "mother_phone", "status", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("tenant_name", "user__username", "room__title", "phone", "father_phone", "mother_phone")


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("id", "room", "user", "rating", "created_at")
    list_filter = ("rating", "created_at")
    search_fields = ("room__title", "user__username", "comment")


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "role")
    list_filter = ("role",)
    search_fields = ("user__username", "user__email")
