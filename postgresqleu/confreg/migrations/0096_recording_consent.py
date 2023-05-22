# Generated by Django 3.2.14 on 2023-05-22 14:28

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('confreg', '0095_tweet_conf_time_idx'),
    ]

    operations = [
        migrations.AddField(
            model_name='conference',
            name='callforpapersrecording',
            field=models.BooleanField(default=False, verbose_name='Ask for recording consent'),
        ),
        migrations.AddField(
            model_name='conferencesession',
            name='recordingconsent',
            field=models.BooleanField(default=False, verbose_name='Consent to recording'),
        ),
    ]
