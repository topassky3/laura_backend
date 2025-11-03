from django.db import models
from django.utils import timezone
from datetime import timedelta
from django.conf import settings

class OtpCode(models.Model):
    email = models.EmailField(db_index=True)
    code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)
    attempts = models.PositiveIntegerField(default=0)

    @staticmethod
    def new_for_email(email: str, code: str | None = None):
        if code is None:
            code = settings.OTP_DEV_FIXED
        exp = timezone.now() + timedelta(minutes=getattr(settings, "OTP_EXP_MINUTES", 10))
        return OtpCode.objects.create(email=email.lower().strip(), code=code, expires_at=exp)

    def is_expired(self) -> bool:
        return timezone.now() > self.expires_at

    def __str__(self):
        return f"{self.email} - {self.code} - {'used' if self.used else 'active'}"
