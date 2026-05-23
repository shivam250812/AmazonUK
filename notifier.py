import os
import smtplib
from email.message import EmailMessage
from dotenv import load_dotenv

load_dotenv()

SMTP_EMAIL = os.getenv("SMTP_EMAIL") or os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_TO_EMAIL = os.getenv("SMTP_TO_EMAIL") or os.getenv("RECEIVER_EMAIL") or SMTP_EMAIL
SMTP_HOST = os.getenv("SMTP_HOST") or os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))

def is_configured():
    return bool(SMTP_EMAIL and SMTP_PASSWORD)

def send_email(subject: str, body: str, attachment_path: str = None):
    """
    Sends an email using configured SMTP settings.
    If SMTP_EMAIL or SMTP_PASSWORD are not set, it prints to console instead.
    """
    if not is_configured():
        print(f"\n[EMAIL NOT CONFIGURED] Would have sent:")
        print(f"Subject: {subject}")
        print(f"Body: {body}")
        if attachment_path:
            print(f"Attachment: {attachment_path}")
        print("-" * 40)
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = SMTP_EMAIL
    msg["To"] = SMTP_TO_EMAIL
    msg.set_content(body)

    if attachment_path and os.path.exists(attachment_path):
        import mimetypes
        ctype, encoding = mimetypes.guess_type(attachment_path)
        if ctype is None or encoding is not None:
            ctype = "application/octet-stream"
        maintype, subtype = ctype.split("/", 1)

        with open(attachment_path, "rb") as f:
            msg.add_attachment(
                f.read(),
                maintype=maintype,
                subtype=subtype,
                filename=os.path.basename(attachment_path)
            )

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_EMAIL, SMTP_PASSWORD)
            server.send_message(msg)
            print(f"  [Email Sent] {subject}")
            return True
    except Exception as e:
        print(f"  [Email Failed] Failed to send email: {e}")
        return False
