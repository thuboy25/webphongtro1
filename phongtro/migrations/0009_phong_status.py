from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("phongtro", "0008_roombooking_tenant_name_roombooking_father_phone_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="phong",
            name="status",
            field=models.CharField(
                choices=[("available", "Còn trống"), ("rented", "Đang thuê"), ("maintenance", "Đang sửa chữa")],
                default="available",
                max_length=20,
            ),
        ),
    ]
