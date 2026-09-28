from collections import OrderedDict
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.conf import settings
from urllib.parse import quote_plus

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import IntegrityError
from django.db.models import Count, Prefetch, Q
from django.db.models.functions import TruncDate, TruncMonth
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import CreateView, DeleteView, ListView, TemplateView, UpdateView

from .forms import AccountPasswordChangeForm, AccountProfileForm, LoginForm, RegisterForm, RoomForm
from .models import Phong, Review, RoomBooking, RoomImage, UserProfile


def _save_room_gallery(room, uploaded_files):
    """
    Lưu các ảnh phụ cho phòng trọ.
    Ảnh đại diện vẫn được giữ ở `Phong.image`, còn gallery được tách sang `RoomImage`.
    """
    if not uploaded_files:
        return

    existing_count = room.gallery_images.count()
    gallery_items = []
    for index, uploaded_file in enumerate(uploaded_files, start=existing_count):
        gallery_items.append(
            RoomImage(
                room=room,
                image=uploaded_file,
                sort_order=index,
            )
        )

    if gallery_items:
        RoomImage.objects.bulk_create(gallery_items)


def _get_or_create_user_profile(user):
    if not user or not user.is_authenticated:
        return None

    defaults = {"role": UserProfile.Role.TENANT}
    if user.is_superuser:
        defaults["role"] = UserProfile.Role.ADMIN
    elif user.is_staff:
        defaults["role"] = UserProfile.Role.LANDLORD

    profile, created = UserProfile.objects.get_or_create(user=user, defaults=defaults)
    if created:
        return profile

    expected_role = None
    if user.is_superuser and profile.role != UserProfile.Role.ADMIN:
        expected_role = UserProfile.Role.ADMIN
    elif not user.is_superuser and profile.role == UserProfile.Role.ADMIN:
        expected_role = UserProfile.Role.LANDLORD if user.is_staff else UserProfile.Role.TENANT

    if expected_role and profile.role != expected_role:
        profile.role = expected_role
        profile.save(update_fields=["role"])
    return profile


def _get_user_role(user):
    profile = _get_or_create_user_profile(user)
    return profile.role if profile else UserProfile.Role.TENANT


def _can_manage_posts(user):
    return user.is_authenticated and _get_user_role(user) in {
        UserProfile.Role.LANDLORD,
        UserProfile.Role.ADMIN,
    }


def _room_has_active_tenant(room):
    return room.status == Phong.RoomStatus.RENTED or room.bookings.filter(
        status=RoomBooking.BookingStatus.APPROVED
    ).exists()


def _get_google_maps_context():
    return {"google_maps_api_key": getattr(settings, "GOOGLE_MAPS_API_KEY", "")}


def _get_auth_context(request):
    role = _get_user_role(request.user) if request.user.is_authenticated else ""
    return {
        "auth_role": role,
        "is_admin_role": role == UserProfile.Role.ADMIN,
        "can_manage_posts": _can_manage_posts(request.user),
        "login_role_choices": LoginForm().fields["role"].choices,
        "register_role_choices": RegisterForm().fields["role"].choices,
    }


def _build_public_home_context(request):
    rooms = Phong.objects.filter(status=Phong.RoomStatus.AVAILABLE)

    khu_vuc = request.GET.get("khu_vuc", "").strip()
    khoang_gia = request.GET.get("khoang_gia", "").strip()
    loai_phong = request.GET.get("loai_phong", "").strip()

    if khu_vuc:
        rooms = rooms.filter(address__icontains=khu_vuc)

    if khoang_gia == "duoi-2":
        rooms = rooms.filter(price__lte=2000000)
    elif khoang_gia == "2-4":
        rooms = rooms.filter(price__gte=2000000, price__lte=4000000)
    elif khoang_gia == "4-6":
        rooms = rooms.filter(price__gte=4000000, price__lte=6000000)
    elif khoang_gia == "tren-6":
        rooms = rooms.filter(price__gte=6000000)

    if loai_phong:
        rooms = rooms.filter(room_type__icontains=loai_phong)

    context = {
        "rooms": rooms.order_by("-id"),
        "selected_khu_vuc": khu_vuc,
        "selected_khoang_gia": khoang_gia,
        "selected_loai_phong": loai_phong,
    }
    context.update(_get_auth_context(request))
    context.update(_get_google_maps_context())
    return context


def home_page(request):
    if request.user.is_authenticated and _get_user_role(request.user) == UserProfile.Role.ADMIN:
        return redirect("phongtro:admin_dashboard")

    return render(request, "phongtro/home.html", _build_public_home_context(request))


def public_home_page(request):
    """
    Trang xem danh sách phòng công khai.
    """
    context = _build_public_home_context(request)
    return render(request, "phongtro/home.html", context)


def _split_feature_text(raw_value):
    if not raw_value:
        return []

    normalized_value = raw_value.replace("\r", "")
    if "\n" in normalized_value:
        parts = normalized_value.split("\n")
    else:
        parts = normalized_value.split(",")

    return [part.strip(" -?\t") for part in parts if part.strip()]


def room_detail(request, room_id):
    room = get_object_or_404(
        Phong.objects.select_related("owner").prefetch_related(
            Prefetch("gallery_images", queryset=RoomImage.objects.order_by("sort_order", "id")),
            Prefetch("review_set", queryset=Review.objects.select_related("user").order_by("-created_at")),
        ),
        id=room_id,
        status=Phong.RoomStatus.AVAILABLE,
    )

    if room.latitude is not None and room.longitude is not None:
        raw_map_query = f"{room.latitude},{room.longitude}"
    else:
        raw_map_query = room.address.strip()
        if raw_map_query and "Th?i Nguy?n" not in raw_map_query:
            raw_map_query = f"{raw_map_query}, Th?i Nguy?n, Vi?t Nam"

    gallery_urls = [{"url": room.primary_image_url(), "caption": room.title}]
    gallery_urls.extend(
        [
            {
                "url": image.image.url,
                "caption": image.caption or room.title,
            }
            for image in room.gallery_images.all()
            if image.image
        ]
    )

    context = {
        "room": room,
        "reviews": list(room.review_set.all()),
        "gallery_urls": gallery_urls,
        "amenities": _split_feature_text(room.amenities),
        "furnishings": _split_feature_text(room.furnishings),
        "next_url": request.get_full_path(),
        "room_map_query": quote_plus(raw_map_query) if raw_map_query else quote_plus("Th?i Nguy?n, Vi?t Nam"),
    }
    context.update(_get_auth_context(request))
    return render(request, "phongtro/room_detail.html", context)


@login_required
@require_http_methods(["POST"])
def add_review(request, room_id):
    room = get_object_or_404(Phong, id=room_id, status=Phong.RoomStatus.AVAILABLE)

    rating_raw = request.POST.get("rating", "").strip()
    comment = request.POST.get("comment", "").strip()

    try:
        rating = int(rating_raw)
    except (TypeError, ValueError):
        messages.error(request, "Số sao không hợp lệ.")
        return redirect("phongtro:room_detail", room_id=room.id)

    if rating < 1 or rating > 5:
        messages.error(request, "Số sao phải từ 1 đến 5.")
        return redirect("phongtro:room_detail", room_id=room.id)

    if not comment:
        messages.error(request, "Vui lòng nhập nội dung bình luận.")
        return redirect("phongtro:room_detail", room_id=room.id)

    Review.objects.create(
        room=room,
        user=request.user,
        rating=rating,
        comment=comment,
    )
    messages.success(request, "Gửi đánh giá thành công.")
    return redirect("phongtro:room_detail", room_id=room.id)


@login_required
@require_http_methods(["GET", "POST"])
def book_room(request, room_id):
    room = get_object_or_404(Phong, id=room_id, is_available=True)

    if request.method == "POST":
        tenant_name = request.POST.get("tenant_name", "").strip()
        phone = request.POST.get("phone", "").strip()
        father_name = request.POST.get("father_name", "").strip()
        father_phone = request.POST.get("father_phone", "").strip()
        mother_name = request.POST.get("mother_name", "").strip()
        mother_phone = request.POST.get("mother_phone", "").strip()
        note = request.POST.get("note", "").strip()

        if not tenant_name or not phone or not father_name or not father_phone or not mother_name or not mother_phone:
            messages.error(request, "Vui lòng nhập đầy đủ thông tin người thuê và số điện thoại bố/mẹ.")
            return render(request, "phongtro/booking_form.html", {"room": room})

        RoomBooking.objects.create(
            user=request.user,
            room=room,
            tenant_name=tenant_name,
            phone=phone,
            father_name=father_name,
            father_phone=father_phone,
            mother_name=mother_name,
            mother_phone=mother_phone,
            note=note,
        )
        messages.success(request, "Bạn đã gửi yêu cầu đặt phòng thành công!")
        return redirect("phongtro:my_bookings")

    return render(request, "phongtro/booking_form.html", {"room": room})


@login_required
def profile_view(request):
    profile = _get_or_create_user_profile(request.user)

    profile_form = AccountProfileForm(instance=profile, user=request.user)
    password_form = AccountPasswordChangeForm(user=request.user)

    if request.method == "POST":
        form_type = request.POST.get("form_type", "").strip()

        if form_type == "profile":
            profile_form = AccountProfileForm(request.POST, request.FILES, instance=profile, user=request.user)
            if profile_form.is_valid():
                profile_form.save()
                messages.success(request, "Đã cập nhật thông tin tài khoản.")
                return redirect("phongtro:profile")
            messages.error(request, "Thông tin tài khoản chưa hợp lệ. Vui lòng kiểm tra lại.")

        elif form_type == "password":
            password_form = AccountPasswordChangeForm(user=request.user, data=request.POST)
            if password_form.is_valid():
                user = password_form.save()
                update_session_auth_hash(request, user)
                messages.success(request, "Đổi mật khẩu thành công.")
                return redirect("phongtro:profile")
            messages.error(request, "Không thể đổi mật khẩu. Vui lòng kiểm tra lại các trường.")

    return render(
        request,
        "phongtro/profile.html",
        {
            "profile_role": profile,
            "is_admin_role": profile.role == UserProfile.Role.ADMIN,
            "can_manage_posts": _can_manage_posts(request.user),
            "show_my_bookings": profile.role == UserProfile.Role.TENANT,
            "pending_booking_count": RoomBooking.objects.filter(
                user=request.user,
                status=RoomBooking.BookingStatus.PENDING,
            ).count(),
            "profile_form": profile_form,
            "password_form": password_form,
        },
    )


def _resolve_username(identifier):
    if not identifier:
        return ""

    if "@" in identifier:
        user = User.objects.filter(email__iexact=identifier).first()
        if user:
            return user.username
    return identifier


def _generate_username_from_email_or_name(email, full_name):
    base = ""
    if email and "@" in email:
        base = email.split("@")[0].strip()
    elif full_name:
        base = "".join(full_name.lower().split())
    if not base:
        base = "user"

    username = base
    index = 1
    while User.objects.filter(username=username).exists():
        username = f"{base}{index}"
        index += 1
    return username


def _safe_next_url(request):
    next_url = request.POST.get("next") or request.GET.get("next") or ""
    if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        return next_url
    return ""


@require_http_methods(["GET", "POST"])
def login_user(request):
    """
    Dang nhap va quay lai trang nguoi dung dang xem (neu co `next`).
    """
    if request.user.is_authenticated:
        return redirect("phongtro:home_page")

    if request.method == "POST":
        form = LoginForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Vui lòng nhập đầy đủ thông tin đăng nhập.")
            return redirect(_safe_next_url(request) or "phongtro:home_page")

        identifier = form.cleaned_data["identifier"].strip()
        password = form.cleaned_data["password"]
        selected_role = form.cleaned_data["role"]
        username = _resolve_username(identifier)

        user = authenticate(request, username=username, password=password)
        if user is not None:
            actual_role = _get_user_role(user)
            if selected_role != actual_role:
                messages.info(request, "Hệ thống đã đăng nhập theo đúng quyền thực tế của tài khoản.")
            login(request, user)
            messages.success(request, "Đăng nhập thành công. Chào mừng bạn quay lại.")
            return redirect(_safe_next_url(request) or "phongtro:home_page")

        messages.error(request, "Thông tin đăng nhập không hợp lệ.")
        return redirect(_safe_next_url(request) or "phongtro:home_page")

    return render(
        request,
        "phongtro/login.html",
        {
            "login_role_choices": LoginForm().fields["role"].choices,
        },
    )


@require_http_methods(["POST"])
def register_user(request):
    """
    Dang ky user moi va tu dong dang nhap.
    Sau khi dang ky thanh cong, quay lai trang chi tiet dang xem do (`next`).
    """
    if request.user.is_authenticated:
        return redirect("phongtro:home_page")

    form = RegisterForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Vui lòng nhập đầy đủ và đúng thông tin đăng ký.")
        return redirect(_safe_next_url(request) or "phongtro:home_page")

    full_name = form.cleaned_data["full_name"].strip()
    email = form.cleaned_data["email"].strip().lower()
    password = form.cleaned_data["password"]
    confirm_password = form.cleaned_data["confirm_password"]
    selected_role = form.cleaned_data["role"]

    if selected_role == UserProfile.Role.ADMIN:
        messages.error(request, "Bạn không thể tự đăng ký tài khoản quản trị.")
        return redirect(_safe_next_url(request) or "phongtro:home_page")

    if password != confirm_password:
        messages.error(request, "Mật khẩu nhập lại không khớp.")
        return redirect(_safe_next_url(request) or "phongtro:home_page")

    if User.objects.filter(email__iexact=email).exists():
        messages.error(request, "Email đã tồn tại.")
        return redirect(_safe_next_url(request) or "phongtro:home_page")

    username = _generate_username_from_email_or_name(email, full_name)
    first_name = full_name.split(" ", 1)[0]
    last_name = full_name.split(" ", 1)[1] if " " in full_name else ""

    try:
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            is_staff=False,
        )
    except IntegrityError:
        messages.error(request, "Không thể tạo tài khoản, vui lòng thử lại.")
        return redirect(_safe_next_url(request) or "phongtro:home_page")

    UserProfile.objects.create(user=user, role=selected_role)

    login(request, user)
    messages.success(request, "Đăng ký thành công. Chào mừng bạn đến với Trọ Tốt.")
    return redirect(_safe_next_url(request) or "phongtro:home_page")


@require_http_methods(["GET", "POST"])
def login_view(request):
    # Alias de giu tuong thich voi code cu
    return login_user(request)


@require_http_methods(["POST"])
def register_view(request):
    # Alias de giu tuong thich voi code cu
    return register_user(request)


@login_required
def logout_view(request):
    logout(request)
    return redirect("phongtro:home_page")


@require_http_methods(["GET", "POST"])
@login_required
def create_room(request):
    """
    Legacy endpoint: giu lai de tuong thich.
    """
    if not _can_manage_posts(request.user):
        return HttpResponseForbidden("Ban khong co quyen truy cap")

    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        price_raw = request.POST.get("price", "").strip()
        area_raw = request.POST.get("area", "").strip()
        address = request.POST.get("address", "").strip()
        khu_vuc = request.POST.get("khu_vuc", "").strip()
        room_type = request.POST.get("room_type", "").strip() or "Phong thuong"
        status = request.POST.get("status", Phong.RoomStatus.AVAILABLE).strip() or Phong.RoomStatus.AVAILABLE
        description = request.POST.get("description", "").strip()
        owner_phone = request.POST.get("owner_phone", "").strip()
        image = request.FILES.get("image")
        gallery_images = request.FILES.getlist("gallery_images")
        latitude_raw = request.POST.get("latitude", "").strip()
        longitude_raw = request.POST.get("longitude", "").strip()

        if not title or not price_raw or not area_raw or not address:
            messages.error(request, "Vui long nhap day du tieu de, gia, dien tich va dia chi.")
            context = _get_google_maps_context()
            return render(request, "phongtro/create_room.html", context)

        try:
            price = Decimal(price_raw)
            area = Decimal(area_raw)
        except (InvalidOperation, ValueError):
            messages.error(request, "Gia hoac dien tich khong dung dinh dang so.")
            context = _get_google_maps_context()
            return render(request, "phongtro/create_room.html", context)

        latitude = None
        longitude = None
        if latitude_raw and longitude_raw:
            try:
                latitude = Decimal(latitude_raw)
                longitude = Decimal(longitude_raw)
            except (InvalidOperation, ValueError):
                messages.error(request, "Toa do Google Maps khong hop le.")
                context = _get_google_maps_context()
                return render(request, "phongtro/create_room.html", context)

        if khu_vuc and khu_vuc.lower() not in address.lower():
            address = f"{address}, {khu_vuc}" if address else khu_vuc

        room = Phong.objects.create(
            owner=request.user,
            title=title,
            price=price,
            area=area,
            address=address,
            room_type=room_type,
            status=status,
            description=description,
            owner_phone=owner_phone,
            image=image,
            latitude=latitude,
            longitude=longitude,
        )
        _save_room_gallery(room, gallery_images)
        messages.success(request, "Them phong moi thanh cong.")
        return redirect("phongtro:home_page")

    return render(request, "phongtro/create_room.html", _get_google_maps_context())


class StaffOnlyMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return _can_manage_posts(self.request.user)

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            messages.error(self.request, "Bạn không có quyền đăng hoặc quản lý tin.")
            return redirect("phongtro:home_page")
        return super().handle_no_permission()


class AdminRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_superuser or _get_user_role(self.request.user) == UserProfile.Role.ADMIN

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            messages.error(self.request, "Bạn không có quyền truy cập trang quản trị hệ thống.")
            return redirect("phongtro:home_page")
        return super().handle_no_permission()


class OwnerObjectMixin(StaffOnlyMixin):
    raise_exception = True

    def test_func(self):
        obj = self.get_object()
        return super().test_func() and obj.owner_id == self.request.user.id


class RoomDashboardListView(StaffOnlyMixin, ListView):
    model = Phong
    template_name = "phongtro/dashboard.html"
    context_object_name = "rooms"

    def get_queryset(self):
        return (
            Phong.objects.filter(owner=self.request.user)
            .annotate(
                total_bookings=Count("bookings"),
                pending_bookings=Count("bookings", filter=Q(bookings__status=RoomBooking.BookingStatus.PENDING)),
                approved_bookings=Count("bookings", filter=Q(bookings__status=RoomBooking.BookingStatus.APPROVED)),
            )
            .order_by("-id")
        )


class RoomBookingDashboardView(StaffOnlyMixin, ListView):
    model = RoomBooking
    template_name = "phongtro/booking_dashboard.html"
    context_object_name = "bookings"
    paginate_by = 20

    def get_queryset(self):
        queryset = (
            RoomBooking.objects.filter(room__owner=self.request.user)
            .select_related("room", "user")
            .order_by("-created_at")
        )
        status = self.request.GET.get("status", "").strip()
        if status in {
            RoomBooking.BookingStatus.PENDING,
            RoomBooking.BookingStatus.APPROVED,
            RoomBooking.BookingStatus.CANCELED,
            RoomBooking.BookingStatus.WITHDRAWN,
        }:
            queryset = queryset.filter(status=status)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        base_queryset = RoomBooking.objects.filter(room__owner=self.request.user)
        context["selected_status"] = self.request.GET.get("status", "").strip()
        context["total_bookings"] = base_queryset.count()
        context["pending_count"] = base_queryset.filter(status=RoomBooking.BookingStatus.PENDING).count()
        context["approved_count"] = base_queryset.filter(status=RoomBooking.BookingStatus.APPROVED).count()
        context["rejected_count"] = base_queryset.filter(status=RoomBooking.BookingStatus.CANCELED).count()
        context["withdrawn_count"] = base_queryset.filter(status=RoomBooking.BookingStatus.WITHDRAWN).count()
        return context


class TenantBookingListView(LoginRequiredMixin, ListView):
    model = RoomBooking
    template_name = "phongtro/my_bookings.html"
    context_object_name = "bookings"
    paginate_by = 10

    def dispatch(self, request, *args, **kwargs):
        if _get_user_role(request.user) != UserProfile.Role.TENANT:
            messages.error(request, "Chỉ tài khoản người thuê mới có trung tâm yêu cầu thuê.")
            return redirect("phongtro:home_page")
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        queryset = (
            RoomBooking.objects.filter(user=self.request.user)
            .select_related("room", "room__owner")
            .order_by("-created_at")
        )
        status = self.request.GET.get("status", "").strip()
        if status in {
            RoomBooking.BookingStatus.PENDING,
            RoomBooking.BookingStatus.APPROVED,
            RoomBooking.BookingStatus.CANCELED,
            RoomBooking.BookingStatus.WITHDRAWN,
        }:
            queryset = queryset.filter(status=status)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        base_queryset = RoomBooking.objects.filter(user=self.request.user)
        context["selected_status"] = self.request.GET.get("status", "").strip()
        context["total_bookings"] = base_queryset.count()
        context["pending_count"] = base_queryset.filter(status=RoomBooking.BookingStatus.PENDING).count()
        context["approved_count"] = base_queryset.filter(status=RoomBooking.BookingStatus.APPROVED).count()
        context["rejected_count"] = base_queryset.filter(status=RoomBooking.BookingStatus.CANCELED).count()
        context["withdrawn_count"] = base_queryset.filter(status=RoomBooking.BookingStatus.WITHDRAWN).count()
        return context


def _get_admin_statistics():
    return {
        "total_landlords": User.objects.filter(profile__role=UserProfile.Role.LANDLORD).count(),
        "total_tenants": User.objects.filter(profile__role=UserProfile.Role.TENANT).count(),
        "total_rooms": Phong.objects.count(),
    }


def _shift_month(base_dt, month_delta):
    month_index = (base_dt.month - 1) + month_delta
    year = base_dt.year + month_index // 12
    month = month_index % 12 + 1
    return base_dt.replace(year=year, month=month, day=1, hour=0, minute=0, second=0, microsecond=0)


def _get_period_config(period):
    now = timezone.localtime()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow_start = today_start + timedelta(days=1)

    if period == "today":
        return {
            "key": "today",
            "label": "Hôm nay",
            "start": today_start,
            "end": tomorrow_start,
            "bucket_count": 6,
            "bucket_label": lambda index: f"{index * 4:02d}h",
            "bucket_index": lambda dt: min(dt.hour // 4, 5),
        }

    if period == "week":
        start = today_start - timedelta(days=6)
        return {
            "key": "week",
            "label": "7 ngày qua",
            "start": start,
            "end": tomorrow_start,
            "bucket_count": 7,
            "bucket_label": lambda index: (start + timedelta(days=index)).strftime("%d/%m"),
            "bucket_index": lambda dt: max(0, min((timezone.localtime(dt).date() - start.date()).days, 6)),
        }

    if period == "year":
        start = _shift_month(today_start, -11)
        end = _shift_month(today_start, 1)
        return {
            "key": "year",
            "label": "12 tháng qua",
            "start": start,
            "end": end,
            "bucket_count": 12,
            "bucket_label": lambda index: _shift_month(start, index).strftime("T%m"),
            "bucket_index": lambda dt: max(
                0,
                min(
                    (timezone.localtime(dt).year - start.year) * 12 + (timezone.localtime(dt).month - start.month),
                    11,
                ),
            ),
        }

    start = today_start - timedelta(days=29)
    return {
        "key": "month",
        "label": "30 ngày qua",
        "start": start,
        "end": tomorrow_start,
        "bucket_count": 6,
        "bucket_label": lambda index: f"{(start + timedelta(days=index * 5)).strftime('%d/%m')}",
        "bucket_index": lambda dt: max(0, min((timezone.localtime(dt).date() - start.date()).days // 5, 5)),
    }


def _build_series(dataset, bucket_count, bucket_index_getter):
    values = [0] * bucket_count
    for item in dataset:
        bucket_index = bucket_index_getter(item)
        if 0 <= bucket_index < bucket_count:
            values[bucket_index] += 1
    return values


def _build_chart_points(labels, primary_values, secondary_values=None):
    secondary_values = secondary_values or [0] * len(labels)
    max_value = max(primary_values + secondary_values + [1])
    points = []
    for index, label in enumerate(labels):
        primary = primary_values[index]
        secondary = secondary_values[index]
        points.append(
            {
                "label": label,
                "primary": primary,
                "secondary": secondary,
                "primary_height": max(10, int((primary / max_value) * 100)) if primary else 6,
                "secondary_height": max(10, int((secondary / max_value) * 100)) if secondary else 6,
            }
        )
    return points


class AdminContextMixin(AdminRequiredMixin):
    active_admin_menu = "dashboard"

    def get_admin_context(self):
        context = _get_admin_statistics()
        context["active_admin_menu"] = self.active_admin_menu
        return context

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self.get_admin_context())
        return context


class AdminDashboardView(AdminContextMixin, TemplateView):
    template_name = "phongtro/admin_dashboard.html"
    active_admin_menu = "dashboard"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        selected_period = self.request.GET.get("period", "month").strip().lower()
        if selected_period not in {"today", "week", "month", "year"}:
            selected_period = "month"

        period_config = _get_period_config(selected_period)
        start = period_config["start"]
        end = period_config["end"]
        bucket_count = period_config["bucket_count"]
        bucket_label = period_config["bucket_label"]
        bucket_index = period_config["bucket_index"]

        landlord_users = list(
            User.objects.filter(profile__role=UserProfile.Role.LANDLORD, date_joined__gte=start, date_joined__lt=end)
            .select_related("profile")
            .annotate(total_rooms=Count("rooms"))
            .order_by("date_joined")
        )
        tenant_users = list(
            User.objects.filter(profile__role=UserProfile.Role.TENANT, date_joined__gte=start, date_joined__lt=end)
            .select_related("profile")
            .order_by("date_joined")
        )
        rooms = list(Phong.objects.filter(created_at__gte=start, created_at__lt=end).select_related("owner").order_by("created_at"))

        labels = [bucket_label(index) for index in range(bucket_count)]
        landlord_values = _build_series((user.date_joined for user in landlord_users), bucket_count, bucket_index)
        tenant_values = _build_series((user.date_joined for user in tenant_users), bucket_count, bucket_index)
        room_values = _build_series((room.created_at for room in rooms), bucket_count, bucket_index)

        all_rooms = Phong.objects.all()
        occupancy_total_rooms = all_rooms.count()
        available_room_count = all_rooms.filter(status=Phong.RoomStatus.AVAILABLE).count()
        rented_room_count = all_rooms.filter(status=Phong.RoomStatus.RENTED).count()
        maintenance_room_count = all_rooms.filter(status=Phong.RoomStatus.MAINTENANCE).count()

        if occupancy_total_rooms:
            rented_room_percent = round((rented_room_count / occupancy_total_rooms) * 100, 1)
            available_room_percent = round((available_room_count / occupancy_total_rooms) * 100, 1)
            maintenance_room_percent = round((maintenance_room_count / occupancy_total_rooms) * 100, 1)

            rented_degrees = round((rented_room_count / occupancy_total_rooms) * 360, 1)
            available_degrees = round((available_room_count / occupancy_total_rooms) * 360, 1)
            maintenance_degrees = 360 - rented_degrees - available_degrees
            occupancy_chart_style = (
                "conic-gradient("
                f"#4f46e5 0deg {rented_degrees}deg, "
                f"#22c55e {rented_degrees}deg {rented_degrees + available_degrees}deg, "
                f"#cbd5e1 {rented_degrees + available_degrees}deg 360deg)"
            )
        else:
            rented_room_percent = 0
            available_room_percent = 0
            maintenance_room_percent = 0
            maintenance_degrees = 360
            occupancy_chart_style = "conic-gradient(#e2e8f0 0deg 360deg)"

        context.update(
            {
                "selected_period": selected_period,
                "selected_period_label": period_config["label"],
                "total_landlords": len(landlord_users),
                "total_tenants": len(tenant_users),
                "total_rooms": len(rooms),
                "user_growth_points": _build_chart_points(labels, landlord_values, tenant_values),
                "room_activity_points": _build_chart_points(labels, room_values),
                "occupancy_total_rooms": occupancy_total_rooms,
                "available_room_count": available_room_count,
                "rented_room_count": rented_room_count,
                "maintenance_room_count": maintenance_room_count,
                "available_room_percent": available_room_percent,
                "rented_room_percent": rented_room_percent,
                "maintenance_room_percent": maintenance_room_percent,
                "maintenance_degrees": maintenance_degrees,
                "occupancy_chart_style": occupancy_chart_style,
                "recent_landlords": list(reversed(landlord_users[-5:])),
            }
        )
        return context


class AdminLandlordListView(AdminContextMixin, ListView):
    model = User
    template_name = "phongtro/admin_landlord_list.html"
    context_object_name = "landlords"
    paginate_by = 20
    active_admin_menu = "landlords"

    def get_queryset(self):
        return (
            User.objects.filter(profile__role=UserProfile.Role.LANDLORD)
            .select_related("profile")
            .annotate(total_rooms=Count("rooms"))
            .order_by("-date_joined", "-id")
        )


class AdminTenantListView(AdminContextMixin, ListView):
    model = User
    template_name = "phongtro/admin_tenant_list.html"
    context_object_name = "tenants"
    paginate_by = 20
    active_admin_menu = "tenants"

    def get_queryset(self):
        return (
            User.objects.filter(profile__role=UserProfile.Role.TENANT)
            .select_related("profile")
            .order_by("-date_joined", "-id")
        )


class AdminRoomListView(AdminContextMixin, ListView):
    model = Phong
    template_name = "phongtro/admin_room_list.html"
    context_object_name = "rooms"
    paginate_by = 20
    active_admin_menu = "rooms"

    def get_queryset(self):
        return Phong.objects.select_related("owner").order_by("-id")


@login_required
@require_http_methods(["GET"])
def approve_booking(request, booking_id):
    if not _can_manage_posts(request.user):
        messages.error(request, "Bạn không có quyền duyệt yêu cầu này.")
        return redirect("phongtro:home_page")

    booking = get_object_or_404(RoomBooking, id=booking_id, room__owner=request.user)
    if booking.status == RoomBooking.BookingStatus.PENDING:
        booking.status = RoomBooking.BookingStatus.APPROVED
        booking.save(update_fields=["status"])
        messages.success(request, "Đã duyệt đơn thành công.")
    else:
        messages.info(request, "Yêu cầu này đã được xử lý trước đó.")
    return redirect("phongtro:dashboard_bookings")


@login_required
@require_http_methods(["GET"])
def reject_booking(request, booking_id):
    if not _can_manage_posts(request.user):
        messages.error(request, "Bạn không có quyền từ chối yêu cầu này.")
        return redirect("phongtro:home_page")

    booking = get_object_or_404(RoomBooking, id=booking_id, room__owner=request.user)
    if booking.status == RoomBooking.BookingStatus.PENDING:
        booking.status = RoomBooking.BookingStatus.CANCELED
        booking.save(update_fields=["status"])
        messages.success(request, "Đã từ chối đơn thành công.")
    else:
        messages.info(request, "Yêu cầu này đã được xử lý trước đó.")
    return redirect("phongtro:dashboard_bookings")


@login_required
@require_http_methods(["POST"])
def cancel_my_booking(request, booking_id):
    if _get_user_role(request.user) != UserProfile.Role.TENANT:
        messages.error(request, "Chỉ tài khoản người thuê mới có thể hủy yêu cầu thuê phòng.")
        return redirect("phongtro:home_page")

    booking = get_object_or_404(
        RoomBooking.objects.select_related("room"),
        id=booking_id,
        user=request.user,
    )

    if booking.status != RoomBooking.BookingStatus.PENDING:
        messages.info(request, "Chỉ có thể hủy yêu cầu đang chờ duyệt.")
        return redirect("phongtro:my_bookings")

    booking.status = RoomBooking.BookingStatus.WITHDRAWN
    booking.save(update_fields=["status"])
    messages.success(request, "Đã hủy yêu cầu thuê phòng.")
    return redirect("phongtro:my_bookings")


class RoomCreateView(StaffOnlyMixin, CreateView):
    model = Phong
    form_class = RoomForm
    template_name = "phongtro/room_form.html"
    success_url = reverse_lazy("phongtro:dashboard")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_get_google_maps_context())
        return context

    def form_valid(self, form):
        # Gan owner de khong the gia mao chu so huu bang request payload
        form.instance.owner = self.request.user
        response = super().form_valid(form)
        _save_room_gallery(self.object, self.request.FILES.getlist("gallery_images"))
        return response


class RoomUpdateView(OwnerObjectMixin, UpdateView):
    model = Phong
    form_class = RoomForm
    template_name = "phongtro/room_form.html"
    success_url = reverse_lazy("phongtro:dashboard")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_get_google_maps_context())
        return context

    def form_valid(self, form):
        original_room = self.get_object()
        submitted_lat = form.cleaned_data.get("latitude")
        submitted_lng = form.cleaned_data.get("longitude")
        submitted_address = (form.cleaned_data.get("address") or "").strip()
        original_address = (original_room.address or "").strip()

        # Khi người dùng đổi địa chỉ nhưng form vẫn giữ tọa độ cũ trong hidden input,
        # trang chi tiết sẽ tiếp tục ưu tiên tọa độ cũ và map nhìn như không cập nhật.
        # Nếu địa chỉ đã đổi và tọa độ gửi lên vẫn đúng bằng tọa độ cũ, xóa tọa độ đó.
        if (
            submitted_address
            and submitted_address != original_address
            and submitted_lat == original_room.latitude
            and submitted_lng == original_room.longitude
        ):
            form.instance.latitude = None
            form.instance.longitude = None

        response = super().form_valid(form)
        _save_room_gallery(self.object, self.request.FILES.getlist("gallery_images"))
        return response


class RoomDeleteView(OwnerObjectMixin, DeleteView):
    model = Phong
    template_name = "phongtro/room_confirm_delete.html"
    success_url = reverse_lazy("phongtro:dashboard")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["has_active_tenant"] = _room_has_active_tenant(self.object)
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        if _room_has_active_tenant(self.object):
            messages.error(
                request,
                "Không thể xóa phòng đang có người thuê. Hãy kết thúc thuê hoặc cập nhật lại trạng thái trước.",
            )
            return redirect("phongtro:dashboard")
        return super().post(request, *args, **kwargs)
