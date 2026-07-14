import json
import logging
import httpx
from app.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """
Eres un asistente experto en extracción de datos y contabilidad.
Tu tarea es analizar el texto extraído mediante OCR de un recibo o factura y estructurarlo en un objeto JSON.

Debes extraer obligatoriamente los siguientes campos:
1. "proveedor": El nombre o razón social del emisor de la factura.
2. "folio": El folio, número de factura, ticket, o ID de documento.
3. "fecha": La fecha de emisión del documento (en formato YYYY-MM-DD o el formato original legible si no se puede determinar).
4. "total": El importe total de la factura en formato numérico (float).
5. "conceptos": Una lista de ítems o conceptos de la factura. Cada concepto debe contener:
   - "descripcion": Nombre o descripción del producto o servicio.
   - "cantidad": Cantidad adquirida (numérico float o int).
   - "precio_unitario": Precio por unidad (numérico float).
   - "importe": Importe total del concepto (cantidad * precio_unitario, numérico float).

Reglas críticas:
- Responde ÚNICAMENTE con el objeto JSON estructurado. No agregues explicaciones, markdown fuera del bloque de JSON, ni comentarios.
- Si falta el folio o algún campo, intenta inferirlo o búscalo de forma exhaustiva.
- Asegúrate de que todos los números sean float y no contengan símbolos de moneda ni comas para los miles (ej: 1250.50 en lugar de $1,250.50).
"""

async def extract_structured_data(ocr_text: str) -> dict:
    """
    Fase 3: Estructuración de datos usando la API REST de Gemini (vía httpx)
    Recibe el texto crudo del OCR y retorna un diccionario estructurado.
    """
    if not settings.GEMINI_API_KEY or settings.GEMINI_API_KEY in ("your_gemini_api_key_here", ""):
        logger.error("API Key de Gemini no configurada")
        raise ValueError("La API Key de Gemini no está configurada en las variables de entorno.")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={settings.GEMINI_API_KEY}"
    
    headers = {
        "Content-Type": "application/json",
    }
    
    payload = {
        "system_instruction": {
            "parts": [{"text": SYSTEM_PROMPT}]
        },
        "contents": [
            {
                "parts": [
                    {"text": f"Texto extraído del documento mediante OCR:\n\n{ocr_text}"}
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.1,
            "responseMimeType": "application/json"
        }
    }
    
    logger.info("Enviando petición a la API REST de Gemini con httpx...")
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            
            if response.status_code != 200:
                error_msg = f"Error HTTP {response.status_code}: {response.text}"
                logger.error(error_msg)
                raise RuntimeError(error_msg)
                
            response_data = response.json()
            
            try:
                content_text = response_data["candidates"][0]["content"]["parts"][0]["text"]
            except (KeyError, IndexError):
                logger.error(f"Estructura de respuesta inesperada: {response_data}")
                raise RuntimeError("La respuesta de Gemini no tiene el formato esperado.")
                
            # Limpiar markdown por precaución
            content_text = content_text.strip()
            if content_text.startswith("```json"):
                content_text = content_text[7:]
            if content_text.endswith("```"):
                content_text = content_text[:-3]
                
            logger.debug(f"Respuesta cruda de Gemini: {content_text}")
            
            structured_data = json.loads(content_text.strip())
            return structured_data
            
    except json.JSONDecodeError as decode_err:
        logger.error(f"Error al decodificar JSON de Gemini: {str(decode_err)}")
        raise ValueError(f"La respuesta de Gemini no es un JSON válido.")
    except Exception as e:
        logger.error(f"Error en la llamada al LLM (Gemini): {str(e)}")
        raise RuntimeError(f"Fallo en la estructuración con LLM: {str(e)}")
