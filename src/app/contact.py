from __future__ import annotations

from urllib.parse import urlencode

CONTACT_EMAIL = "rainbowlensdatahub@gmail.com"


def contact_mailto(language: str) -> str:
    if language == "en":
        subject = "RainbowLens DataHub enquiry"
        body = """Hello,

I am contacting RainbowLens DataHub.

Name:
Reason for contacting:
Message:

Thank you."""
    else:
        subject = "Consulta sobre RainbowLens DataHub"
        body = """Hola,

Me pongo en contacto con RainbowLens DataHub.

Nombre:
Motivo de contacto:
Mensaje:

Gracias."""
    return f"mailto:{CONTACT_EMAIL}?{urlencode({'subject': subject, 'body': body})}"
