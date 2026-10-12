"""Small, escaped transactional templates based on the approved email reference."""

from dataclasses import dataclass
from html import escape
from urllib.parse import urlsplit


@dataclass(frozen=True)
class EmailContent:
    subject: str
    html: str
    text: str


def render_email(
    subject: str,
    paragraphs: list[str],
    *,
    action_url: str,
    action_label: str,
    locale: str = "en-US",
    note: str = "",
) -> EmailContent:
    url = urlsplit(action_url)
    if url.scheme not in {"https", "http"} or not url.netloc or url.username or url.password:
        raise ValueError("Invalid email destination")
    if url.scheme == "http" and url.hostname not in {"localhost", "127.0.0.1"}:
        raise ValueError("Email destinations require HTTPS")
    spanish = locale == "es-MX"
    fallback = (
        "¿No funciona el botón? Abre este enlace:"
        if spanish
        else "Button not working? Open this link:"
    )
    footer = (
        "No respondas a este correo; no se supervisan las respuestas. Abre el portal para comunicarte con tu equipo."
        if spanish
        else "Do not reply to this email; replies are not monitored. Open the portal to contact your team."
    )
    prototype = (
        "MediAgent es un prototipo de proyecto de maestría con datos ficticios."
        if spanish
        else "MediAgent is a master's-project prototype using fictional demonstration data."
    )
    body = "".join(
        f'<p class="body" style="margin:0 0 16px;font-size:16px;line-height:24px;color:#33434E">{escape(p)}</p>'
        for p in paragraphs
    )
    safe_url = escape(action_url, quote=True)
    note_html = (
        f'<p class="note" style="padding:14px 16px;border-radius:12px;background:#E3F0EC;color:#0F5C50;font-size:14px;line-height:21px">{escape(note)}</p>'
        if note
        else ""
    )
    html = f'''<!doctype html><html lang="{"es-MX" if spanish else "en-US"}"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark"><meta name="supported-color-schemes" content="light dark">
<meta name="x-apple-disable-message-reformatting"><title>{escape(subject)}</title>
<style>@media(max-width:620px){{.px{{padding:24px 22px!important}}.h1{{font-size:26px!important;line-height:32px!important}}}}
@media(prefers-color-scheme:dark){{.bg{{background:#14191D!important}}.card{{background:#1D2428!important}}.ink{{color:#EEF2F1!important}}.body{{color:#C9D1D3!important}}.note{{background:#1F3C35!important;color:#D8EEE5!important}}}}</style></head>
<body class="bg" style="margin:0;background:#F3EEE6;font-family:Arial,Helvetica,sans-serif">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" class="bg" bgcolor="#F3EEE6"><tr><td align="center" style="padding:32px 12px">
<!--[if mso]><table role="presentation" width="600"><tr><td><![endif]-->
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px">
<tr><td class="ink" style="padding:0 8px 20px;color:#10202B;font-size:17px;font-weight:bold">MediAgent</td></tr>
<tr><td class="card px" bgcolor="#FFFDF9" style="padding:36px 40px 28px;background:#FFFDF9;border:1px solid #E8E1D6;border-radius:20px">
<h1 class="h1 ink" style="margin:0 0 18px;color:#10202B;font-size:30px;line-height:36px">{escape(subject)}</h1>{body}{note_html}
<table role="presentation" cellpadding="0" cellspacing="0" style="margin:24px 0"><tr><td bgcolor="#147465" style="border-radius:12px;background:#147465">
<a href="{safe_url}" style="display:block;padding:15px 28px;font-size:16px;line-height:20px;font-weight:bold;color:#fff;text-decoration:none;border-radius:12px">{escape(action_label)}</a></td></tr></table>
<p class="body" style="font-size:13px;line-height:20px;color:#5B6872">{fallback}<br><a href="{safe_url}" style="color:#147465;word-break:break-all">{safe_url}</a></p></td></tr>
<tr><td class="body" style="padding:22px 16px;color:#5B6872;font-size:12px;line-height:18px">{footer}<br><br>{prototype}</td></tr></table>
<!--[if mso]></td></tr></table><![endif]--></td></tr></table></body></html>'''
    text = "\n\n".join(
        [subject, *paragraphs, note, f"{action_label}: {action_url}", footer, prototype]
    )
    return EmailContent(subject=" ".join(subject.split()), html=html, text=text)


def verification_email(code: str, preferences_url: str, locale: str) -> EmailContent:
    spanish = locale == "es-MX"
    return render_email(
        "Verifica tu correo" if spanish else "Verify your email",
        [
            (
                f"Tu código de verificación es: {code}. Caduca en 10 minutos."
                if spanish
                else f"Your verification code is: {code}. It expires in 10 minutes."
            ),
            (
                "Ingresa el código en Preferencias de correo. Verificar no activa los avisos opcionales."
                if spanish
                else "Enter the code in Email preferences. Verification does not enable optional notices."
            ),
        ],
        action_url=preferences_url,
        action_label="Abrir preferencias" if spanish else "Open preferences",
        locale=locale,
    )
