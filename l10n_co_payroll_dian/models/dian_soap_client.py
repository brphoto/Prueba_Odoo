import base64
import hashlib
import logging
import warnings
import uuid
from datetime import datetime, timedelta

import requests

from lxml import etree

from cryptography import x509
from cryptography.hazmat.primitives.serialization import (
    pkcs12,
    Encoding,
    load_pem_private_key,
)
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding


_logger = logging.getLogger(__name__)


class DianSoapError(Exception):
    def __init__(self, message, detail=None):
        super().__init__(message)
        self.detail = detail or {}


class DianSOAPClient:
    """
    Cliente SOAP WS-Security compatible con DIAN
    para:
        - SendTestSetAsync
        - SendNominaSync
        - GetStatusZip

    Compatible:
        - Odoo 14
        - SOAP 1.2
        - WS-Addressing
        - WS-Security
        - XMLDSig
    """

    SOAP_NS = "http://www.w3.org/2003/05/soap-envelope"

    WSA_NS = "http://www.w3.org/2005/08/addressing"

    WSSE_NS = (
        "http://docs.oasis-open.org/wss/2004/01/"
        "oasis-200401-wss-wssecurity-secext-1.0.xsd"
    )

    WSU_NS = (
        "http://docs.oasis-open.org/wss/2004/01/"
        "oasis-200401-wss-wssecurity-utility-1.0.xsd"
    )

    DS_NS = "http://www.w3.org/2000/09/xmldsig#"

    DIAN_NS = "http://wcf.dian.colombia"

    NSMAP = {
        "soap": SOAP_NS,
        "wsa": WSA_NS,
        "wsse": WSSE_NS,
        "wsu": WSU_NS,
        "ds": DS_NS,
        "wcf": DIAN_NS,
    }

    ACTIONS = {
        "SendTestSetAsync": (
            "http://wcf.dian.colombia/"
            "IWcfDianCustomerServices/SendTestSetAsync"
        ),
        "SendNominaSync": (
            "http://wcf.dian.colombia/"
            "IWcfDianCustomerServices/SendNominaSync"
        ),
        "GetStatusZip": (
            "http://wcf.dian.colombia/"
            "IWcfDianCustomerServices/GetStatusZip"
        ),
        "GetStatus": (
            "http://wcf.dian.colombia/"
            "IWcfDianCustomerServices/GetStatus"
        ),
        "GetXmlByDocumentKey": (
            "http://wcf.dian.colombia/"
            "IWcfDianCustomerServices/GetXmlByDocumentKey"
        ),
    }

    def __init__(
        self,
        wsdl_url,
        p12_bytes,
        p12_password,
        timeout=90,
        verify_ssl=True,
    ):

        self.wsdl_url = wsdl_url

        self.endpoint = wsdl_url.replace("?wsdl", "")

        self.timeout = timeout

        self.verify_ssl = verify_ssl

        self.session = requests.Session()

        self.private_key = None
        self.certificate = None
        self.certificate_chain = []

        self._load_certificate(
            p12_bytes,
            p12_password
        )

    # =========================================================
    # CERTIFICADO
    # =========================================================

    def _load_certificate(
        self,
        p12_bytes,
        p12_password
    ):

        raw_p12 = self._normalize_pkcs12_input(p12_bytes)
        try:

            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message="PKCS#12 bundle could not be parsed as DER, falling back to parsing as BER.*",
                )
                (
                    self.private_key,
                    self.certificate,
                    additional_certificates
                ) = pkcs12.load_key_and_certificates(
                    raw_p12,
                    (p12_password or "").encode()
                )

        except Exception as e:

            raise Exception(
                "Error cargando PKCS12: %(error)s. "
                "Detalle: bytes=%(size)s sha256=%(sha)s clave_cargada=%(has_password)s clave_len=%(password_len)s"
                % {
                    "error": str(e),
                    "size": len(raw_p12 or b""),
                    "sha": hashlib.sha256(raw_p12 or b"").hexdigest()[:16] if raw_p12 else "",
                    "has_password": "si" if bool(p12_password) else "no",
                    "password_len": len(p12_password or ""),
                }
            )

        if not self.private_key:
            raise Exception(
                "Private key no encontrada"
            )

        if not self.certificate:
            raise Exception(
                "Certificado no encontrado"
            )
        self.certificate_chain = self._sort_cert_chain(
            [self.certificate] + list(additional_certificates or [])
        )

    def _load_pem_certificate(
        self,
        pem_certificate,
        pem_key,
        password=None,
    ):

        try:
            cert_bytes = self._normalize_pem_input(pem_certificate)
            key_bytes = self._normalize_pem_input(pem_key)
            encoded_password = (password or "").encode("utf-8") if password else None
            try:
                self.private_key = load_pem_private_key(
                    key_bytes,
                    password=encoded_password,
                )
            except TypeError:
                if encoded_password:
                    self.private_key = load_pem_private_key(
                        key_bytes,
                        password=None,
                    )
                else:
                    raise
            except ValueError as exc:
                if encoded_password and "private key is not encrypted" in str(exc).lower():
                    self.private_key = load_pem_private_key(
                        key_bytes,
                        password=None,
                    )
                else:
                    raise
            self.certificate = x509.load_pem_x509_certificate(cert_bytes)
            self.certificate_chain = [self.certificate]
        except Exception as e:
            raise Exception(
                f"Error cargando PEM: {str(e)}"
            )

        if not self.private_key:
            raise Exception(
                "Private key no encontrada"
            )

        if not self.certificate:
            raise Exception(
                "Certificado no encontrado"
            )

    def _normalize_pem_input(self, value):

        if not value:
            return value

        if isinstance(value, str):
            raw_bytes = value.encode("utf-8")
        else:
            raw_bytes = value

        if b"-----BEGIN" in raw_bytes:
            return raw_bytes

        return base64.b64decode(raw_bytes)

    def _normalize_pkcs12_input(self, value):

        if not value:
            return b""

        if isinstance(value, str):
            raw_bytes = value.encode("utf-8")
        else:
            raw_bytes = value

        # Odoo Binary fields normally arrive here as base64 text. Raw P12 files
        # start with ASN.1 SEQUENCE (0x30), so only decode when it looks textual.
        if raw_bytes[:1] == b"0":
            return raw_bytes

        try:
            return base64.b64decode(raw_bytes, validate=True)
        except Exception:
            return raw_bytes

    def _sort_cert_chain(self, cert_chain):
        """Order certificates as leaf -> intermediates -> root for DIAN validation."""
        if len(cert_chain) <= 1:
            return cert_chain
        sorted_chain = [cert_chain[0]]
        remaining = list(cert_chain[1:])
        current = cert_chain[0]
        while remaining:
            issuer = next((cert for cert in remaining if cert.subject == current.issuer), None)
            if issuer is None:
                sorted_chain.extend(remaining)
                break
            sorted_chain.append(issuer)
            remaining.remove(issuer)
            current = issuer
        return sorted_chain

    # =========================================================
    # HELPERS
    # =========================================================

    def qname(
        self,
        ns,
        tag
    ):
        return f"{{{ns}}}{tag}"

    def generate_id(
        self,
        prefix
    ):
        return f"{prefix}-{uuid.uuid4()}"

    def canonicalize(
        self,
        node
    ):

        return etree.tostring(
            node,
            method="c14n",
            exclusive=True,
            with_comments=False,
        )

    def sha256_digest(
        self,
        data
    ):

        digest = hashlib.sha256(data).digest()

        return base64.b64encode(
            digest
        ).decode()

    def sign_binary(
        self,
        data
    ):

        signature = self.private_key.sign(
            data,
            padding.PKCS1v15(),
            hashes.SHA256(),
        )

        return base64.b64encode(
            signature
        ).decode()

    def now_utc(self):

        return datetime.utcnow()

    # =========================================================
    # SOAP BASE
    # =========================================================

    def build_envelope(
        self,
        operation,
        body_content
    ):

        action = self.ACTIONS[operation]

        envelope = etree.Element(
            self.qname(
                self.SOAP_NS,
                "Envelope"
            ),
            nsmap=self.NSMAP
        )

        header = etree.SubElement(
            envelope,
            self.qname(
                self.SOAP_NS,
                "Header"
            )
        )

        body = etree.SubElement(
            envelope,
            self.qname(
                self.SOAP_NS,
                "Body"
            )
        )

        body_id = self.generate_id(
            "id-body"
        )

        body.set(
            self.qname(
                self.WSU_NS,
                "Id"
            ),
            body_id
        )

        body.append(
            body_content
        )

        # =====================================================
        # ACTION
        # =====================================================

        action_node = etree.SubElement(
            header,
            self.qname(
                self.WSA_NS,
                "Action"
            )
        )

        action_node.text = action
        action_node.set(
            self.qname(
                self.SOAP_NS,
                "mustUnderstand"
            ),
            "1"
        )

        action_id = self.generate_id(
            "id-action"
        )

        action_node.set(
            self.qname(
                self.WSU_NS,
                "Id"
            ),
            action_id
        )

        # =====================================================
        # TO
        # =====================================================

        to_node = etree.SubElement(
            header,
            self.qname(
                self.WSA_NS,
                "To"
            )
        )

        to_node.text = self.endpoint

        to_id = self.generate_id(
            "id-to"
        )

        to_node.set(
            self.qname(
                self.WSU_NS,
                "Id"
            ),
            to_id
        )

        # =====================================================
        # MESSAGE ID
        # =====================================================

        message_id = etree.SubElement(
            header,
            self.qname(
                self.WSA_NS,
                "MessageID"
            )
        )

        message_id.text = (
            f"urn:uuid:{uuid.uuid4()}"
        )

        # =====================================================
        # REPLY TO
        # =====================================================

        reply_to = etree.SubElement(
            header,
            self.qname(
                self.WSA_NS,
                "ReplyTo"
            )
        )

        address = etree.SubElement(
            reply_to,
            self.qname(
                self.WSA_NS,
                "Address"
            )
        )

        address.text = (
            "http://www.w3.org/2005/08/"
            "addressing/anonymous"
        )

        # =====================================================
        # SECURITY
        # =====================================================

        security = etree.SubElement(
            header,
            self.qname(
                self.WSSE_NS,
                "Security"
            )
        )
        security.set(
            self.qname(
                self.SOAP_NS,
                "mustUnderstand"
            ),
            "1"
        )

        # =====================================================
        # TIMESTAMP
        # =====================================================

        timestamp = etree.SubElement(
            security,
            self.qname(
                self.WSU_NS,
                "Timestamp"
            )
        )

        timestamp_id = self.generate_id(
            "TS"
        )

        timestamp.set(
            self.qname(
                self.WSU_NS,
                "Id"
            ),
            timestamp_id
        )

        created = etree.SubElement(
            timestamp,
            self.qname(
                self.WSU_NS,
                "Created"
            )
        )

        expires = etree.SubElement(
            timestamp,
            self.qname(
                self.WSU_NS,
                "Expires"
            )
        )

        now = self.now_utc()

        created.text = (
            now.strftime(
                "%Y-%m-%dT%H:%M:%S.%f"
            )[:-3]
            + "Z"
        )

        expires.text = (
            (
                now +
                timedelta(minutes=5)
            ).strftime(
                "%Y-%m-%dT%H:%M:%S.%f"
            )[:-3]
            + "Z"
        )

        # =====================================================
        # BINARY SECURITY TOKEN
        # =====================================================

        token_id = self.generate_id(
            "X509"
        )

        cert_der = self.certificate.public_bytes(
            Encoding.DER
        )

        cert_b64 = base64.b64encode(
            cert_der
        ).decode()

        binary_token = etree.SubElement(
            security,
            self.qname(
                self.WSSE_NS,
                "BinarySecurityToken"
            )
        )

        binary_token.text = cert_b64

        binary_token.set(
            self.qname(
                self.WSU_NS,
                "Id"
            ),
            token_id
        )

        binary_token.set(
            "EncodingType",
            (
                "http://docs.oasis-open.org/"
                "wss/2004/01/"
                "oasis-200401-wss-soap-message-"
                "security-1.0#Base64Binary"
            )
        )

        binary_token.set(
            "ValueType",
            (
                "http://docs.oasis-open.org/"
                "wss/2004/01/"
                "oasis-200401-wss-x509-token-"
                "profile-1.0#X509v3"
            )
        )

        # =====================================================
        # SIGNATURE
        # =====================================================

        signature = etree.SubElement(
            security,
            self.qname(
                self.DS_NS,
                "Signature"
            )
        )

        signed_info = etree.SubElement(
            signature,
            self.qname(
                self.DS_NS,
                "SignedInfo"
            )
        )

        canonicalization_method = etree.SubElement(
            signed_info,
            self.qname(
                self.DS_NS,
                "CanonicalizationMethod"
            )
        )

        canonicalization_method.set(
            "Algorithm",
            "http://www.w3.org/2001/10/xml-exc-c14n#"
        )

        signature_method = etree.SubElement(
            signed_info,
            self.qname(
                self.DS_NS,
                "SignatureMethod"
            )
        )

        signature_method.set(
            "Algorithm",
            (
                "http://www.w3.org/2001/04/"
                "xmldsig-more#rsa-sha256"
            )
        )

        # El servicio WCF de DIAN para nomina ha aceptado el perfil de SoapUI
        # del anexo firmando wsa:To. Firmar Body/Timestamp puede provocar
        # a:InvalidSecurity en SendTestSetAsync aunque el XML de nomina sea
        # correcto, por eso mantenemos el perfil minimo compatible.
        refs = [
            ("wsa:To", to_node),
        ]
        self._validate_ws_security_refs(refs)

        for _label, node in refs:

            self.add_reference(
                signed_info,
                node
            )

        signed_info_c14n = (
            self.canonicalize(
                signed_info
            )
        )

        signature_value = etree.SubElement(
            signature,
            self.qname(
                self.DS_NS,
                "SignatureValue"
            )
        )

        signature_value.text = (
            self.sign_binary(
                signed_info_c14n
            )
        )

        # =====================================================
        # KEY INFO
        # =====================================================

        key_info = etree.SubElement(
            signature,
            self.qname(
                self.DS_NS,
                "KeyInfo"
            )
        )

        security_token_reference = etree.SubElement(
            key_info,
            self.qname(
                self.WSSE_NS,
                "SecurityTokenReference"
            )
        )

        token_reference = etree.SubElement(
            security_token_reference,
            self.qname(
                self.WSSE_NS,
                "Reference"
            )
        )

        token_reference.set("URI", f"#{token_id}")
        token_reference.set(
            "ValueType",
            (
                "http://docs.oasis-open.org/"
                "wss/2004/01/"
                "oasis-200401-wss-x509-token-"
                "profile-1.0#X509v3"
            )
        )

        return envelope

    # =========================================================
    # REFERENCES
    # =========================================================

    def _validate_ws_security_refs(
        self,
        refs
    ):

        ids = []
        for label, node in refs:
            node_id = node.get(
                self.qname(
                    self.WSU_NS,
                    "Id"
                )
            )
            if not node_id:
                raise DianSoapError(
                    "Firma SOAP DIAN incompleta: falta wsu:Id en %(label)s."
                    % {"label": label},
                    detail={"label": label},
                )
            ids.append(node_id)

        if len(ids) != len(set(ids)):
            raise DianSoapError(
                "Firma SOAP DIAN invalida: referencias WS-Security duplicadas.",
                detail={"references": ids},
            )

    def add_reference(
        self,
        signed_info,
        node
    ):

        reference = etree.SubElement(
            signed_info,
            self.qname(
                self.DS_NS,
                "Reference"
            )
        )

        uri = node.get(
            self.qname(
                self.WSU_NS,
                "Id"
            )
        )

        reference.set(
            "URI",
            f"#{uri}"
        )

        transforms = etree.SubElement(
            reference,
            self.qname(
                self.DS_NS,
                "Transforms"
            )
        )

        transform = etree.SubElement(
            transforms,
            self.qname(
                self.DS_NS,
                "Transform"
            )
        )

        transform.set(
            "Algorithm",
            "http://www.w3.org/2001/10/xml-exc-c14n#"
        )

        digest_method = etree.SubElement(
            reference,
            self.qname(
                self.DS_NS,
                "DigestMethod"
            )
        )

        digest_method.set(
            "Algorithm",
            "http://www.w3.org/2001/04/xmlenc#sha256"
        )

        digest_value = etree.SubElement(
            reference,
            self.qname(
                self.DS_NS,
                "DigestValue"
            )
        )

        digest_value.text = (
            self.sha256_digest(
                self.canonicalize(
                    node
                )
            )
        )

    # =========================================================
    # HTTP SEND
    # =========================================================

    def send(
        self,
        operation,
        envelope
    ):

        xml_data = etree.tostring(
            envelope,
            pretty_print=False,
            xml_declaration=True,
            encoding="utf-8"
        )

        action = self.ACTIONS.get(operation, "")
        headers = {
            "Content-Type": (
                f'application/soap+xml;charset=UTF-8;'
                f'action="{action}"'
            ),
            "SOAPAction": f'"{action}"',
        }

        _logger.info(
            "DIAN REQUEST:\n%s",
            xml_data.decode()
        )

        response = self.session.post(
            self.endpoint,
            data=xml_data,
            headers=headers,
            timeout=self.timeout,
            verify=self.verify_ssl,
        )

        _logger.info(
            "DIAN RESPONSE:\n%s",
            response.text
        )

        return self.parse_response(
            response,
            xml_data
        )

    # =========================================================
    # OPERACIONES
    # =========================================================

    def send_test_set_async(
        self,
        zip_name,
        zip_b64,
        test_set_id
    ):

        body = etree.Element(
            self.qname(
                self.DIAN_NS,
                "SendTestSetAsync"
            )
        )

        etree.SubElement(body, self.qname(self.DIAN_NS, "fileName")).text = zip_name

        etree.SubElement(body, self.qname(self.DIAN_NS, "contentFile")).text = zip_b64

        etree.SubElement(body, self.qname(self.DIAN_NS, "testSetId")).text = test_set_id

        envelope = self.build_envelope(
            "SendTestSetAsync",
            body
        )

        return self.send(
            "SendTestSetAsync",
            envelope
        )

    def send_nomina_sync(
        self,
        zip_b64,
        zip_name=None,
    ):

        body = etree.Element(
            self.qname(
                self.DIAN_NS,
                "SendNominaSync"
            )
        )

        etree.SubElement(body, self.qname(self.DIAN_NS, "contentFile")).text = zip_b64

        envelope = self.build_envelope(
            "SendNominaSync",
            body
        )

        return self.send(
            "SendNominaSync",
            envelope
        )

    def get_status_zip(
        self,
        track_id
    ):

        body = etree.Element(
            self.qname(
                self.DIAN_NS,
                "GetStatusZip"
            )
        )

        etree.SubElement(body, self.qname(self.DIAN_NS, "trackId")).text = track_id

        envelope = self.build_envelope(
            "GetStatusZip",
            body
        )

        return self.send(
            "GetStatusZip",
            envelope
        )

    def get_status(self, cune):
        """Consulta el documento individual usando su CUNE.

        DIAN diferencia esta operación de GetStatusZip: el segundo recibe el
        ZipKey entregado por SendTestSetAsync, mientras que GetStatus recibe
        el CUNE del documento.
        """
        body = etree.Element(self.qname(self.DIAN_NS, "GetStatus"))
        etree.SubElement(body, self.qname(self.DIAN_NS, "trackId")).text = cune
        envelope = self.build_envelope("GetStatus", body)
        return self.send("GetStatus", envelope)

    # =========================================================
    # RESPONSE PARSER
    # =========================================================

    def parse_response(
        self,
        response,
        request_xml=None
    ):

        result = {
            "success": False,
            "http_code": response.status_code,
            "request_xml":
                request_xml.decode()
                if request_xml
                else None,
            "response_xml": response.text,
        }

        try:

            root = etree.fromstring(
                response.content
            )

        except Exception as e:

            result["error"] = (
                f"HTTP {response.status_code}"
                if response.status_code != 200
                else f"XML Parse Error: {str(e)}"
            )

            return result

        # =====================================================
        # SOAP FAULT
        # =====================================================

        fault = root.find(
            ".//soap:Fault",
            namespaces=self.NSMAP
        )

        if fault is not None:

            fault_values = fault.findall(
                ".//soap:Value",
                namespaces=self.NSMAP
            )
            fault_subcode = (
                fault_values[-1].text.strip()
                if fault_values and fault_values[-1].text
                else ""
            )
            fault_reason = fault.find(
                ".//soap:Reason/soap:Text",
                namespaces=self.NSMAP
            )
            fault_reason_text = (
                fault_reason.text.strip()
                if fault_reason is not None and fault_reason.text
                else ""
            )

            result["error"] = (
                f"SOAP Fault {fault_subcode}: {fault_reason_text}".strip()
            )
            result["fault_subcode"] = fault_subcode
            result["fault_reason"] = fault_reason_text

            result["fault_xml"] = (
                etree.tostring(
                    fault,
                    pretty_print=True
                ).decode()
            )

            return result

        if response.status_code != 200:

            result["error"] = (
                f"HTTP {response.status_code}"
            )

            return result

        def _node_text(xpath):
            node = root.find(xpath)
            return (node.text or "").strip() if node is not None and node.text else ""

        def _bool_text(value):
            return str(value or "").strip().lower() in {"true", "1", "yes"}

        def _extract_status_payload(node):
            payload = {}
            mappings = {
                "ZipKey": ".//{*}ZipKey",
                "XmlDocumentKey": ".//{*}XmlDocumentKey",
                "XmlBase64Bytes": ".//{*}XmlBase64Bytes",
                "XmlBytes": ".//{*}XmlBytes",
                "StatusCode": ".//{*}StatusCode",
                "StatusDescription": ".//{*}StatusDescription",
                "StatusMessage": ".//{*}StatusMessage",
                "ErrorMessage": ".//{*}ErrorMessage",
            }
            for key, xpath in mappings.items():
                value = node.find(xpath)
                if value is not None and value.text:
                    payload[key] = value.text.strip()
            is_valid = node.find(".//{*}IsValid")
            if is_valid is not None and is_valid.text:
                payload["IsValid"] = _bool_text(is_valid.text)
            error_items = []
            for error_node in node.findall(".//{*}ErrorMessage//{*}string"):
                if error_node.text and error_node.text.strip():
                    error_items.append(error_node.text.strip())
            if error_items:
                payload["ErrorMessageList"] = error_items
            return payload

        dian_items = []
        for candidate in root.findall(".//{*}DianResponse"):
            payload = _extract_status_payload(candidate)
            if payload:
                dian_items.append(payload)
        if dian_items:
            result["DianResponse"] = dian_items

        # =====================================================
        # TOP-LEVEL FIELDS
        # =====================================================

        zip_key = _node_text(".//{*}ZipKey")
        if zip_key:
            result["track_id"] = zip_key
            result["ZipKey"] = zip_key

        xml_document_key = _node_text(".//{*}XmlDocumentKey")
        if xml_document_key:
            result["XmlDocumentKey"] = xml_document_key

        xml_base64_bytes = _node_text(".//{*}XmlBase64Bytes")
        if xml_base64_bytes:
            result["XmlBase64Bytes"] = xml_base64_bytes

        xml_bytes = _node_text(".//{*}XmlBytes")
        if xml_bytes:
            result["XmlBytes"] = xml_bytes

        status_code = _node_text(".//{*}StatusCode")
        if status_code:
            result["status_code"] = status_code
            result["StatusCode"] = status_code

        status_description = _node_text(".//{*}StatusDescription")
        if status_description:
            result["status_description"] = status_description
            result["StatusDescription"] = status_description

        status_message = _node_text(".//{*}StatusMessage")
        if status_message:
            result["status_message"] = status_message
            result["StatusMessage"] = status_message

        error_message = _node_text(".//{*}ErrorMessage")
        if error_message:
            result["ErrorMessage"] = error_message
        error_items = []
        for error_node in root.findall(".//{*}ErrorMessage//{*}string"):
            if error_node.text and error_node.text.strip():
                error_items.append(error_node.text.strip())
        if error_items:
            result["ErrorMessageList"] = error_items

        is_valid_text = _node_text(".//{*}IsValid")
        if is_valid_text:
            result["IsValid"] = _bool_text(is_valid_text)

        result["success"] = True

        return result


class DianSoapClient(DianSOAPClient):
    HAB_WSDL = "https://vpfe-hab.dian.gov.co/WcfDianCustomerServices.svc?wsdl"
    PROD_WSDL = "https://vpfe.dian.gov.co/WcfDianCustomerServices.svc?wsdl"

    def __init__(
        self,
        wsdl_or_environment,
        timeout=90,
        certificate_data=None,
        certificate_password=None,
        pem_certificate=None,
        pem_key=None,
        verify_ssl=True,
        p12_bytes=None,
        p12_password=None,
        **_kwargs,
    ):
        self.environment = str(wsdl_or_environment or "2")
        wsdl_url = self._resolve_wsdl(wsdl_or_environment)
        certificate_bytes = certificate_data or p12_bytes
        password = certificate_password or p12_password or ""
        self._co_connection_meta = {
            "wsdl": wsdl_url,
            "timeout": timeout,
            "verify_ssl": verify_ssl,
        }
        if pem_certificate and pem_key:
            self.wsdl_url = wsdl_url
            self.endpoint = wsdl_url.replace("?wsdl", "")
            self.timeout = timeout
            self.verify_ssl = verify_ssl
            self.session = requests.Session()
            self.private_key = None
            self.certificate = None
            try:
                self._load_pem_certificate(
                    pem_certificate,
                    pem_key,
                    password=password,
                )
            except Exception as exc:
                raise DianSoapError(
                    f"No fue posible cargar el material PEM para SOAP DIAN: {exc}",
                    detail={"source": "pem", "wsdl": wsdl_url},
                )
        elif certificate_bytes:
            super().__init__(
                wsdl_url=wsdl_url,
                p12_bytes=certificate_bytes,
                p12_password=password,
                timeout=timeout,
                verify_ssl=verify_ssl,
            )
        else:
            self.wsdl_url = wsdl_url
            self.endpoint = wsdl_url.replace("?wsdl", "")
            self.timeout = timeout
            self.verify_ssl = verify_ssl
            self.session = requests.Session()
            self.private_key = None
            self.certificate = None

    def _resolve_wsdl(self, wsdl_or_environment):
        value = str(wsdl_or_environment or "").strip()
        if value.lower().startswith("http"):
            return value
        return self.HAB_WSDL if value == "2" else self.PROD_WSDL

    def connection_diagnostics(self):
        operations = sorted(self.ACTIONS.keys())
        return {
            "wsdl": self.wsdl_url,
            "timeout": self.timeout,
            "operations": operations,
        }

    def _require_certificate(self):
        if not self.private_key or not self.certificate:
            raise DianSoapError(
                f"No fue posible cargar el WSDL DIAN {self.wsdl_url}: falta certificado para autenticar.",
                detail=self.connection_diagnostics(),
            )

    def send_test_set_async(self, zip_name, zip_bytes, test_set_id):
        self._require_certificate()
        if isinstance(zip_bytes, (bytes, bytearray)):
            zip_b64 = base64.b64encode(zip_bytes).decode()
        else:
            zip_b64 = zip_bytes
        try:
            return super().send_test_set_async(zip_name, zip_b64, test_set_id)
        except Exception as exc:
            raise DianSoapError(
                f"Error SOAP DIAN en SendTestSetAsync contra {self.wsdl_url}: {exc}",
                detail={"operation": "SendTestSetAsync", "wsdl": self.wsdl_url},
            ) from exc

    def send_nomina_sync(self, zip_bytes, zip_name=None):
        self._require_certificate()
        if isinstance(zip_bytes, (bytes, bytearray)):
            zip_b64 = base64.b64encode(zip_bytes).decode()
        else:
            zip_b64 = zip_bytes
        try:
            return super().send_nomina_sync(zip_b64, zip_name=zip_name)
        except Exception as exc:
            raise DianSoapError(
                f"Error SOAP DIAN en SendNominaSync contra {self.wsdl_url}: {exc}",
                detail={"operation": "SendNominaSync", "wsdl": self.wsdl_url},
            ) from exc

    def get_status_zip(self, track_id):
        self._require_certificate()
        try:
            return super().get_status_zip(track_id)
        except Exception as exc:
            raise DianSoapError(
                f"Error SOAP DIAN en GetStatusZip contra {self.wsdl_url}: {exc}",
                detail={"operation": "GetStatusZip", "wsdl": self.wsdl_url, "track_id": track_id},
            ) from exc

    def get_status(self, cune):
        self._require_certificate()
        try:
            return super().get_status(cune)
        except Exception as exc:
            raise DianSoapError(
                f"Error SOAP DIAN en GetStatus contra {self.wsdl_url}: {exc}",
                detail={"operation": "GetStatus", "wsdl": self.wsdl_url, "cune": cune},
            ) from exc

    def get_xml_by_document_key(self, document_key):
        self._require_certificate()
        body = etree.Element(self.qname(self.DIAN_NS, "GetXmlByDocumentKey"))
        etree.SubElement(body, self.qname(self.DIAN_NS, "trackId")).text = document_key
        envelope = self.build_envelope("GetXmlByDocumentKey", body)
        try:
            return self.send("GetXmlByDocumentKey", envelope)
        except Exception as exc:
            raise DianSoapError(
                f"Error SOAP DIAN en GetXmlByDocumentKey contra {self.wsdl_url}: {exc}",
                detail={"operation": "GetXmlByDocumentKey", "wsdl": self.wsdl_url, "document_key": document_key},
            ) from exc


def serialize_response(response):
    if isinstance(response, dict):
        return response
    if hasattr(response, "json"):
        try:
            return response.json()
        except Exception:
            pass
    return {"result": response}
