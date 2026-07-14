import os
import httpx
import logging
import uuid
import tempfile
from typing import Optional
from sqlalchemy import select
from pydantic import ValidationError

from app.database import AsyncSessionLocal
from app.models import InvoiceExtraction
from app.ocr import extract_text_from_file
from app.llm import extract_structured_data
from app.schemas import ExtractionDataSchema

logger = logging.getLogger(__name__)

async def download_file(url: str, dest_path: str) -> None:
    """
    Descarga un archivo desde una URL y lo guarda en la ruta destino.
    """
    logger.info(f"Descargando archivo desde la URL: {url}")
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url)
        if response.status_code != 200:
            raise RuntimeError(f"Fallo al descargar archivo (HTTP {response.status_code})")
        with open(dest_path, "wb") as f:
            f.write(response.content)

async def process_document_task(
    job_id: uuid.UUID,
    file_path: Optional[str] = None,
    url: Optional[str] = None
) -> None:
    """
    Procesamiento asíncrono en segundo plano:
    Fase 1 (Preprocesamiento) + Fase 2 (OCR) + Fase 3 (LLM) + Sanity Check
    """
    logger.info(f"Iniciando tarea de procesamiento para el Job ID: {job_id}")
    
    # Determinar tipo de origen
    source_type = "file" if file_path else "url"
    temp_file_path = file_path
    
    # Inicializar variables de estado
    status = "pending"
    extracted_data = {}

    try:
        # 1. Si es una URL, descargar el archivo a un directorio temporal
        if source_type == "url":
            # Crear un archivo temporal
            suffix = ".pdf" if ".pdf" in url.lower() else ".jpg"
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            temp_file_path = temp_file.name
            temp_file.close() # Cerrar para permitir que otros procesos escriban en él
            
            await download_file(url, temp_file_path)

        if not temp_file_path or not os.path.exists(temp_file_path):
            raise FileNotFoundError("El archivo a procesar no existe o no se pudo descargar.")

        import asyncio
        # 2. Fases 1 y 2: Preprocesamiento e inferencia OCR
        logger.info("Ejecutando OCR...")
        # Offload CPU intensive OCR to a thread
        ocr_text = await asyncio.to_thread(extract_text_from_file, temp_file_path)
        logger.debug(f"Texto OCR extraído: {ocr_text[:500]}...")

        if not ocr_text.strip():
            raise ValueError("No se pudo extraer texto del documento (el texto extraído está vacío).")

        # 3. Fase 3: Estructuración con Gemini LLM
        logger.info("Enviando texto a Gemini...")
        # Direct async call
        structured_json = await extract_structured_data(ocr_text)

        # 4. Lógica de Validación y Estados (Sanity Check con Pydantic)
        logger.info("Validando datos estructurados con Pydantic...")
        try:
            # Intentar validar contra el esquema estricto (verifica que cuadre total con conceptos)
            validated_model = ExtractionDataSchema.model_validate(structured_json)
            status = "ok"
            extracted_data = validated_model.model_dump()
            logger.info(f"Validación exitosa (status = ok) para Job ID: {job_id}")
        except ValidationError as val_err:
            # Si hay un error de validación (faltan campos obligatorios o la suma no coincide)
            status = "revisar"
            # Estructurar la información de error para que sea amigable en la BD
            errors_list = [{"loc": e["loc"], "msg": e["msg"], "type": e["type"]} for e in val_err.errors()]
            extracted_data = {
                "raw_data": structured_json,
                "validation_errors": errors_list
            }
            logger.warning(f"Error de validación (status = revisar) para Job ID: {job_id}. Errores: {errors_list}")

    except Exception as e:
        status = "error"
        extracted_data = {
            "error_message": str(e),
            "error_type": type(e).__name__
        }
        logger.error(f"Error procesando Job ID {job_id}: {str(e)}", exc_info=True)

    finally:
        # 5. Limpieza del archivo temporal si fue descargado de URL
        if source_type == "url" and temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
                logger.info(f"Archivo temporal eliminado: {temp_file_path}")
            except Exception as e:
                logger.warning(f"No se pudo eliminar el archivo temporal: {str(e)}")
        
        # Si fue subido como archivo local, la API principal debería eliminar su archivo temporal,
        # pero por si acaso, si termina el pipeline, lo borramos aquí si es una ruta temporal.
        elif source_type == "file" and temp_file_path and "tmp" in temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
                logger.info(f"Archivo temporal de subida eliminado: {temp_file_path}")
            except Exception:
                pass

        # 6. Guardar estado en base de datos
        logger.info(f"Actualizando estado del Job ID {job_id} a '{status}'...")
        async with AsyncSessionLocal() as db:
            try:
                result = await db.execute(
                    select(InvoiceExtraction).filter(InvoiceExtraction.id == job_id)
                )
                db_record = result.scalars().first()
                if db_record:
                    db_record.status = status
                    db_record.extracted_data = extracted_data
                    await db.commit()
                    logger.info(f"Base de datos actualizada con éxito para Job ID {job_id}")
                else:
                    logger.error(f"No se encontró el registro en la BD para el Job ID: {job_id}")
            except Exception as db_err:
                logger.error(f"Error al escribir en la base de datos: {str(db_err)}")
                await db.rollback()
