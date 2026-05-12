from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('analysis', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='detection',
            name='crop',
            field=models.ImageField(
                blank=True,
                help_text=(
                    'Cropped bbox image, written after inference for review '
                    'and training.'
                ),
                null=True,
                upload_to='runs/crops/',
            ),
        ),
    ]
