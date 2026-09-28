from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("phongtro", "0013_phong_created_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="phong",
            name="amenities",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="phong",
            name="furnishings",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.CreateModel(
            name="RoomImage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("image", models.ImageField(upload_to="rooms/gallery/")),
                ("caption", models.CharField(blank=True, default="", max_length=255)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("room", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="gallery_images", to="phongtro.phong")),
            ],
            options={"ordering": ["sort_order", "id"]},
        ),
    ]
