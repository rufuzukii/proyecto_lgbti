from __future__ import annotations

from urllib.parse import quote, urlencode

CONTACT_EMAIL = "rainbowlensdatahub@gmail.com"


def contact_mailto(language: str) -> str:
    if language == "en":
        subject = "Contact with RainbowLens DataHub"
        body = """Hello,

I am contacting RainbowLens DataHub regarding...

Kind regards."""
    else:
        subject = "Contacto con RainbowLens DataHub"
        body = """Hola,

Me pongo en contacto con RainbowLens DataHub para solicitar información sobre...

Un saludo."""
    query = urlencode({"subject": subject, "body": body}, quote_via=quote)
    return f"mailto:{CONTACT_EMAIL}?{query}"
