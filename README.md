# Facturas API

Una API construida con FastAPI para el procesamiento, extracción y análisis de facturas utilizando OCR (Tesseract) y modelos de lenguaje de gran tamaño (LLM - Google Gemini).

## Componentes del Proyecto

El proyecto está compuesto por los siguientes servicios y tecnologías:
- **FastAPI**: Framework web de alto rendimiento para construir la API.
- **PostgreSQL**: Base de datos relacional (con soporte asíncrono a través de `asyncpg`) para almacenar la información estructurada de las facturas.
- **Tesseract OCR, Poppler & OpenCV**: Herramientas a nivel de sistema para el procesamiento de imágenes, PDFs y reconocimiento óptico de caracteres (OCR).
- **Google Gemini**: Modelo de lenguaje (LLM) utilizado para interpretar y extraer información estructurada (fechas, montos, conceptos) del texto plano extraído de las facturas.
- **Nginx**: Servidor web que actúa como proxy inverso.
- **Docker & Docker Compose**: Orquestación y contenedorización de los servicios (API, Base de Datos y Nginx) para facilitar la instalación.

## Requisitos Previos

Antes de instalar y ejecutar el proyecto, asegúrate de tener instalado en tu sistema:
- [Git](https://git-scm.com/)
- [Docker](https://www.docker.com/)
- [Docker Compose](https://docs.docker.com/compose/)

## Instalación y Configuración

### 1. Clonar el repositorio

Abre tu terminal y ejecuta:

```bash
git clone <URL_DEL_REPOSITORIO>
cd facturas
```
*(Nota: Reemplaza `<URL_DEL_REPOSITORIO>` con la URL real de este repositorio en caso de tenerlo alojado en GitHub, GitLab, etc.)*

### 2. Configurar las variables de entorno

El proyecto utiliza un archivo `.env` para manejar la configuración, incluyendo credenciales de base de datos y la API Key de Gemini. 

Copia el archivo de ejemplo para crear tu configuración local:

```bash
cp .env.example .env
```

Abre el archivo `.env` en tu editor de código favorito y asegúrate de agregar tu API Key de Gemini:

```ini
# Configuración del LLM
GEMINI_API_KEY=tu_api_key_de_gemini_aqui

# Configuración de Base de Datos (PostgreSQL)
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres_secure_pass
POSTGRES_DB=facturas_db
DATABASE_URL=postgresql+asyncpg://postgres:postgres_secure_pass@db:5432/facturas_db

# Configuración de la API
PORT=8000
HOST=0.0.0.0
ENV=development
```
*Si no tienes una API Key de Gemini, puedes obtener una en [Google AI Studio](https://aistudio.google.com/).*

### 3. Construir y ejecutar con Docker Compose

El proyecto está completamente dockerizado. Para levantar todos los servicios (API, PostgreSQL y Nginx), ejecuta el siguiente comando en la raíz del proyecto:

```bash
docker-compose up --build -d
```

Este comando:
1. Descargará las imágenes base de PostgreSQL y Nginx.
2. Construirá la imagen de la API definida en el `Dockerfile`, instalando las dependencias del sistema operativo (Tesseract, Poppler, OpenCV) y de Python (`requirements.txt`).
3. Levantará los contenedores en segundo plano (`-d`).

### 4. Verificar que la aplicación esté en funcionamiento

Una vez que el proceso finalice y los contenedores estén corriendo, la API estará lista para recibir peticiones.

- **Documentación interactiva de la API (Swagger UI):** Puedes acceder a `http://localhost/docs` o `http://localhost:8000/docs` para ver todos los endpoints disponibles y probarlos.
- **Base de datos:** Se expone localmente en el puerto `5432`, por lo que puedes conectarte utilizando herramientas como DBeaver o pgAdmin.

## Estructura del Proyecto

- `app/`: Contiene el código fuente principal de la aplicación FastAPI.
  - `main.py`: Punto de entrada de la aplicación FastAPI y definición de endpoints.
  - `models.py` / `schemas.py`: Modelos de base de datos SQLAlchemy y validación de datos con Pydantic.
  - `database.py`: Configuración de conexión asíncrona a la base de datos PostgreSQL.
  - `ocr.py`: Lógica para procesar imágenes o documentos y extraer texto empleando Tesseract.
  - `llm.py`: Integración y promting con la API de Google Gemini para estructurar los datos del OCR.
  - `processor.py`: Orquestador principal que coordina el flujo de extracción OCR -> LLM -> Base de datos.
  - `tests/`: Pruebas automatizadas.
- `nginx/`: Configuración del servidor Nginx (`nginx.conf`).
- `docker-compose.yml`: Definición de la orquestación de los contenedores Docker.
- `Dockerfile`: Instrucciones de construcción de la imagen de la API, incluyendo las dependencias de sistema necesarias.
- `requirements.txt`: Listado de librerías de dependencias de Python (FastAPI, SQLAlchemy, pytesseract, google-generativeai, etc).
- `.env.example`: Plantilla de base para la creación de las variables de entorno.

## Detener el proyecto

Para detener y remover los contenedores, redes y volúmenes temporales, ejecuta:

```bash
docker-compose down
```

*(Si deseas eliminar también el volumen de persistencia de datos de PostgreSQL, añade la bandera `-v` al comando: `docker-compose down -v`)*
