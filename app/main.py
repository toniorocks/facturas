import os
import uuid
import logging
import tempfile
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, UploadFile, File, Form, HTTPException, status, BackgroundTasks
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, init_db
from app.models import InvoiceExtraction
from app.schemas import JobResponse, PaginatedExtractionsResponse, ExtractionListItem
from app.processor import process_document_task

# Configuración del logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("app.main")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Evento de inicio
    logger.info("Iniciando la aplicación...")
    try:
        await init_db()
        logger.info("Base de datos inicializada y tablas creadas (si no existían).")
    except Exception as e:
        logger.error(f"Error al inicializar la base de datos en el inicio: {str(e)}")
        # En producción se podría reintentar o abortar el inicio
    yield
    # Evento de apagado
    logger.info("Apagando la aplicación...")

app = FastAPI(
    title="API de Procesamiento de Recibos y Facturas",
    description="API asíncrona para la extracción estructurada de datos de facturas usando OCR y LLM.",
    version="1.0.0",
    lifespan=lifespan
)

@app.get("/health", tags=["Salud"])
def health_check():
    return {"status": "healthy", "service": "invoice-processor-api"}

@app.post(
    "/extract",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=JobResponse,
    tags=["Extracción"],
    summary="Inicia el procesamiento de un documento en segundo plano"
)
async def extract_invoice(
    background_tasks: BackgroundTasks,
    file: Optional[UploadFile] = File(None),
    url: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db)
):
    """
    Recibe un documento (archivo físico de máximo 5MB o una URL externa).
    
    Valida las entradas, guarda un registro inicial con estado **pending** en la
    base de datos y lanza el pipeline en segundo plano de manera asíncrona.
    """
    # 1. Validación de exclusividad de campos
    if file is not None and url is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Debe proporcionar un archivo físico O una URL externa, no ambos."
        )
    if file is None and url is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Debe proporcionar al menos un archivo físico o una URL externa."
        )

    job_id = uuid.uuid4()
    source_type = "file" if file is not None else "url"
    
    temp_file_path = None

    if file is not None:
        # 2. Validación de tamaño de archivo (máximo 5MB en backend por seguridad adicional)
        # Nginx ya aplica un límite de 5M, pero aquí garantizamos que la app de Python no sature memoria.
        MAX_SIZE = 5 * 1024 * 1024  # 5MB
        
        # Leer el archivo por chunks para no cargar todo en memoria a la vez
        contents = await file.read(1024)
        size = len(contents)
        
        # Crear un archivo temporal físico para pasar al pipeline OCR
        # Usamos suffix para que pytesseract/pdf2image identifique el tipo de archivo (ej. .pdf, .png)
        file_ext = os.path.splitext(file.filename)[1].lower() if file.filename else ""
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=file_ext)
        temp_file_path = temp_file.name
        
        try:
            temp_file.write(contents)
            while True:
                chunk = await file.read(1024 * 64) # leer de a 64KB
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_SIZE:
                    # Cerrar y eliminar archivo temporal antes de lanzar el error
                    temp_file.close()
                    os.remove(temp_file_path)
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail="El archivo excede el tamaño máximo permitido de 5MB."
                    )
                temp_file.write(chunk)
            temp_file.close()
        except HTTPException:
            raise
        except Exception as e:
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
            logger.error(f"Error escribiendo archivo temporal: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error interno al guardar el archivo cargado."
            )
            
    # 3. Crear registro inicial en la Base de Datos
    db_record = InvoiceExtraction(
        id=job_id,
        source_type=source_type,
        status="pending",
        extracted_data=None
    )
    
    try:
        db.add(db_record)
        await db.commit()
    except Exception as db_err:
        if temp_file_path and os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        logger.error(f"Fallo al registrar la tarea en base de datos: {str(db_err)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error en persistencia de datos al registrar la tarea."
        )

    # 4. Encolar la tarea en segundo plano asíncrona
    if source_type == "file":
        background_tasks.add_task(
            process_document_task,
            job_id=job_id,
            file_path=temp_file_path
        )
    else:
        background_tasks.add_task(
            process_document_task,
            job_id=job_id,
            url=url
        )

    return JobResponse(job_id=job_id, status="pending")

@app.get(
    "/extractions",
    response_model=PaginatedExtractionsResponse,
    tags=["Extracción"],
    summary="Devuelve una lista paginada de extracciones"
)
async def list_extractions(
    limit: int = 10,
    offset: int = 0,
    db: AsyncSession = Depends(get_db)
):
    """
    Consulta la base de datos y devuelve una lista paginada de los documentos procesados,
    incluyendo su estado actual y la información estructurada extraída.
    """
    if limit < 1 or limit > 100:
        limit = 10
    if offset < 0:
        offset = 0

    # Consulta para obtener los items paginados
    query = select(InvoiceExtraction).order_by(InvoiceExtraction.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(query)
    items = result.scalars().all()

    # Consulta para obtener el total de registros
    total_query = select(func.count()).select_from(InvoiceExtraction)
    total_result = await db.execute(total_query)
    total = total_result.scalar() or 0

    return PaginatedExtractionsResponse(
        items=[ExtractionListItem.from_orm(item) for item in items],
        total=total,
        limit=limit,
        offset=offset
    )

@app.delete(
    "/extractions/{job_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Extracción"],
    summary="Elimina una extracción por ID"
)
async def delete_extraction(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Elimina un registro de extracción específico usando su ID.
    """
    # Verificar si existe
    result = await db.execute(select(InvoiceExtraction).filter(InvoiceExtraction.id == job_id))
    db_record = result.scalars().first()
    if not db_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Extracción no encontrada."
        )
    
    await db.execute(delete(InvoiceExtraction).where(InvoiceExtraction.id == job_id))
    await db.commit()
    return None

@app.delete(
    "/extractions",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Extracción"],
    summary="Elimina todas las extracciones"
)
async def delete_all_extractions(
    db: AsyncSession = Depends(get_db)
):
    """
    Elimina todos los registros de extracción de la base de datos.
    """
    await db.execute(delete(InvoiceExtraction))
    await db.commit()
    return None
