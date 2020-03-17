# -*- coding: utf-8 -*-
# Generated by Django 1.11.27 on 2020-03-14 19:08
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('confreg', '0069_bulkpayment_datetime'),
    ]

    operations = [
        migrations.AddField(
            model_name='conferenceregistration',
            name='canceledat',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Canceled at'),
        ),
        migrations.RunSQL("ALTER TABLE confreg_conferenceregistration ADD CONSTRAINT ck_no_cancel_unconfirmed CHECK (canceledat IS NULL OR payconfirmedat IS NOT NULL)"),
    ]
