from pydantic import BaseModel, Field, model_validator, ConfigDict
import math
import uuid
from datetime import datetime
from typing import List, Any, Dict, Optional

class ConceptoSchema(BaseModel):
    descripcion: str = Field(..., description="Descripción del concepto o artículo")
    cantidad: float = Field(..., description="Cantidad del concepto")
    precio_unitario: float = Field(..., description="Precio unitario del concepto")
    importe: float = Field(..., description="Importe total del concepto (generalmente cantidad * precio_unitario)")

class ExtractionDataSchema(BaseModel):
    proveedor: str = Field(..., description="Nombre del proveedor o emisor de la factura")
    folio: str = Field(..., description="Folio, número de factura o identificación del documento")
    fecha: str = Field(..., description="Fecha de emisión del documento")
    total: float = Field(..., description="Total de la factura")
    conceptos: List[ConceptoSchema] = Field(..., description="Lista de conceptos detallados en la factura")

    @model_validator(mode="after")
    def verify_total(self) -> "ExtractionDataSchema":
        sum_importes = sum(c.importe for c in self.conceptos)
        # Comparación con tolerancia de 0.01 para evitar problemas de coma flotante
        if not math.isclose(sum_importes, self.total, abs_tol=0.01):
            raise ValueError(
                f"La suma de los importes de los conceptos ({round(sum_importes, 2)}) "
                f"no coincide con el total reportado ({round(self.total, 2)})"
            )
        return self

# Esquemas para la API REST

class ExtractRequest(BaseModel):
    url: Optional[str] = Field(None, description="URL del documento PDF o imagen a procesar")

class JobResponse(BaseModel):
    job_id: uuid.UUID
    status: str

class ExtractionListItem(BaseModel):
    id: uuid.UUID
    source_type: str
    status: str
    extracted_data: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class PaginatedExtractionsResponse(BaseModel):
    items: List[ExtractionListItem]
    total: int
    limit: int
    offset: int
