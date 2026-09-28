from django import forms
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.models import User

from .models import Phong, UserProfile


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    widget = MultipleFileInput

    def clean(self, data, initial=None):
        single_file_clean = super().clean
        if isinstance(data, (list, tuple)):
            return [single_file_clean(item, initial) for item in data]
        if not data:
            return []
        return [single_file_clean(data, initial)]


ROLE_CHOICES_ALL = [
    (UserProfile.Role.TENANT, "Khách thuê"),
    (UserProfile.Role.LANDLORD, "Chủ trọ"),
    (UserProfile.Role.ADMIN, "Quản trị viên hệ thống"),
]

ROLE_CHOICES_REGISTER = [
    (UserProfile.Role.TENANT, "Khách thuê"),
    (UserProfile.Role.LANDLORD, "Chủ trọ"),
]


class LoginForm(forms.Form):
    identifier = forms.CharField(max_length=150)
    password = forms.CharField(widget=forms.PasswordInput)
    role = forms.ChoiceField(choices=ROLE_CHOICES_ALL)


class RegisterForm(forms.Form):
    full_name = forms.CharField(max_length=150)
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput)
    confirm_password = forms.CharField(widget=forms.PasswordInput)
    role = forms.ChoiceField(choices=ROLE_CHOICES_REGISTER)


class AccountProfileForm(forms.ModelForm):
    email = forms.EmailField(label="Email", required=False)

    class Meta:
        model = UserProfile
        fields = ["avatar", "phone", "contact_address"]
        labels = {
            "avatar": "Ảnh đại diện",
            "phone": "Số điện thoại liên hệ",
            "contact_address": "Địa chỉ liên hệ",
        }

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

        base_class = "mt-1 w-full rounded-xl border border-slate-300 px-4 py-3 text-sm outline-none ring-indigo-500 focus:ring"
        self.fields["email"].widget.attrs.update(
            {
                "class": base_class,
                "placeholder": "email@example.com",
            }
        )
        self.fields["avatar"].widget.attrs.update(
            {
                "class": base_class,
                "accept": "image/*",
            }
        )
        self.fields["phone"].widget.attrs.update(
            {
                "class": base_class,
                "placeholder": "Ví dụ: 0912345678",
                "inputmode": "tel",
            }
        )
        self.fields["contact_address"].widget.attrs.update(
            {
                "class": base_class,
                "placeholder": "Nhập địa chỉ liên hệ",
            }
        )

        if self.user:
            self.fields["email"].initial = self.user.email
        self._original_phone = (self.instance.phone or "").strip() if self.instance else ""

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if not email:
            return ""

        queryset = User.objects.filter(email__iexact=email)
        if self.user:
            queryset = queryset.exclude(pk=self.user.pk)
        if queryset.exists():
            raise forms.ValidationError("Email đã được sử dụng.")
        return email

    def clean_phone(self):
        phone = (self.cleaned_data.get("phone") or "").strip()
        if not phone:
            return ""

        normalized = phone.replace(" ", "")
        if not all(char.isdigit() or char == "+" for char in normalized):
            raise forms.ValidationError("Số điện thoại chỉ được chứa số hoặc dấu +.")
        return normalized

    def save(self, commit=True):
        profile = super().save(commit=False)
        new_phone = (self.cleaned_data.get("phone") or "").strip()
        if new_phone != self._original_phone:
            profile.phone_verified = False

        if self.user is not None:
            self.user.email = self.cleaned_data.get("email", "")
            if commit:
                self.user.save(update_fields=["email"])

        if commit:
            profile.save()
        return profile


class AccountPasswordChangeForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        base_class = "mt-1 w-full rounded-xl border border-slate-300 px-4 py-3 text-sm outline-none ring-indigo-500 focus:ring"
        self.fields["old_password"].label = "Mật khẩu hiện tại"
        self.fields["new_password1"].label = "Mật khẩu mới"
        self.fields["new_password2"].label = "Nhập lại mật khẩu mới"
        for field in self.fields.values():
            field.widget.attrs.update({"class": base_class})


class RoomForm(forms.ModelForm):
    ROOM_TYPE_CHOICES = [
        ("", "Chọn loại phòng"),
        ("Phòng thường", "Phòng thường"),
        ("Phòng điều hòa", "Phòng điều hòa"),
        ("Phòng nóng lạnh", "Phòng nóng lạnh"),
        ("Phòng đầy đủ", "Phòng đầy đủ"),
    ]
    KHU_VUC_CHOICES = [
        ("", "Chọn khu vực"),
        ("Gần Đại học Sư phạm Thái Nguyên", "Gần Đại học Sư phạm Thái Nguyên"),
        ("Gần Đại học Kỹ thuật Công nghiệp", "Gần Đại học Kỹ thuật Công nghiệp"),
        ("Gần Đại học Công nghệ Thông tin và Truyền thông", "Gần Đại học Công nghệ Thông tin và Truyền thông"),
        ("Gần Đại học Nông Lâm Thái Nguyên", "Gần Đại học Nông Lâm Thái Nguyên"),
        ("Gần Đại học Khoa học Thái Nguyên", "Gần Đại học Khoa học Thái Nguyên"),
        ("Gần Đại học Y - Dược Thái Nguyên", "Gần Đại học Y - Dược Thái Nguyên"),
        ("Khu Đại học Thái Nguyên (Tân Thịnh)", "Khu Đại học Thái Nguyên (Tân Thịnh)"),
    ]
    STATUS_CHOICES = [
        ("available", "Còn trống"),
        ("rented", "Đang thuê"),
        ("maintenance", "Đang sửa chữa"),
    ]

    khu_vuc = forms.ChoiceField(choices=KHU_VUC_CHOICES, required=False)
    gallery_images = MultipleFileField(
        required=False,
        widget=MultipleFileInput(attrs={"multiple": True}),
    )

    class Meta:
        model = Phong
        fields = [
            "title",
            "price",
            "area",
            "address",
            "latitude",
            "longitude",
            "room_type",
            "status",
            "description",
            "owner_phone",
            "image",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        base_class = "mt-1 w-full rounded-xl border border-slate-300 px-4 py-3 text-sm outline-none ring-indigo-500 focus:ring"
        self.fields["room_type"].widget = forms.Select(choices=self.ROOM_TYPE_CHOICES)
        self.fields["status"].widget = forms.Select(choices=self.STATUS_CHOICES)
        self.fields["price"].widget = forms.TextInput()
        self.fields["latitude"].widget = forms.HiddenInput(attrs={"id": "id_latitude"})
        self.fields["longitude"].widget = forms.HiddenInput(attrs={"id": "id_longitude"})
        for name, field in self.fields.items():
            if name == "description":
                field.widget.attrs.update({"class": base_class, "rows": 5})
            elif name == "price":
                field.widget.attrs.update(
                    {
                        "class": base_class,
                        "inputmode": "numeric",
                        "placeholder": "Ví dụ: 1,000,000",
                        "data-format-price": "true",
                    }
                )
            else:
                field.widget.attrs.update({"class": base_class})

        self.fields["image"].widget.attrs.update({"accept": "image/*"})
        self.fields["gallery_images"].widget.attrs.update(
            {
                "class": base_class,
                "accept": "image/*",
            }
        )

    def clean(self):
        cleaned_data = super().clean()
        address = cleaned_data.get("address", "").strip()
        khu_vuc = cleaned_data.get("khu_vuc", "").strip()
        if khu_vuc and khu_vuc.lower() not in address.lower():
            cleaned_data["address"] = f"{address}, {khu_vuc}" if address else khu_vuc
        return cleaned_data
