import pytest
from pydantic import ValidationError
from app.schemas import ExtractionDataSchema, ConceptoSchema

def test_valid_invoice_schema():
    """
    Verifica que un JSON de factura correcto e internamente consistente
    pase la validación Pydantic sin errores.
    """
    valid_data = {
        "proveedor": "Abarrotes La Esquina S.A.",
        "folio": "F-45892",
        "fecha": "2026-03-01",
        "total": 150.50,
        "conceptos": [
            {
                "descripcion": "Caja de leche de soya",
                "cantidad": 2,
                "precio_unitario": 50.00,
                "importe": 100.00
            },
            {
                "descripcion": "Paquete de galletas avena",
                "cantidad": 1,
                "precio_unitario": 50.50,
                "importe": 50.50
            }
        ]
    }
    
    # Debe instanciarse correctamente
    schema = ExtractionDataSchema.model_validate(valid_data)
    assert schema.proveedor == "Abarrotes La Esquina S.A."
    assert schema.total == 150.50
    assert len(schema.conceptos) == 2

def test_invalid_total_mismatch():
    """
    Verifica que si la suma de los conceptos no coincide con el total reportado,
    se lance un ValidationError debido a la lógica del validador de Pydantic.
    """
    invalid_data = {
        "proveedor": "Papelería Del Centro",
        "folio": "T-1002",
        "fecha": "2026-03-02",
        "total": 500.00,  # El total reportado es 500
        "conceptos": [
            {
                "descripcion": "Libreta profesional",
                "cantidad": 3,
                "precio_unitario": 100.00,
                "importe": 300.00  # Suma total = 300
            }
        ]
    }
    
    with pytest.raises(ValidationError) as exc_info:
        ExtractionDataSchema.model_validate(invalid_data)
        
    # Verificar que el error sea sobre la discrepancia matemática
    assert "La suma de los importes de los conceptos" in str(exc_info.value)
    assert "no coincide con el total reportado" in str(exc_info.value)

def test_missing_required_fields():
    """
    Verifica que falten campos obligatorios (como el folio)
    resulte en un ValidationError estándar de Pydantic.
    """
    # Falta el campo folio
    missing_folio_data = {
        "proveedor": "Restaurante Mexicano",
        "fecha": "2026-03-03",
        "total": 200.00,
        "conceptos": [
            {
                "descripcion": "Comida corrida",
                "cantidad": 1,
                "precio_unitario": 200.00,
                "importe": 200.00
            }
        ]
    }
    
    with pytest.raises(ValidationError) as exc_info:
        ExtractionDataSchema.model_validate(missing_folio_data)
        
    assert "folio" in str(exc_info.value)
