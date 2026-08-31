# Dependencias de Prueba_Odoo

## Instalación

Las dependencias se mantienen en la raíz de los módulos para que todos los
submódulos compartan una única instalación:

```powershell
& "C:\Users\Bryan\Desktop\odoo19e\python\python.exe" -m pip install -r "C:\Program Files\Odoo 19.0e.20251201\server\addons\Prueba_Odoo\requirements.txt"
```

Para ejecutar pruebas que generan PDFs de ejemplo:

```powershell
& "C:\Users\Bryan\Desktop\odoo19e\python\python.exe" -m pip install -r "C:\Program Files\Odoo 19.0e.20251201\server\addons\Prueba_Odoo\requirements-dev.txt"
```

Debe usarse el mismo intérprete Python configurado para el servicio de Odoo;
instalar paquetes en otro Python no modifica el entorno del servidor.

## Qué habilita cada dependencia

| Dependencia | Uso |
|---|---|
| `requests` | Llamadas a OpenAI, PayPhone y conectores HTTP. |
| `pypdf` | Indexación de PDFs con texto en la base de conocimiento. |
| `pdf2image` | Convierte páginas escaneadas para OCR. |
| `pytesseract` | Extrae texto de imágenes de PDF. |
| `pdfminer.six` | Refuerza la extracción de texto de adjuntos PDF de Odoo. |
| `reportlab` | Solo demos y pruebas que generan documentos PDF. |

## OCR en Windows

Las librerías Python no incluyen los ejecutables externos. Para PDFs
escaneados también se necesita:

1. **Tesseract OCR**, disponible en el equipo y en el `PATH` (o configurando
   `pytesseract.pytesseract.tesseract_cmd`). Instalar el paquete de idioma
   español `spa` junto con `eng`.
2. **Poppler**, disponible en el `PATH`, para que `pdf2image` pueda convertir
   el PDF.

Si uno de estos componentes no está disponible, la indexación normal de PDFs
con texto sigue funcionando y el registro de conocimiento queda marcado como
`OCR no disponible` para no ocultar el problema.

## Diagnóstico rápido

Desde la carpeta de Odoo se puede comprobar el entorno con:

```powershell
& "C:\Users\Bryan\Desktop\odoo19e\python\python.exe" -c "import requests,pypdf; print('runtime OK')"
& "C:\Users\Bryan\Desktop\odoo19e\python\python.exe" -c "import pdf2image,pytesseract; print('OCR Python OK')"
tesseract --version
pdftoppm -h
```

No se deben guardar claves de OpenAI, PayPhone ni otros secretos en este
archivo. Las credenciales continúan en los ajustes protegidos de Odoo.
