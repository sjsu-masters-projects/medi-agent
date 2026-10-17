"""Small, escaped transactional templates based on the approved email reference."""

from dataclasses import dataclass
from html import escape
from typing import Literal
from urllib.parse import urlsplit

Audience = Literal["patient", "clinician"]


@dataclass(frozen=True)
class EmailContent:
    subject: str
    html: str
    text: str


@dataclass(frozen=True)
class _Brand:
    """Role-specific palette from each portal's ``globals.css`` and brand assets."""

    product: str
    header: str
    canvas: str
    card: str
    border: str
    ink: str
    body: str
    muted: str
    action: str
    link: str
    note: str
    dark: str


_BRANDS: dict[Audience, _Brand] = {
    # Patient: warm sand canvas, emerald action (unchanged approved reference).
    "patient": _Brand(
        product="MediAgent",
        header='<tr><td class="ink" style="padding:0 8px 20px;color:#10202B;font-size:17px;font-weight:bold">MediAgent</td></tr>',
        canvas="#F3EEE6",
        card="#FFFDF9",
        border="#E8E1D6",
        ink="#10202B",
        body="#33434E",
        muted="#5B6872",
        action="#147465",
        link='class="accent" style="color:#147465;word-break:break-all"',
        note="background:#E3F0EC;color:#0F5C50",
        dark=(
            ".bg{background:#14191D!important}.card{background:#1D2428!important}"
            ".ink{color:#EEF2F1!important}.body{color:#C9D1D3!important}"
            ".accent{color:#D8EEE5!important}"
            ".note{background:#1F3C35!important;color:#D8EEE5!important}"
        ),
    ),
    # Clinician: navy M-check tile (mark-sidebar.svg), blue primary, "MediAgent Pro".
    # Muted text is slate-600 so footer copy keeps 4.5:1 on the light canvas.
    "clinician": _Brand(
        product="MediAgent Pro",
        header=(
            '<tr><td style="padding:0 8px 20px"><table role="presentation" cellpadding="0" cellspacing="0"><tr>'
            '<td bgcolor="#1E293B" style="padding:9px;border-radius:9px;background:#1E293B;color:#FFFFFF;font-weight:bold">'
            'M<span style="color:#60A5FA">&#10003;</span></td>'
            '<td class="ink" style="padding-left:10px;color:#0F172A;font-size:17px;font-weight:bold">'
            'MediAgent <span class="accent" style="color:#2563EB">Pro</span></td></tr></table></td></tr>'
        ),
        canvas="#F4F6FA",
        card="#FFFFFF",
        border="#E2E8F0",
        ink="#0F172A",
        body="#334155",
        muted="#475569",
        action="#2563EB",
        link='class="accent" style="color:#2563EB;word-break:break-all"',
        note="background:#EFF6FF;color:#1D4ED8",
        dark=(
            ".bg{background:#0A1222!important}.card{background:#111B2E!important}"
            ".ink{color:#E6ECF5!important}.body{color:#A9B6CA!important}"
            ".accent{color:#60A5FA!important}"
            ".note{background:#172554!important;color:#DBEAFE!important}"
        ),
    ),
}


def render_email(
    subject: str,
    paragraphs: list[str],
    *,
    action_url: str,
    action_label: str,
    audience: Audience,
    locale: str = "en-US",
    note: str = "",
    clinic: str = "",
    clinic_in_subject: bool = True,
) -> EmailContent:
    url = urlsplit(action_url)
    if url.scheme not in {"https", "http"} or not url.netloc or url.username or url.password:
        raise ValueError("Invalid email destination")
    if url.scheme == "http" and url.hostname not in {"localhost", "127.0.0.1"}:
        raise ValueError("Email destinations require HTTPS")
    brand = _BRANDS[audience]
    # Clinician email is English; only patients receive es-MX.
    spanish = audience == "patient" and locale == "es-MX"
    fallback = (
        "¿No funciona el botón? Abre este enlace:"
        if spanish
        else "Button not working? Open this link:"
    )
    footer = (
        "No se supervisan las respuestas. Abre el portal para comunicarte con tu equipo."
        if spanish
        else "Replies aren't monitored. Open the portal to contact your team."
    )
    prototype = (
        f"Prototipo de {brand.product} · datos ficticios."
        if spanish
        else f"{brand.product} prototype · fictional demo data."
    )
    body = "".join(
        f'<p class="body" style="margin:0 0 16px;font-size:16px;line-height:24px;color:{brand.body}">{escape(p)}</p>'
        for p in paragraphs
    )
    safe_url = escape(action_url, quote=True)
    # CLN-003 slice F: a person with several clinics must see which one this is from. The clinic
    # leads the subject ("<Clinic> · …") and sits on its own line under the brand; one clinic
    # means no clinic line, so existing mail is unchanged.
    clinic = " ".join(clinic.split())
    title = f"{clinic} · {subject}" if clinic and clinic_in_subject else subject
    clinic_row = (
        f'<tr><td class="body" style="padding:0 8px 14px;color:{brand.muted};font-size:14px;'
        f'line-height:20px;font-weight:bold">{escape(clinic)}</td></tr>'
        if clinic
        else ""
    )
    note_html = (
        f'<p class="note" style="padding:14px 16px;border-radius:12px;{brand.note};font-size:14px;line-height:21px">{escape(note)}</p>'
        if note
        else ""
    )
    html = f'''<!doctype html><html lang="{"es-MX" if spanish else "en-US"}"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark"><meta name="supported-color-schemes" content="light dark">
<meta name="x-apple-disable-message-reformatting"><title>{escape(title)}</title>
<style>@media(max-width:620px){{.px{{padding:24px 22px!important}}.h1{{font-size:26px!important;line-height:32px!important}}}}
@media(prefers-color-scheme:dark){{{brand.dark}}}</style></head>
<body class="bg" style="margin:0;background:{brand.canvas};font-family:Arial,Helvetica,sans-serif">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" class="bg" bgcolor="{brand.canvas}"><tr><td align="center" style="padding:32px 12px">
<!--[if mso]><table role="presentation" width="600"><tr><td><![endif]-->
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px">
{brand.header}
{clinic_row}<tr><td class="card px" bgcolor="{brand.card}" style="padding:36px 40px 28px;background:{brand.card};border:1px solid {brand.border};border-radius:20px">
<h1 class="h1 ink" style="margin:0 0 18px;color:{brand.ink};font-size:30px;line-height:36px">{escape(subject)}</h1>{body}{note_html}
<table role="presentation" cellpadding="0" cellspacing="0" style="margin:24px 0 0"><tr><td bgcolor="{brand.action}" style="border-radius:12px;background:{brand.action}">
<a href="{safe_url}" style="display:block;padding:15px 28px;font-size:16px;line-height:20px;font-weight:bold;color:#fff;text-decoration:none;border-radius:12px">{escape(action_label)}</a></td></tr></table></td></tr>
<tr><td class="body" style="padding:22px 16px;color:{brand.muted};font-size:12px;line-height:18px">{fallback}<br><a href="{safe_url}" {brand.link}>{safe_url}</a><br><br>{footer}<br><br>{prototype}</td></tr></table>
<!--[if mso]></td></tr></table><![endif]--></td></tr></table></body></html>'''
    text = "\n\n".join(
        [
            title,
            *paragraphs,
            *([note] if note else []),
            f"{action_label}: {action_url}",
            footer,
            prototype,
        ]
    )
    return EmailContent(subject=" ".join(title.split()), html=html, text=text)


def verification_email(
    code: str, preferences_url: str, locale: str, *, audience: Audience
) -> EmailContent:
    spanish = audience == "patient" and locale == "es-MX"
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
        audience=audience,
        locale="es-MX" if spanish else "en-US",
    )
