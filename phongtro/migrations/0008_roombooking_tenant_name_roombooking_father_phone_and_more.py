from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("phongtro", "0007_roombooking"),
    ]

    operations = [
        migrations.AddField(
            model_name="roombooking",
            name="father_phone",
            field=models.CharField(default="", max_length=20),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="roombooking",
            name="mother_phone",
            field=models.CharField(default="", max_length=20),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="roombooking",
            name="tenant_name",
            field=models.CharField(default="", max_length=150),
            preserve_default=False,
        ),
    ]
