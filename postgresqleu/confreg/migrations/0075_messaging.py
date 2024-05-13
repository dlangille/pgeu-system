# Generated by Django 2.2.11 on 2020-04-20 12:17

from django.contrib.postgres.indexes import GinIndex
import django.core.serializers.json
from django.db import migrations, models
from django.conf import settings


def migrate_news_twitter(apps, schema_editor):
    if getattr(settings, 'TWITTER_NEWS_TOKEN', None):
        apps.get_model('confreg', 'MessagingProvider')(
            series=None,
            internalname='Twitter news',
            publicname='Twitter',
            classname='postgresqleu.util.messaging.twitter.Twitter',
            active=True,
            config={
                'token': settings.TWITTER_NEWS_TOKEN,
                'secret': settings.TWITTER_NEWS_TOKENSECRET,
            },
            route_incoming=None,
        ).save()


def unmigrate_news_twitter(apps, schema_editor):
    aps.get_model('confreg', 'MessagingProvider').objects.filter(classname='postgresqleu.util.messaging.twitter.Twitter', series__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('confreg', '0074_activate_timezones'),
        ('util', '0003_oauthapps'),
    ]

    operations = [
        migrations.CreateModel(
            name='MessagingProvider',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('series', models.ForeignKey('confreg.ConferenceSeries', null=True, blank=True, on_delete=models.CASCADE)),
                ('internalname', models.CharField(max_length=100, verbose_name='Internal name')),
                ('publicname', models.CharField(max_length=100, verbose_name='Public name')),
                ('classname', models.CharField(max_length=200, verbose_name='Implementation class')),
                ('active', models.BooleanField(null=False, blank=False, default=False)),
                ('config', models.JSONField(default=dict, encoder=django.core.serializers.json.DjangoJSONEncoder)),
                ('route_incoming', models.ForeignKey('confreg.Conference', null=True, blank=True, on_delete=models.SET_NULL, verbose_name='Route incoming messages to', related_name='incoming_messaging_route_for')),
                ('public_checkpoint', models.BigIntegerField(null=False, blank=False, default=0)),
                ('public_lastpoll', models.DateTimeField(null=False, blank=False, auto_now_add=True)),
                ('private_checkpoint', models.BigIntegerField(null=False, blank=False, default=0)),
                ('private_lastpoll', models.DateTimeField(null=False, blank=False, auto_now_add=True)),
            ],
            options={
                'ordering': ('internalname', ),
            }
        ),
        migrations.CreateModel(
            name='ConferenceMessaging',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('broadcast', models.BooleanField(default=False, verbose_name='Broadcasts')),
                ('privatebcast', models.BooleanField(default=False, verbose_name='Attendee only broadcasts')),
                ('notification', models.BooleanField(default=False, verbose_name='Private notifications')),
                ('orgnotification', models.BooleanField(default=False, verbose_name='Organizer notifications')),
                ('config', models.JSONField(default=dict)),
                ('conference', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='confreg.Conference')),
                ('provider', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='confreg.MessagingProvider')),
            ],
            options={
                'verbose_name': 'messaging configuration',
                'ordering': ('provider__publicname',),
            },
        ),
        migrations.AlterUniqueTogether(
            name='conferencemessaging',
            unique_together=set([('conference', 'provider', )]),
        ),
        # Create messaging providers for any conference series with existing twitter accounts.
        # Pick the latest conference in each series that actually has a token.
        migrations.RunSQL("""INSERT INTO confreg_messagingprovider
 (series_id, internalname, publicname, classname, config, active, route_incoming_id, private_lastpoll, private_checkpoint, public_lastpoll, public_checkpoint)
SELECT DISTINCT ON (s.name) s.id, 'Twitter ' || twitter_user, 'Twitter',
 'postgresqleu.util.messaging.twitter.Twitter',
 jsonb_build_object('token', c.twitter_token, 'secret', c.twitter_secret, 'screen_name', c.twitter_user),
 true,
 CASE WHEN c.twitterincoming_active THEN c.id ELSE NULL END,
 current_timestamp, 0, current_timestamp, 0
FROM confreg_conferenceseries s
INNER JOIN confreg_conference c ON c.series_id=s.id
WHERE twitter_token != ''
ORDER BY s.name, c.twittersync_active desc, c.startdate desc
"""),

        migrations.AddField(
            model_name='ConferenceTweetQueue',
            name='remainingtosend',
            field=models.ManyToManyField('confreg.MessagingProvider', blank=True),
        ),
        migrations.AddField(
            model_name='ConferenceTweetqueue',
            name='postids',
            field=models.JSONField(default=dict),
        ),
        migrations.RunSQL("""UPDATE confreg_conferencetweetqueue cq SET postids=jsonb_build_object(tweetid, (SELECT mp.id FROM confreg_messagingprovider mp INNER JOIN confreg_conference c ON c.series_id=mp.series_id WHERE c.id=cq.conference_id AND mp.classname='postgresqleu.util.messaging.twitter.Twitter')) WHERE tweetid!=0"""
        ),
        migrations.RemoveField(
            model_name='ConferenceTweetQueue',
            name='tweetid',
        ),
        migrations.AlterField(
            model_name='ConferenceTweetQueue',
            name='conference',
            field=models.ForeignKey('confreg.Conference', null=True, on_delete=models.CASCADE),
        ),
        migrations.AlterField(
            model_name='ConferenceTweetQueue',
            name='contents',
            field=models.CharField(max_length=1000, null=False, blank=False),
        ),
        migrations.AlterUniqueTogether(
            name='conferencetweetqueue',
            unique_together=set(),
        ),
        migrations.AlterField(
            model_name='ConferenceIncomingTweet',
            name='statusid',
            field=models.BigIntegerField(null=False, blank=False),
        ),
        migrations.AddField(
            model_name='ConferenceIncomingTweet',
            name='provider',
            field=models.ForeignKey('confreg.MessagingProvider', null=True, on_delete=models.SET_NULL),
        ),
        migrations.AlterUniqueTogether(
            name='conferenceincomingtweet',
            unique_together=set([('statusid', 'provider')]),
        ),
        migrations.AlterUniqueTogether(
            name='conferenceincomingtweetmedia',
            unique_together=set([('incomingtweet', 'sequence')]),
        ),
        migrations.AddIndex(
            model_name='conferencetweetqueue',
            index=GinIndex(name='tweetqueue_postids_idx', fields=['postids'], opclasses=['jsonb_path_ops']),
        ),
        migrations.AddField(
            model_name='conferenceregistration',
            name='messaging',
            field=models.ForeignKey('confreg.ConferenceMessaging', null=True, blank=True, on_delete=models.SET_NULL),
        ),
        migrations.AddField(
            model_name='conferenceregistration',
            name='messaging_copiedfrom',
            field=models.ForeignKey('confreg.Conference', null=True, blank=True, on_delete=models.SET_NULL, related_name='reg_messaging_copiedfrom'),
        ),
        migrations.AddField(
            model_name='conferenceregistration',
            name='messaging_config',
            field=models.JSONField(default=dict),
        ),
        migrations.CreateModel(
            name='NotificationQueue',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('time', models.DateTimeField()),
                ('expires', models.DateTimeField()),
                ('channel', models.CharField(blank=True, max_length=50, null=True)),
                ('msg', models.TextField()),
                ('messaging', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='confreg.ConferenceMessaging')),
                ('reg', models.ForeignKey(null=True, blank=True, on_delete=django.db.models.deletion.CASCADE, to='confreg.ConferenceRegistration')),
            ],
        ),
        migrations.CreateModel(
            name='IncomingDirectMessage',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('provider', models.ForeignKey('confreg.MessagingProvider', null=False, blank=False, on_delete=models.CASCADE)),
                ('time', models.DateTimeField(null=False, blank=False)),
                ('postid', models.BigIntegerField(null=False, blank=False)),
                ('internallyprocessed', models.BooleanField(null=False, blank=False, default=False)),
                ('sender', models.JSONField(default=dict)),
                ('txt', models.TextField(null=False, blank=True)),
            ],
        ),
        migrations.AlterUniqueTogether(
            name='incomingdirectmessage',
            unique_together=set([('postid', 'provider', )]),
        ),
        migrations.RunPython(migrate_news_twitter, unmigrate_news_twitter),
        migrations.RemoveField(
            model_name='Conference',
            name='twittersync_active',
        ),
        migrations.RemoveField(
            model_name='Conference',
            name='twitterincoming_active',
        ),
        migrations.RemoveField(
            model_name='Conference',
            name='twitterreminders_active',
        ),
        migrations.RemoveField(
            model_name='Conference',
            name='twitter_user',
        ),
        migrations.RemoveField(
            model_name='Conference',
            name='twitter_token',
        ),
        migrations.RemoveField(
            model_name='Conference',
            name='twitter_secret',
        ),
    ]
