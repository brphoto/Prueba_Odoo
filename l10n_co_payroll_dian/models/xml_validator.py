from functools import lru_cache
from io import BytesIO
from pathlib import Path

from lxml import etree


MODULE_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = MODULE_DIR / "dian_assets"
XSD_DIR = ASSETS_DIR / "xsd"


@lru_cache(maxsize=2)
def _load_schema(is_adjustment):
    schema_name = (
        "NominaIndividualDeAjusteElectronicaXSDV1.0.6.xsd"
        if is_adjustment
        else "NominaIndividualElectronicaXSDV1.0.6.xsd"
    )
    schema_path = XSD_DIR / schema_name
    schema_doc = etree.parse(str(schema_path))
    return etree.XMLSchema(schema_doc)


def validate_xml(xml_bytes, is_adjustment):
    schema = _load_schema(is_adjustment)
    try:
        doc = etree.parse(BytesIO(xml_bytes))
    except (etree.XMLSyntaxError, OSError, ValueError) as exc:
        return False, [f"XML invalido: {exc}"]
    is_valid = schema.validate(doc)
    errors = []
    if not is_valid:
        for error in schema.error_log:
            errors.append(f"L{error.line} C{error.column}: {error.message}")
    return is_valid, errors
