from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("phongtro", "0012_userprofile"),
    ]

    operations = [
        migrations.AddField(
            model_name="phong",
            name="created_at",
            field=models.DateTimeField(db_index=True, default=django.utils.timezone.now),
        ),
    ]
