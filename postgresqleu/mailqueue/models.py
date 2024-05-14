from django.db import models
from django.utils import timezone


class QueuedMail(models.Model):
    sender = models.EmailField(max_length=100, null=False, blank=False)
    receiver = models.EmailField(max_length=100, null=False, blank=False)
    # We store the raw MIME message, so if there are any attachments or
    # anything, we just push them right in there!
    fullmsg = models.TextField(null=False, blank=False)
    sendtime = models.DateTimeField(null=False, blank=False, default=timezone.now)
    regtime = models.DateTimeField(null=False, blank=False, auto_now_add=True)
    subject = models.CharField(max_length=500, null=False, blank=False)

    def __str__(self):
        return "%s: %s -> %s" % (self.pk, self.sender, self.receiver)

    class Meta:
        ordering = ('sendtime', )
