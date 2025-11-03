# auth_otp/otp_service.py
import secrets
from datetime import timedelta
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.contrib.auth.hashers import make_password, check_password

# Redis opcional (si REDIS_URL no está, hacemos fallback a DB)
try:
    import redis
    _r = redis.from_url(settings.REDIS_URL, decode_responses=True) if settings.REDIS_URL else None
except Exception:
    _r = None

OTP_TTL = int(getattr(settings, "OTP_EXP_MINUTES", 10)) * 60
OTP_LEN = int(getattr(settings, "OTP_LEN", 6))

def _otp_key(email: str) -> str:
    return f"otp:{email.lower().strip()}"

def _attempts_key(email: str) -> str:
    return f"otp:attempts:{email.lower().strip()}"

def gen_code(n: int = OTP_LEN) -> str:
    digits = "0123456789"
    return "".join(secrets.choice(digits) for _ in range(n))

def create_and_send(email: str) -> None:
    """
    Genera código, lo guarda (Redis con TTL o DB) y envía email HTML+texto.
    """
    email = email.lower().strip()
    code = gen_code()

    if _r:
        _r.setex(_otp_key(email), OTP_TTL, make_password(code))
    else:
        # Fallback a DB si no hay Redis
        from django.utils import timezone
        from .models import OtpCode
        exp = timezone.now() + timedelta(minutes=getattr(settings, "OTP_EXP_MINUTES", 10))
        OtpCode.objects.create(email=email, code=code, expires_at=exp)

    _send_email(email, code)

def verify(email: str, code: str) -> bool:
    """
    Verifica código con throttle (6 intentos/ventana). Elimina token si es correcto.
    """
    email = email.lower().strip()
    code = code.strip()

    # Throttle simple: 6 intentos por TTL de OTP
    if _r:
        c = _r.incr(_attempts_key(email))
        if c == 1:
            _r.expire(_attempts_key(email), OTP_TTL)
        if c > 6:
            return False

    if _r:
        hashed = _r.get(_otp_key(email))
        if not hashed:
            return False
        ok = check_password(code, hashed)
        if ok:
            _r.delete(_otp_key(email))
        return ok
    else:
        from django.utils import timezone
        from .models import OtpCode
        otp = OtpCode.objects.filter(email=email, used=False).order_by("-created_at").first()
        if not otp or timezone.now() > otp.expires_at:
            return False
        if code != otp.code:
            otp.attempts += 1
            otp.save(update_fields=["attempts"])
            return False
        otp.used = True
        otp.save(update_fields=["used"])
        return True

def _send_email(to_email: str, code: str) -> None:
    subject = "Tu código de acceso (expira en 10 minutos)"
    text = f"Tu código es {code}. Expira en 10 minutos. Si no fuiste tú, ignora este correo."
    html = f"""<p>Hola,</p>
    <p>Tu código es <strong style="font-size:18px;letter-spacing:2px">{code}</strong>.</p>
    <p>Expira en <strong>10 minutos</strong>.</p>
    <p>Si no fuiste tú, puedes ignorar este mensaje.</p>"""

    msg = EmailMultiAlternatives(subject, text, settings.DEFAULT_FROM_EMAIL, [to_email])
    msg.attach_alternative(html, "text/html")
    msg.send(fail_silently=False)
