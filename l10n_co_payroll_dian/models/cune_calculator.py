import hashlib


def _normalize_value(value):
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value).strip()


def build_cune_seed(values):
    ordered_keys = [
        "NumeroCompleto",
        "FechaGen",
        "HoraGen",
        "DevengadosTotal",
        "DeduccionesTotal",
        "ComprobanteTotal",
        "EmpleadorNIT",
        "TrabajadorID",
        "TipoXML",
        "SoftwarePIN",
        "Ambiente",
    ]
    return "".join(_normalize_value(values.get(key)) for key in ordered_keys)


def calculate_cune(values):
    seed = build_cune_seed(values)
    return hashlib.sha384(seed.encode("utf-8")).hexdigest()
