import pytest
import uuid
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app
from app.database import get_db

client = TestClient(app)

@pytest.fixture
def mock_db():
    mock_session = AsyncMock()
    # Sobrescribimos la dependencia get_db para evitar conectar a la BD real en los tests
    app.dependency_overrides[get_db] = lambda: mock_session
    yield mock_session
    app.dependency_overrides.clear()

def test_health_endpoint():
    """
    Verifica que el endpoint /health responda correctamente.
    """
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "service": "invoice-processor-api"}

def test_extract_endpoint_validation_no_params(mock_db):
    """
    Verifica que /extract devuelva 400 Bad Request si no se envía ni archivo ni URL.
    """
    response = client.post("/extract")
    assert response.status_code == 400
    assert "Debe proporcionar al menos un archivo físico o una URL externa" in response.json()["detail"]

def test_extract_endpoint_validation_both_params(mock_db):
    """
    Verifica que /extract devuelva 400 Bad Request si se envían tanto archivo como URL.
    """
    response = client.post(
        "/extract",
        data={"url": "https://example.com/invoice.pdf"},
        files={"file": ("invoice.png", b"file content", "image/png")}
    )
    assert response.status_code == 400
    assert "Debe proporcionar un archivo físico O una URL externa, no ambos" in response.json()["detail"]

@patch("app.main.BackgroundTasks.add_task")
def test_extract_endpoint_url_success(mock_add_task, mock_db):
    """
    Verifica que /extract acepte una URL válida, cree el registro
    con estado pending y encole la tarea en background.
    """
    # Mockear el commit en la BD
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    
    url_test = "https://example.com/invoice.pdf"
    response = client.post("/extract", data={"url": url_test})
    
    assert response.status_code == 202
    res_json = response.json()
    assert "job_id" in res_json
    assert res_json["status"] == "pending"
    
    # Verificar que se encoló la tarea en segundo plano
    mock_add_task.assert_called_once()
    args, kwargs = mock_add_task.call_args
    assert kwargs["url"] == url_test
    assert isinstance(kwargs["job_id"], uuid.UUID)

@patch("app.main.BackgroundTasks.add_task")
def test_extract_endpoint_file_success(mock_add_task, mock_db):
    """
    Verifica que /extract acepte un archivo físico válido, cree el registro
    y encole la tarea en background.
    """
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    
    file_content = b"pdf dummy content"
    response = client.post(
        "/extract",
        files={"file": ("invoice.pdf", file_content, "application/pdf")}
    )
    
    assert response.status_code == 202
    res_json = response.json()
    assert "job_id" in res_json
    assert res_json["status"] == "pending"
    
    # Verificar que se encoló la tarea en segundo plano
    mock_add_task.assert_called_once()
    args, kwargs = mock_add_task.call_args
    assert "file_path" in kwargs
    assert kwargs["file_path"] is not None
    assert isinstance(kwargs["job_id"], uuid.UUID)
