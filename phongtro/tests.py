from pathlib import Path
from tempfile import TemporaryDirectory
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from unittest.mock import PropertyMock, patch

from .models import Phong, RoomBooking, UserProfile


class TenantBookingCenterTests(TestCase):
    def setUp(self):
        self.landlord = User.objects.create_user(username="landlord", password="testpass123")
        UserProfile.objects.create(user=self.landlord, role=UserProfile.Role.LANDLORD)

        self.tenant = User.objects.create_user(username="tenant", password="testpass123")
        UserProfile.objects.create(user=self.tenant, role=UserProfile.Role.TENANT)

        self.other_tenant = User.objects.create_user(username="tenant2", password="testpass123")
        UserProfile.objects.create(user=self.other_tenant, role=UserProfile.Role.TENANT)

        self.room = Phong.objects.create(
            owner=self.landlord,
            title="Phòng thử nghiệm",
            price=2500000,
            area=25,
            address="TP. Thái Nguyên",
            room_type="Phòng thường",
            owner_phone="0912345678",
            status=Phong.RoomStatus.AVAILABLE,
        )

    def test_my_bookings_requires_login(self):
        response = self.client.get(reverse("phongtro:my_bookings"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("phongtro:login"), response.url)

    def test_landlord_cannot_access_tenant_booking_center(self):
        self.client.force_login(self.landlord)

        response = self.client.get(reverse("phongtro:my_bookings"))

        self.assertRedirects(response, reverse("phongtro:home_page"))

    def test_my_bookings_only_shows_current_users_requests(self):
        own_booking = RoomBooking.objects.create(
            user=self.tenant,
            room=self.room,
            tenant_name="Nguyen Van A",
            phone="0911111111",
            father_name="Bo A",
            father_phone="0911222222",
            mother_name="Me A",
            mother_phone="0911333333",
        )
        other_booking = RoomBooking.objects.create(
            user=self.other_tenant,
            room=self.room,
            tenant_name="Nguyen Van B",
            phone="0922222222",
            father_name="Bo B",
            father_phone="0922333333",
            mother_name="Me B",
            mother_phone="0922444444",
        )

        self.client.force_login(self.tenant)
        response = self.client.get(reverse("phongtro:my_bookings"))

        self.assertEqual(response.status_code, 200)
        bookings = list(response.context["bookings"])
        self.assertIn(own_booking, bookings)
        self.assertNotIn(other_booking, bookings)

    def test_pending_booking_can_be_canceled_by_owner(self):
        booking = RoomBooking.objects.create(
            user=self.tenant,
            room=self.room,
            tenant_name="Nguyen Van A",
            phone="0911111111",
            father_name="Bo A",
            father_phone="0911222222",
            mother_name="Me A",
            mother_phone="0911333333",
        )

        self.client.force_login(self.tenant)
        response = self.client.post(reverse("phongtro:cancel_my_booking", args=[booking.id]))

        booking.refresh_from_db()
        self.assertRedirects(response, reverse("phongtro:my_bookings"))
        self.assertEqual(booking.status, RoomBooking.BookingStatus.WITHDRAWN)

    def test_non_pending_booking_cannot_be_canceled(self):
        booking = RoomBooking.objects.create(
            user=self.tenant,
            room=self.room,
            tenant_name="Nguyen Van A",
            phone="0911111111",
            father_name="Bo A",
            father_phone="0911222222",
            mother_name="Me A",
            mother_phone="0911333333",
            status=RoomBooking.BookingStatus.APPROVED,
        )

        self.client.force_login(self.tenant)
        response = self.client.post(reverse("phongtro:cancel_my_booking", args=[booking.id]))

        booking.refresh_from_db()
        self.assertRedirects(response, reverse("phongtro:my_bookings"))
        self.assertEqual(booking.status, RoomBooking.BookingStatus.APPROVED)

    def test_book_room_redirects_to_my_bookings(self):
        self.client.force_login(self.tenant)

        response = self.client.post(
            reverse("phongtro:book_room", args=[self.room.id]),
            {
                "tenant_name": "Nguyen Van A",
                "phone": "0911111111",
                "father_name": "Bo A",
                "father_phone": "0911222222",
                "mother_name": "Me A",
                "mother_phone": "0911333333",
                "note": "Muon vao o tu thang sau",
            },
        )

        self.assertRedirects(response, reverse("phongtro:my_bookings"))
        self.assertTrue(RoomBooking.objects.filter(user=self.tenant, room=self.room).exists())


class AccountProfileTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="profileuser",
            email="old@example.com",
            password="testpass123",
        )
        self.profile = UserProfile.objects.create(
            user=self.user,
            role=UserProfile.Role.TENANT,
            phone="0911111111",
            phone_verified=True,
            contact_address="Địa chỉ cũ",
        )

    def test_profile_update_resets_phone_verification_when_phone_changes(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("phongtro:profile"),
            {
                "form_type": "profile",
                "email": "new@example.com",
                "phone": "0922222222",
                "contact_address": "Địa chỉ mới",
            },
        )

        self.profile.refresh_from_db()
        self.user.refresh_from_db()
        self.assertRedirects(response, reverse("phongtro:profile"))
        self.assertEqual(self.user.email, "new@example.com")
        self.assertEqual(self.profile.phone, "0922222222")
        self.assertEqual(self.profile.contact_address, "Địa chỉ mới")
        self.assertFalse(self.profile.phone_verified)

    def test_profile_page_contains_password_reset_link(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("phongtro:profile"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("phongtro:password_reset"))


@override_settings(SECURE_SSL_REDIRECT=False)
class ImageUploadUrlTests(TestCase):
    def test_uploaded_media_is_served_when_debug_is_disabled(self):
        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            image_path = Path(media_root) / "rooms" / "uploaded-room.jpg"
            image_path.parent.mkdir(parents=True)
            image_path.write_bytes(b"uploaded-image-bytes")

            response = self.client.get("/media/rooms/uploaded-room.jpg")

            self.assertEqual(response.status_code, 200)
            self.assertEqual(b"".join(response.streaming_content), b"uploaded-image-bytes")

    def test_room_safe_image_url_prefers_uploaded_file_url_even_when_storage_check_fails(self):
        room = Phong.objects.create(
            title="Phòng test",
            price=2000000,
            area=20,
            address="Thái Nguyên",
            room_type="Phòng thường",
            status=Phong.RoomStatus.AVAILABLE,
        )

        room.image.save(
            "room-cover.jpg",
            SimpleUploadedFile("room-cover.jpg", b"image-bytes", content_type="image/jpeg"),
            save=False,
        )

        with patch.object(room.image.storage, "exists", return_value=False):
            url = room.safe_image_url()

        self.assertTrue(url.startswith("/media/rooms/"))
        self.assertNotIn("images.unsplash.com", url)

    def test_room_safe_image_url_falls_back_to_media_path_when_url_property_fails(self):
        room = Phong.objects.create(
            title="Phòng fallback",
            price=2000000,
            area=20,
            address="Thái Nguyên",
            room_type="Phòng thường",
            status=Phong.RoomStatus.AVAILABLE,
        )

        room.image.save(
            "fallback-room.jpg",
            SimpleUploadedFile("fallback-room.jpg", b"image-bytes", content_type="image/jpeg"),
            save=False,
        )

        with patch("django.db.models.fields.files.FieldFile.url", new_callable=PropertyMock, side_effect=ValueError("url unavailable")):
            url = room.safe_image_url()

        self.assertEqual(url, "/media/rooms/fallback-room.jpg")

    def test_room_detail_uses_uploaded_cover_for_main_image_and_thumbnail(self):
        room = Phong.objects.create(
            title="Phòng có ảnh gốc",
            price=2000000,
            area=20,
            address="Thái Nguyên",
            room_type="Phòng thường",
            status=Phong.RoomStatus.AVAILABLE,
        )
        room.image.save(
            "original-upload.jpg",
            SimpleUploadedFile("original-upload.jpg", b"original-image", content_type="image/jpeg"),
        )

        response = self.client.get(reverse("phongtro:room_detail", args=[room.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, room.image.url)
        self.assertContains(response, "data-image-url=\"" + room.image.url + "\"")
        self.assertNotContains(response, "unsplash.com")
        self.assertNotContains(response, "pexels.com")

        image_response = self.client.get(room.image.url)
        self.assertEqual(image_response.status_code, 200)
        self.assertEqual(b"".join(image_response.streaming_content), b"original-image")

    def test_room_gallery_url_uses_uploaded_file_url_even_when_storage_check_fails(self):
        room = Phong.objects.create(
            title="Phòng gallery",
            price=1800000,
            area=18,
            address="Thái Nguyên",
            room_type="Phòng thường",
            status=Phong.RoomStatus.AVAILABLE,
        )

        gallery = room.gallery_images.create(
            image=SimpleUploadedFile("gallery-1.jpg", b"image-bytes", content_type="image/jpeg"),
        )

        with patch.object(gallery.image.storage, "exists", side_effect=RuntimeError("storage backend unavailable")):
            url = room.safe_image_url()

        self.assertTrue(url.startswith("/media/rooms/"))
        self.assertNotIn("images.unsplash.com", url)
