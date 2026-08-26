"""
Envío del código de acceso por Resend.

POR QUÉ NO SMTP

La versión anterior hablaba SMTP con Gmail desde el propio proceso. Eso
tiene tres problemas en un despliegue serverless: la conexión SMTP tarda
segundos y se paga en cada invocación, Gmail limita y bloquea el envío
programático desde IPs de datacenter, y cuando falla lanza una excepción
que devuelve 500 — y el login se quedaba atascado en el paso del correo
sin llegar nunca al campo del código.

Resend es una API HTTP: una petición, una respuesta, sin conexión que
mantener. Y el dominio propio evita que el correo caiga en spam.

POR QUÉ urllib Y NO httpx

Para no añadir una dependencia al bundle de Vercel por una sola llamada
POST. `urllib.request` es biblioteca estándar y hace exactamente esto.

DEGRADACIÓN

Sin `RESEND_API_KEY` el código se registra en el log y la función
devuelve normal, igual que hacía la versión con SMTP sin credenciales.
Eso mantiene el desarrollo local sin correo, y —lo importante— evita
que un fallo del proveedor bloquee el acceso al panel.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request

logger = logging.getLogger("agw-cloud-api.email")

_RESEND_URL = "https://api.resend.com/emails"
_TIMEOUT_S = 10

# Remitente por defecto. El dominio debe estar verificado en Resend o el
# envío se rechaza con 403.
_REMITENTE_DEF = "VitalCrop <vitalcrop@info.noxumsoluciones.com>"


def _plantilla_html(otp: str, minutos: int, destinatario: str) -> str:
    """
    Cuerpo del correo.

    Tres decisiones sobre el diseño:

      · Tablas y estilos en línea, no flexbox ni <style>. Outlook y
        varios clientes de escritorio ignoran las hojas de estilo
        embebidas y no implementan flex; una maquetación moderna se ve
        rota justo en los clientes donde más importa que se vea bien.

      · El código en un bloque grande y monoespaciado, separado por
        letra. Es lo único que la persona va a copiar, así que domina
        la pieza y se lee sin ambigüedad entre 0/O y 1/l.

      · Fondo claro. El correo se lee en contextos que ya tienen su
        propio tema y un fondo oscuro pelea con el del cliente.
    """
    digitos = " ".join(otp)

    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tu código de acceso · VitalCrop</title>
</head>
<body style="margin:0;padding:0;background-color:#eef2f0;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"
       style="background-color:#eef2f0;padding:32px 12px;">
  <tr><td align="center">

    <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
           style="max-width:560px;background-color:#ffffff;border-radius:10px;
                  overflow:hidden;box-shadow:0 1px 3px rgba(16,32,26,.08),
                  0 12px 32px -18px rgba(16,32,26,.35);">

      <!-- Cabecera -->
      <tr>
        <td style="background-color:#0d7350;padding:26px 32px;">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
            <tr>
              <td style="font-family:'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
                         font-size:21px;font-weight:700;color:#ffffff;
                         letter-spacing:-.2px;">
                VitalCrop
              </td>
              <td align="right"
                  style="font-family:'Courier New',Courier,monospace;font-size:11px;
                         color:#a7ddc8;letter-spacing:1.4px;text-transform:uppercase;">
                AGW Dashboard
              </td>
            </tr>
          </table>
        </td>
      </tr>

      <!-- Cuerpo -->
      <tr>
        <td style="padding:34px 32px 8px;">
          <p style="margin:0 0 6px;font-family:'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
                    font-size:19px;font-weight:600;color:#11201a;">
            Tu código de acceso
          </p>
          <p style="margin:0 0 24px;font-family:'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
                    font-size:14px;line-height:1.65;color:#566a61;">
            Alguien —esperamos que tú— pidió entrar al panel de control del
            cultivo con la dirección
            <span style="color:#11201a;font-weight:600;">{destinatario}</span>.
            Usa este código para completar el acceso.
          </p>
        </td>
      </tr>

      <!-- Código -->
      <tr>
        <td style="padding:0 32px;">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
                 style="background-color:#f2f8f5;border:1px solid #d8ece3;border-radius:8px;">
            <tr>
              <td align="center" style="padding:26px 16px 8px;">
                <div style="font-family:'Courier New',Courier,monospace;
                            font-size:38px;font-weight:700;color:#0d7350;
                            letter-spacing:8px;line-height:1.1;">{digitos}</div>
              </td>
            </tr>
            <tr>
              <td align="center" style="padding:0 16px 22px;">
                <span style="font-family:'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
                             font-size:12px;color:#7c8d85;">
                  Caduca en {minutos} minutos · un solo uso
                </span>
              </td>
            </tr>
          </table>
        </td>
      </tr>

      <!-- Aviso -->
      <tr>
        <td style="padding:26px 32px 0;">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
                 style="border-left:3px solid #d8ece3;">
            <tr>
              <td style="padding:2px 0 2px 14px;
                         font-family:'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
                         font-size:12.5px;line-height:1.6;color:#7c8d85;">
                Si no pediste este código, ignora el mensaje: sin él nadie entra,
                y caduca solo. Nunca te pediremos que lo compartas ni lo
                respondas por correo.
              </td>
            </tr>
          </table>
        </td>
      </tr>

      <!-- Pie -->
      <tr>
        <td style="padding:30px 32px 28px;">
          <div style="border-top:1px solid #e6ece9;padding-top:16px;
                      font-family:'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
                      font-size:11.5px;line-height:1.6;color:#9aa8a1;">
            VitalCrop AGW · Monitoreo y control de cultivo en ambiente controlado<br>
            Gateway <span style="font-family:'Courier New',monospace;">FOG_RPI_HIERBABUENA_01</span> ·
            Nodo <span style="font-family:'Courier New',monospace;">IoT-node-26.001</span><br>
            <span style="color:#b6c2bc;">Este mensaje se generó automáticamente. No hace falta responderlo.</span>
          </div>
        </td>
      </tr>

    </table>

    <div style="max-width:560px;margin:14px auto 0;
                font-family:'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
                font-size:11px;color:#9aa8a1;text-align:center;">
      Enviado a {destinatario}
    </div>

  </td></tr>
</table>
</body>
</html>"""


def _plantilla_texto(otp: str, minutos: int) -> str:
    """
    Alternativa en texto plano.

    No es opcional: los filtros de spam penalizan los correos que solo
    traen HTML, y algunos clientes corporativos lo muestran por defecto.
    """
    return (
        "VitalCrop · Tu codigo de acceso\n"
        "================================\n\n"
        f"    {otp}\n\n"
        f"Caduca en {minutos} minutos y solo puede usarse una vez.\n\n"
        "Si no pediste este codigo, ignora este mensaje.\n\n"
        "VitalCrop AGW · Gateway FOG_RPI_HIERBABUENA_01\n"
    )


def enviar_otp(destinatario: str, otp: str, minutos: int = 10) -> bool:
    """
    Manda el código. Devuelve True si Resend lo aceptó.

    No lanza excepción nunca: un fallo del proveedor de correo no puede
    impedir que `request-code` responda 200, porque el código ya está
    guardado en la base y el usuario puede recuperarlo del log. Que el
    login entero se cayera por un problema de correo fue el fallo que
    este módulo viene a corregir.
    """
    api_key = os.getenv("RESEND_API_KEY")
    remitente = os.getenv("RESEND_FROM", _REMITENTE_DEF)

    if not api_key:
        logger.warning("RESEND_API_KEY no configurada — el codigo no se envia")
        logger.info("SIMULADO: OTP %s para %s", otp, destinatario)
        return False

    cuerpo = json.dumps({
        "from": remitente,
        "to": [destinatario],
        "subject": f"{otp} es tu codigo de acceso a VitalCrop",
        "html": _plantilla_html(otp, minutos, destinatario),
        "text": _plantilla_texto(otp, minutos),
        # Etiqueta para poder filtrar estos envios en el panel de Resend
        # sin confundirlos con otros correos del dominio.
        "tags": [{"name": "tipo", "value": "otp"}],
    }).encode("utf-8")

    peticion = urllib.request.Request(
        _RESEND_URL,
        data=cuerpo,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            # Sin User-Agent explicito, urllib manda "Python-urllib/3.x" y
            # el WAF que hay delante de Resend lo bloquea con un 403 de
            # Cloudflare (error 1010) que no se parece en nada a un error
            # de la API: el cuerpo no es JSON y el mensaje no menciona
            # nada del envio.
            "User-Agent": "VitalCrop-AGW/2.0 (+https://github.com/JHONATTANG/vitalcrop)",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(peticion, timeout=_TIMEOUT_S) as resp:
            datos = json.loads(resp.read().decode("utf-8"))
        logger.info("Correo enviado por Resend", extra={"id": datos.get("id")})
        return True

    except urllib.error.HTTPError as exc:
        detalle = exc.read().decode("utf-8", errors="replace")[:300]
        # 403 casi siempre significa dominio sin verificar en Resend.
        logger.error("Resend rechazo el envio (%s): %s", exc.code, detalle)
        logger.info("SIMULADO: OTP %s para %s", otp, destinatario)
        return False

    except Exception as exc:
        logger.error("No se pudo contactar con Resend: %s", exc)
        logger.info("SIMULADO: OTP %s para %s", otp, destinatario)
        return False
