from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def seed_user_profiles(apps, schema_editor):
    User = apps.get_model("auth", "User")
    UserProfile = apps.get_model("phongtro", "UserProfile")

    for user in User.objects.all():
        role = "tenant"
        if user.is_superuser:
            role = "admin"
        elif user.is_staff:
            role = "landlord"
        UserProfile.objects.get_or_create(user=user, defaults={"role": role})


class Migration(migrations.Migration):

    dependencies = [
        ("phongtro", "0011_phong_latitude_phong_longitude"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="UserProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "role",
                    models.CharField(
                        choices=[
                            ("tenant", "Khách thuê"),
                            ("landlord", "Chủ trọ"),
                            ("admin", "Quản trị viên hệ thống"),
                        ],
                        default="tenant",
                        max_length=20,
                    ),
                ),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="profile",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.RunPython(seed_user_profiles, migrations.RunPython.noop),
    ]
