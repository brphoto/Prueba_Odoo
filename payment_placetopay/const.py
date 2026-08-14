# Default sandbox host. Production hosts are region-specific (Colombia, Ecuador,
# Chile, etc.) and must be set by the merchant on the provider record, e.g.:
#   - https://checkout-test.placetopay.com  (sandbox, all regions)
#   - https://checkout-co.placetopay.com    (Colombia production)
#   - https://checkout.placetopay.ec        (Ecuador production)
# See https://docs.placetopay.dev/checkout for the exact host assigned to you.
DEFAULT_BASE_URL = 'https://checkout-test.placetopay.com'

SESSION_ENDPOINT = '/api/session'

DEFAULT_PAYMENT_METHOD_CODES = {'placetopay'}

# Status values documented by PlacetoPay for the `status.status` field of a session
# or a payment attempt.
STATUS_MAPPING = {
    'pending': ('PENDING', 'PENDING_VALIDATION', 'PENDING_PROCESS'),
    'done': ('APPROVED', 'OK'),
    'canceled': ('REJECTED_BY_PAYER', 'ABANDONED'),
    'error': ('REJECTED', 'FAILED'),
}

DOCUMENT_TYPE_SELECTION = [
    ('CC', "Cédula de ciudadanía (CC)"),
    ('CE', "Cédula de extranjería (CE)"),
    ('NIT', "NIT"),
    ('RUC', "RUC"),
    ('TI', "Tarjeta de identidad (TI)"),
    ('PPN', "Pasaporte (PPN)"),
]

LOCALE_SELECTION = [
    ('es_CO', "Español (Colombia)"),
    ('es_EC', "Español (Ecuador)"),
    ('es_CL', "Español (Chile)"),
    ('es_PE', "Español (Perú)"),
    ('es_MX', "Español (México)"),
    ('en_US', "English (US)"),
]
