#!/usr/bin/env python3
"""
Simulador de Webhooks de Llamadas de Voz con IA (Vapi AI y Retell AI)
Permite probar la recepción de eventos de fin de llamada, parseo de transcripciones
y la posterior derivación comercial hacia el asesor asignado.

Uso:
    python tests/simulate_voice.py --provider vapi --type compra
    python tests/simulate_voice.py --provider vapi --type cotizacion
    python tests/simulate_voice.py --provider retell --type compra
    python tests/simulate_voice.py --provider retell --type cotizacion
"""

import argparse
import sys
import time
import httpx


def generate_vapi_payload(phone: str, name: str, intent_type: str, custom_text: str = None):
    call_id = f"vapi_{int(time.time() * 1000)}"
    
    if custom_text:
        transcript = f"Cliente: {custom_text}"
        summary = custom_text
    elif intent_type == "compra":
        transcript = "Agente: Bienvenido a Ventas. ¿Cómo podemos ayudarte? Cliente: Hola, quiero comprar de inmediato 15 licencias empresariales. ¿Dónde puedo pagar o transferir ya?"
        summary = "El cliente desea realizar la compra de 15 licencias hoy mismo."
    else:
        transcript = "Agente: Bienvenido a Ventas. ¿Cómo podemos ayudarte? Cliente: Buen día, necesitamos una cotización formal detallada y desglosada para presentar al comité de compras."
        summary = "Solicitud de cotización formal con membrete."

    return {
        "message": {
            "type": "end-of-call-report",
            "call": {
                "id": call_id,
                "customer": {
                    "number": phone,
                    "name": name
                },
                "status": "ended"
            },
            "transcript": transcript,
            "summary": summary,
            "recordingUrl": f"https://vapi.ai/recordings/{call_id}.mp3"
        }
    }


def generate_retell_payload(phone: str, name: str, intent_type: str, custom_text: str = None):
    call_id = f"retell_{int(time.time() * 1000)}"

    if custom_text:
        transcript = f"Cliente: {custom_text}"
        summary = custom_text
    elif intent_type == "compra":
        transcript = "Agente: Hola, gracias por llamar. Cliente: Hola, quiero comprar el servicio ahora mismo, pásenme el link de pago o la cuenta bancaria por favor."
        summary = "Cliente solicita datos de pago para comprar ya."
    else:
        transcript = "Agente: Hola, gracias por llamar. Cliente: Hola, queremos solicitar una propuesta formal y cotización por volumen de 50 puestos para evaluar."
        summary = "Petición de propuesta comercial por volumen."

    return {
        "event": "call_analyzed",
        "call_id": call_id,
        "from_number": phone,
        "customer_name": name,
        "transcript": transcript,
        "call_analysis": {
            "call_summary": summary
        },
        "recording_url": f"https://retellai.com/recordings/{call_id}.wav"
    }


def main():
    parser = argparse.ArgumentParser(description="Simulador de Webhooks de Llamadas de Voz con IA")
    parser.add_argument(
        "--provider",
        choices=["vapi", "retell", "auto"],
        default="vapi",
        help="Proveedor de voz a simular"
    )
    parser.add_argument(
        "--type",
        choices=["compra", "cotizacion"],
        default="compra",
        help="Intención comercial a simular"
    )
    parser.add_argument(
        "--phone",
        default="+5491133339999",
        help="Teléfono del cliente que llamó"
    )
    parser.add_argument(
        "--name",
        default="Cliente Voz",
        help="Nombre del cliente"
    )
    parser.add_argument(
        "--custom",
        type=str,
        help="Texto personalizado de transcripción"
    )

    args = parser.parse_args()

    # Seleccionar endpoint según el proveedor
    if args.provider == "vapi":
        endpoint = "http://localhost:8000/api/v1/webhooks/voice/vapi"
        payload = generate_vapi_payload(args.phone, args.name, args.type, args.custom)
    elif args.provider == "retell":
        endpoint = "http://localhost:8000/api/v1/webhooks/voice/retell"
        payload = generate_retell_payload(args.phone, args.name, args.type, args.custom)
    else:
        endpoint = "http://localhost:8000/api/v1/webhooks/voice"
        payload = generate_vapi_payload(args.phone, args.name, args.type, args.custom)

    print("=" * 65)
    print(f"🎙️  SIMULADOR DE LLAMADAS DE VOZ CON IA")
    print(f"🏢 Proveedor: {args.provider.upper()}")
    print(f"🎯 Intención: {args.type.upper()}")
    print(f"👤 Cliente:   {args.name} ({args.phone})")
    print(f"🌐 Destino:   {endpoint}")
    print("=" * 65)

    try:
        start_time = time.time()
        with httpx.Client(timeout=10.0) as client:
            response = client.post(endpoint, json=payload)
            elapsed_ms = (time.time() - start_time) * 1000

        print(f"\n📥 RESPUESTA DEL SERVIDOR (Tiempo: {elapsed_ms:.1f}ms):")
        print(f"Código HTTP: {response.status_code}")
        print(f"Respuesta:   {response.json()}")

        if response.status_code == 200 and response.json().get("status") == "received":
            print("\n✅ ÉXITO: La llamada de voz fue recibida, normalizada y encolada para enrutamiento comercial.")
        else:
            print(f"\n❌ Código de respuesta inesperado: {response.status_code}")

    except httpx.ConnectError:
        print(f"\n⚠️  No se pudo conectar al backend en {endpoint}.")
        print("Inicia el servidor con: uvicorn app.main:app --port 8000")
        sys.exit(1)


if __name__ == "__main__":
    main()
