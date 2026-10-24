#!/usr/bin/env python3
"""
Simulador de Webhooks de WhatsApp (Evolution API / Meta Cloud API)
Permite enviar payloads de prueba al webhook local para verificar la recepción
y el comportamiento del asistente sin depender de un teléfono físico en esta etapa.

Uso:
    python tests/simulate_webhook.py --type compra
    python tests/simulate_webhook.py --type cotizacion
    python tests/simulate_webhook.py --type outgoing
    python tests/simulate_webhook.py --custom "Quiero comprar 3 unidades ya"
"""

import argparse
import sys
import time
import httpx


def generate_evolution_payload(message_text: str, sender_phone: str, sender_name: str, from_me: bool = False):
    timestamp_sec = int(time.time())
    msg_id = f"SIM_{int(time.time() * 1000)}"
    remote_jid = f"{sender_phone.replace('+', '')}@s.whatsapp.net"

    return {
        "event": "messages.upsert",
        "instance": "asistente-comercial",
        "data": {
            "key": {
                "remoteJid": remote_jid,
                "fromMe": from_me,
                "id": msg_id
            },
            "pushName": sender_name,
            "message": {
                "conversation": message_text
            },
            "messageType": "conversation",
            "messageTimestamp": timestamp_sec
        },
        "destination": "http://localhost:8000/api/v1/webhooks/whatsapp",
        "date_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "sender": remote_jid
    }


def main():
    parser = argparse.ArgumentParser(description="Simulador de Webhook de WhatsApp")
    parser.add_argument(
        "--url",
        default="http://localhost:8000/api/v1/webhooks/whatsapp",
        help="URL del endpoint webhook de WhatsApp"
    )
    parser.add_argument(
        "--type",
        choices=["compra", "cotizacion", "outgoing"],
        default="compra",
        help="Tipo de escenario a simular"
    )
    parser.add_argument(
        "--custom",
        type=str,
        help="Texto personalizado para enviar"
    )
    parser.add_argument(
        "--phone",
        default="+5491144445555",
        help="Número de teléfono simulado del cliente"
    )
    parser.add_argument(
        "--name",
        default="Cliente Prueba",
        help="Nombre simulado del cliente"
    )

    args = parser.parse_args()

    # Selección del escenario
    if args.custom:
        text = args.custom
        from_me = False
        scenario_label = "PERSONALIZADO"
    elif args.type == "compra":
        text = "¡Buenas tardes! Deseo comprar el paquete corporativo de 20 licencias de forma inmediata. ¿Cuál es el link de pago?"
        from_me = False
        scenario_label = "INTENCIÓN DE COMPRA DIRECTA"
    elif args.type == "cotizacion":
        text = "Hola, somos la empresa Logística Sur. Solicitamos una cotización formal y desglosada con membrete para presentar a directorio."
        from_me = False
        scenario_label = "INTENCIÓN DE COTIZACIÓN FORMAL"
    elif args.type == "outgoing":
        text = "Mensaje automático enviado por el bot al cliente."
        from_me = True
        scenario_label = "MENSAJE PROPIO DEL BOT (Debe ser IGNORADO)"
    else:
        text = "Hola"
        from_me = False
        scenario_label = "GENÉRICO"

    payload = generate_evolution_payload(
        message_text=text,
        sender_phone=args.phone,
        sender_name=args.name,
        from_me=from_me
    )

    print("=" * 65)
    print(f"📡 SIMULADOR DE WEBHOOK DE WHATSAPP")
    print(f"🎯 Escenario: {scenario_label}")
    print(f"🌐 Destino:   {args.url}")
    print(f"👤 Remitente: {args.name} ({args.phone})")
    print(f"💬 Mensaje:   '{text}'")
    print(f"🤖 fromMe:    {from_me}")
    print("=" * 65)

    try:
        with httpx.Client(timeout=10.0) as client:
            start_time = time.time()
            response = client.post(args.url, json=payload)
            elapsed_ms = (time.time() - start_time) * 1000

        print(f"\n📥 RESPUESTA DEL SERVIDOR (Tiempo: {elapsed_ms:.1f}ms):")
        print(f"Código HTTP: {response.status_code}")
        print(f"Respuesta:   {response.json()}")

        if response.status_code == 200:
            status = response.json().get("status")
            if status == "received":
                print("\n✅ ÉXITO: El webhook aceptó el mensaje y lo encoló para procesamiento en segundo plano.")
            elif status == "ignored":
                print("\n✅ ÉXITO: El webhook identificó correctamente el mensaje como descartable (anti-loop).")
        else:
            print(f"\n❌ ERROR: El servidor respondió con código {response.status_code}")

    except httpx.ConnectError:
        print(f"\n⚠️  No se pudo conectar a {args.url}.")
        print("Asegúrate de que el servidor FastAPI esté corriendo con:")
        print("    source venv/bin/activate && uvicorn app.main:app --reload --port 8000")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error al enviar la petición: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
