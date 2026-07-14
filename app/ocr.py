import os
import logging
from typing import List
import cv2
import numpy as np
import pytesseract
from PIL import Image
from pdf2image import convert_from_path, convert_from_bytes

logger = logging.getLogger(__name__)

def preprocess_image(pil_image: Image.Image) -> Image.Image:
    """
    Fase 1: Preprocesamiento Visual con OpenCV
    Convierte la imagen a escala de grises, ajusta el contraste, aplica umbralizado y elimina el ruido.
    """
    try:
        # 1. Convertir de PIL a formato OpenCV (numpy array BGR)
        open_cv_image = np.array(pil_image)
        # Si la imagen tiene canal alfa (RGBA), convertir a RGB
        if open_cv_image.ndim == 3 and open_cv_image.shape[2] == 4:
            open_cv_image = cv2.cvtColor(open_cv_image, cv2.COLOR_RGBA2BGR)
        elif open_cv_image.ndim == 3:
            open_cv_image = cv2.cvtColor(open_cv_image, cv2.COLOR_RGB2BGR)
        else:
            # Ya está en escala de grises o formato de canal único
            pass

        # 2. Escala de grises (si no lo está ya)
        if len(open_cv_image.shape) == 3:
            gray = cv2.cvtColor(open_cv_image, cv2.COLOR_BGR2GRAY)
        else:
            gray = open_cv_image

        # 3. Ajustar contraste (CLAHE - Contrast Limited Adaptive Histogram Equalization)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        contrast = clahe.apply(gray)

        # 4. Eliminar ruido (Filtro Gaussiano suave para limpiar imperfecciones)
        denoised = cv2.GaussianBlur(contrast, (3, 3), 0)

        # 5. Umbralizado (Thresholding adaptativo o binarización de Otsu)
        # Otsu calcula el umbral óptimo de forma automática
        _, threshold = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        # 6. Convertir de vuelta a PIL Image para Pytesseract
        preprocessed_pil = Image.fromarray(threshold)
        return preprocessed_pil

    except Exception as e:
        logger.error(f"Error en el preprocesamiento de la imagen: {str(e)}")
        # En caso de error, devolvemos la imagen original para no bloquear el flujo
        return pil_image

def extract_text_from_image(pil_image: Image.Image) -> str:
    """
    Fase 2: Extracción OCR local usando Pytesseract
    """
    try:
        # Configurar idiomas: Español e Inglés
        custom_config = r'--oem 3 --psm 4'
        text = pytesseract.image_to_string(pil_image, lang='spa+eng', config=custom_config)
        return text
    except Exception as e:
        logger.error(f"Error durante la extracción OCR con Tesseract: {str(e)}")
        raise RuntimeError(f"Fallo en Tesseract OCR: {str(e)}")

def extract_text_from_file(file_path: str) -> str:
    """
    Determina el tipo de archivo, realiza la conversión si es PDF,
    preprocesa y extrae el texto usando OCR.
    """
    ext = os.path.splitext(file_path)[1].lower()
    
    if ext == '.pdf':
        logger.info(f"Procesando PDF: {file_path}")
        try:
            # Convertir PDF a lista de imágenes PIL
            pages = convert_from_path(file_path, dpi=200)
        except Exception as e:
            logger.error(f"Error al convertir PDF a imágenes: {str(e)}")
            raise RuntimeError(f"Error de conversión PDF a Imagen (pdf2image): {str(e)}")
        
        full_text = []
        for i, page in enumerate(pages):
            logger.info(f"Procesando página {i+1} de {len(pages)}")
            preprocessed_page = preprocess_image(page)
            page_text = extract_text_from_image(preprocessed_page)
            full_text.append(f"--- PÁGINA {i+1} ---\n{page_text}")
        
        return "\n\n".join(full_text)
    
    else:
        # Asumimos que es una imagen (PNG, JPG, JPEG, etc.)
        logger.info(f"Procesando Imagen: {file_path}")
        try:
            with Image.open(file_path) as img:
                preprocessed_img = preprocess_image(img)
                return extract_text_from_image(preprocessed_img)
        except Exception as e:
            logger.error(f"Error al procesar imagen: {str(e)}")
            raise RuntimeError(f"Error procesando archivo de imagen: {str(e)}")
