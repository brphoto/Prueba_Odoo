"""Firma digital XAdES-EPES para nomina electronica DIAN (modo software propio).

Esta implementacion usa la libreria ``signxml`` para construir la firma. El
motivo es critico: la canonicalizacion C14N de los fragmentos referenciados
(``SignedProperties`` y ``KeyInfo``) debe respetar el contexto de namespaces
heredado del documento. Una implementacion manual basada en
``lxml.etree.tostring(node, method="c14n")`` sobre nodos aislados re-declara
los namespaces de los ancestros sobre el nodo, produciendo un ``DigestValue``
distinto al que recalcula la DIAN. Eso provoca el rechazo con la regla ZE02
("Valor de la Firma invalido"). ``signxml`` implementa correctamente la
canonicalizacion de node-sets de XMLDSig y evita ese problema.

Estrategia de firmado:
  1. Se inserta un placeholder ``<ds:Signature Id="placeholder"/>`` dentro de
     ``ext:ExtensionContent``.
  2. Se firma el DOCUMENTO COMPLETO en modo enveloped. signxml reemplaza el
     placeholder con la firma real en su sitio y calcula todos los digests
     sobre el arbol final consistente.

Perfil DIAN para nomina (Anexo Tecnico Res. 000013 de 2021, seccion 6.2.5):
  - CanonicalizationMethod = C14N 1.0 (xml-c14n-20010315), NO exclusiva, NO c14n11.
  - SignatureMethod = RSA-SHA512; DigestMethod = SHA256.
  - Tres referencias: documento (URI=""), SignedProperties y KeyInfo.
  - Transform enveloped-signature en la referencia del documento.
      - SigningCertificate "legacy" (NO SigningCertificateV2) con CertDigest SHA256.
      - Cadena completa de certificados en orden hoja -> intermedia -> raiz.
  - SignaturePolicyIdentifier apuntando a la politica de firma v2 de la DIAN.
  - SignerRole/ClaimedRole = "supplier".
"""

import base64
import datetime
import uuid
import warnings
from copy import deepcopy
from io import BytesIO

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    load_pem_private_key,
)
from cryptography.hazmat.primitives.serialization.pkcs12 import load_key_and_certificates
from lxml import etree

from signxml import CanonicalizationMethod, DigestAlgorithm, SignatureMethod
from signxml.algorithms import DigestAlgorithm as _DigestAlgorithm
from signxml.xades import (
    XAdESSignaturePolicy,
    XAdESSigner,
)
from signxml.xades.xades import ds_tag, xades_tag
from signxml.util import add_pem_header, strip_pem_header


DS_NS = "http://www.w3.org/2000/09/xmldsig#"
XADES_NS = "http://uri.etsi.org/01903/v1.3.2#"
EXT_NS = "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2"

DIAN_C14N = "http://www.w3.org/TR/2001/REC-xml-c14n-20010315"
DIAN_RSA_SHA256 = "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"
DIAN_ENVELOPED_SIGNATURE = "http://www.w3.org/2000/09/xmldsig#enveloped-signature"
DIAN_DIGEST = "http://www.w3.org/2001/04/xmlenc#sha256"
DIAN_POLICY_DIGEST_METHOD = "http://www.w3.org/2001/04/xmlenc#sha256"
DIAN_SIGNED_PROPERTIES_TYPE = "http://uri.etsi.org/01903#SignedProperties"

DIAN_POLICY_ID = "https://facturaelectronica.dian.gov.co/politicadefirma/v2/politicadefirmav2.pdf"
DIAN_POLICY_DESCRIPTION = "Política de firma para nóminas electrónicas de la República de Colombia."
DIAN_POLICY_DIGEST = "dMoMvtcG5aIzgYo0tIsSQeVJBDnUnfSOfBpxXrmor0Y="

DIAN_CLAIMED_ROLE = "supplier"


def _colombia_signing_time():
    """Hora legal colombiana (UTC-5), sin fracciones para el perfil DIAN."""
    return datetime.datetime.now(
        datetime.timezone(datetime.timedelta(hours=-5))
    ).isoformat(timespec="seconds")


def _digest_sha256(value):
    digest = hashes.Hash(hashes.SHA256())
    digest.update(value)
    return base64.b64encode(digest.finalize()).decode()


def _digest_sha512(value):
    digest = hashes.Hash(hashes.SHA512())
    digest.update(value)
    return base64.b64encode(digest.finalize()).decode()


def _integer_to_base64(value):
    raw = value.to_bytes((value.bit_length() + 7) // 8, byteorder="big")
    return base64.b64encode(raw).decode()


def _c14n(node):
    """C14N 1.0 inclusiva, sin comentarios (perfil DIAN)."""
    return etree.tostring(node, method="c14n", exclusive=False, with_comments=False)


class DianXAdESSigner(XAdESSigner):
    """XAdESSigner adaptado al perfil de nomina electronica de la DIAN.

    Diferencias frente al comportamiento por defecto de signxml:
      - SigningTime usa hora legal colombiana (UTC-5), no UTC.
      - Solo emite ``xades:SigningCertificate`` (legacy) con CertDigest SHA256;
        NO emite ``SigningCertificateV2`` ni usa SHA1.
    """

    def add_signing_time(self, signed_signature_properties, sig_root, signing_settings):
        signing_time = etree.SubElement(
            signed_signature_properties,
            xades_tag("SigningTime"),
            nsmap=self.namespaces,
        )
        signing_time.text = _colombia_signing_time()

    def add_signing_certificate(self, signed_signature_properties, sig_root, signing_settings):
        """Emitir SigningCertificate legacy con toda la cadena y CertDigest SHA256."""
        signing_cert = etree.SubElement(
            signed_signature_properties,
            xades_tag("SigningCertificate"),
            nsmap=self.namespaces,
        )
        assert signing_settings.cert_chain is not None
        for cert in signing_settings.cert_chain:
            if isinstance(cert, x509.Certificate):
                loaded_cert = cert
            else:
                loaded_cert = x509.load_pem_x509_certificate(add_pem_header(cert))
            der_encoded_cert = loaded_cert.public_bytes(Encoding.DER)
            cert_digest_bytes = self._get_digest(
                der_encoded_cert, algorithm=_DigestAlgorithm.SHA256
            )

            cert_node = etree.SubElement(signing_cert, xades_tag("Cert"), nsmap=self.namespaces)
            cert_digest = etree.SubElement(cert_node, xades_tag("CertDigest"), nsmap=self.namespaces)
            etree.SubElement(
                cert_digest,
                ds_tag("DigestMethod"),
                nsmap=self.namespaces,
                Algorithm=DIAN_DIGEST,
            )
            digest_value_node = etree.SubElement(cert_digest, ds_tag("DigestValue"), nsmap=self.namespaces)
            digest_value_node.text = base64.b64encode(cert_digest_bytes).decode()

            issuer_serial = etree.SubElement(cert_node, xades_tag("IssuerSerial"), nsmap=self.namespaces)
            issuer_name = etree.SubElement(issuer_serial, ds_tag("X509IssuerName"), nsmap=self.namespaces)
            issuer_name.text = loaded_cert.issuer.rfc4514_string()
            serial_number = etree.SubElement(issuer_serial, ds_tag("X509SerialNumber"), nsmap=self.namespaces)
            serial_number.text = str(loaded_cert.serial_number)

    def _build_xades_ds_object(self, sig_root, signing_settings):
        """Build XAdES object with DIAN example reference order.

        signxml adds the references as document -> SignedProperties -> KeyInfo.
        The DIAN payroll annex examples use document -> KeyInfo -> SignedProperties,
        so we keep signxml's implementation pattern and only swap those two calls.
        """
        ds_object = etree.SubElement(sig_root, ds_tag("Object"), nsmap=self.namespaces)
        sig_root.append(ds_object)
        if "Id" not in sig_root.keys():
            sig_root.set("Id", f"xmldsig-{uuid.uuid4()}")
        signature_id = sig_root.get("Id")

        signed_info = self._find(sig_root, "SignedInfo")
        document_reference = signed_info.find(ds_tag("Reference"))
        if document_reference is not None and document_reference.get("URI", "") == "":
            document_reference.set("Id", f"{signature_id}-ref0")

        key_info = self._find(sig_root, "KeyInfo")
        if "Id" not in key_info.keys():
            key_info.set("Id", f"{signature_id}-keyinfo")

        qualifying_properties = etree.SubElement(
            ds_object,
            xades_tag("QualifyingProperties"),
            nsmap=self.namespaces,
            Target=f"#{sig_root.get('Id')}",
        )
        signed_properties = etree.SubElement(
            qualifying_properties,
            xades_tag("SignedProperties"),
            nsmap=self.namespaces,
            Id=f"{signature_id}-signedprops",
        )
        signed_signature_properties = etree.SubElement(
            signed_properties,
            xades_tag("SignedSignatureProperties"),
            nsmap=self.namespaces,
        )
        for ssp_annotator in self.signed_signature_properties_annotators:
            ssp_annotator(
                signed_signature_properties,
                sig_root=sig_root,
                signing_settings=signing_settings,
            )
        signed_data_object_properties = etree.SubElement(
            signed_properties,
            xades_tag("SignedDataObjectProperties"),
            nsmap=self.namespaces,
        )
        for dop_annotator in self.signed_data_object_properties_annotators:
            dop_annotator(
                signed_data_object_properties,
                sig_root=sig_root,
                signing_settings=signing_settings,
            )

        self._add_reference_to_signed_info_with_optional_transform(sig_root, key_info)
        self._add_reference_to_signed_info_with_optional_transform(
            sig_root,
            signed_properties,
            add_c14n_transform=True,
            Type=DIAN_SIGNED_PROPERTIES_TYPE,
        )

    def _add_reference_to_signed_info_with_optional_transform(
        self,
        sig_root,
        node_to_reference,
        add_c14n_transform=False,
        **attrs,
    ):
        signed_info = self._find(sig_root, "SignedInfo")
        reference = etree.SubElement(signed_info, ds_tag("Reference"), nsmap=self.namespaces)
        reference.set("URI", f"#{node_to_reference.get('Id')}")
        for attr_name, attr_value in attrs.items():
            reference.set(attr_name, attr_value)
        if add_c14n_transform:
            transforms = etree.SubElement(reference, ds_tag("Transforms"), nsmap=self.namespaces)
            etree.SubElement(
                transforms,
                ds_tag("Transform"),
                nsmap=self.namespaces,
                Algorithm=DIAN_C14N,
            )
        etree.SubElement(reference, ds_tag("DigestMethod"), nsmap=self.namespaces, Algorithm=DIAN_DIGEST)
        digest_value_node = etree.SubElement(reference, ds_tag("DigestValue"), nsmap=self.namespaces)
        node_to_reference_c14n = self._c14n(node_to_reference, algorithm=self.c14n_alg)
        digest = self._get_digest(node_to_reference_c14n, algorithm=self.digest_alg)
        digest_value_node.text = base64.b64encode(digest).decode()


def _sort_cert_chain(cert_chain):
    """Ordenar certificados como hoja -> intermedios -> raiz."""
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


def _find_extension_content(root):
    return root.find(
        ".//{urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2}ExtensionContent"
    )


def _remove_existing_signature(root):
    for signature in root.findall(".//{http://www.w3.org/2000/09/xmldsig#}Signature"):
        parent = signature.getparent()
        if parent is not None:
            parent.remove(signature)


def _build_signature(root, private_key, cert_chain):
    """Firmar ``root`` y devolver el elemento raiz del documento firmado.

    Inserta un placeholder de firma dentro de ``ext:ExtensionContent`` y firma el
    documento completo en modo enveloped; signxml reemplaza el placeholder con la
    firma real en su sitio.
    """
    extension_content = _find_extension_content(root)
    if extension_content is None:
        raise ValueError("El XML no tiene contenedor ext:ExtensionContent para la firma DIAN.")

    # No debe quedar ninguna firma previa.
    _remove_existing_signature(root)

    # Placeholder: signxml lo reemplaza con la firma real, dentro de ExtensionContent.
    placeholder = etree.SubElement(extension_content, f"{{{DS_NS}}}Signature")
    placeholder.set("Id", "placeholder")

    signer = DianXAdESSigner(
        signature_policy=XAdESSignaturePolicy(
            Identifier=DIAN_POLICY_ID,
            Description=DIAN_POLICY_DESCRIPTION,
            DigestMethod=DigestAlgorithm.SHA256,
            DigestValue=DIAN_POLICY_DIGEST,
        ),
        claimed_roles=[DIAN_CLAIMED_ROLE],
        # Parametros reenviados al XMLSigner subyacente:
        signature_algorithm=SignatureMethod.RSA_SHA256,
        digest_algorithm=DigestAlgorithm.SHA256,
        # CRITICO: la DIAN exige C14N 1.0, NO la 1.1 que signxml usa por defecto.
        c14n_algorithm=CanonicalizationMethod.CANONICAL_XML_1_0,
    )
    signer.signed_data_object_properties_annotators = []

    certificate = cert_chain[0]
    cert_pem_chain = [cert.public_bytes(Encoding.PEM).decode() for cert in cert_chain]

    # KeyInfo alineado con el XML aceptado por DIAN: certificado del firmante y
    # RSAKeyValue. Se construye ANTES de firmar porque KeyInfo va referenciado.
    key_info = etree.Element(f"{{{DS_NS}}}KeyInfo", nsmap={"ds": DS_NS})
    x509_data = etree.SubElement(key_info, f"{{{DS_NS}}}X509Data")
    for cert in cert_chain:
        x509_certificate = etree.SubElement(x509_data, f"{{{DS_NS}}}X509Certificate")
        x509_certificate.text = strip_pem_header(cert.public_bytes(Encoding.PEM))
    key_value = etree.SubElement(key_info, f"{{{DS_NS}}}KeyValue")
    rsa_key_value = etree.SubElement(key_value, f"{{{DS_NS}}}RSAKeyValue")
    public_numbers = certificate.public_key().public_numbers()
    etree.SubElement(rsa_key_value, f"{{{DS_NS}}}Modulus").text = _integer_to_base64(public_numbers.n)
    etree.SubElement(rsa_key_value, f"{{{DS_NS}}}Exponent").text = _integer_to_base64(public_numbers.e)

    # Firmar el documento completo. Con el placeholder presente, signxml deriva la
    # referencia del documento (URI="") automaticamente y rellena el placeholder.
    #
    # exclude_c14n_transform_element=True: el anexo DIAN (DC07) exige que la
    # referencia del documento tenga UNICAMENTE el transform enveloped-signature.
    # Por defecto signxml agrega un segundo transform de canonicalizacion C14N,
    # que el validador de la DIAN rechaza (regla SIGNPLGNS: "No se pudo validar
    # firma").
    signed_root = signer.sign(
        root,
        key=private_key,
        cert=cert_pem_chain,
        key_info=key_info,
        exclude_c14n_transform_element=True,
    )

    return signed_root


def validate_dian_signature_profile(xml_bytes):
    """Validar el perfil XAdES de nomina DIAN antes de enviarlo.

    Recalcula los DigestValue de cada referencia usando la MISMA canonicalizacion
    que la DIAN (documento completo -> extraccion del subarbol con su contexto de
    namespaces) y verifica el SignatureValue contra el certificado.
    """
    root = etree.parse(BytesIO(xml_bytes)).getroot()
    ds = f"{{{DS_NS}}}"
    xades_ns = f"{{{XADES_NS}}}"
    ns = {"ds": DS_NS, "xades": XADES_NS, "ext": EXT_NS}

    signatures = root.xpath(
        ".//ext:UBLExtension/ext:ExtensionContent/ds:Signature",
        namespaces=ns,
    )
    if len(signatures) != 1:
        raise ValueError(
            "Firma DIAN invalida: debe existir exactamente una firma en "
            "ext:UBLExtension/ext:ExtensionContent."
        )
    signature = signatures[0]
    signed_info = signature.find(f"{ds}SignedInfo")
    if signed_info is None:
        raise ValueError("Firma DIAN invalida: falta ds:SignedInfo.")

    canonicalization = signed_info.find(f"{ds}CanonicalizationMethod")
    signature_method = signed_info.find(f"{ds}SignatureMethod")
    if canonicalization is None or canonicalization.get("Algorithm") != DIAN_C14N:
        raise ValueError("Firma DIAN invalida: CanonicalizationMethod no coincide con el anexo tecnico.")
    if signature_method is None or signature_method.get("Algorithm") != DIAN_RSA_SHA256:
        raise ValueError("Firma DIAN invalida: SignatureMethod debe ser rsa-sha256.")

    references = signed_info.findall(f"{ds}Reference")
    if len(references) != 3:
        raise ValueError("Firma DIAN invalida: SignedInfo debe tener tres referencias.")

    def _reference_kind(reference):
        if reference.get("URI") == "":
            return "documento"
        if reference.get("Type") == DIAN_SIGNED_PROPERTIES_TYPE:
            return "SignedProperties"
        return "KeyInfo"

    reference_order = [_reference_kind(reference) for reference in references]
    expected_order = ["documento", "KeyInfo", "SignedProperties"]
    if reference_order != expected_order:
        raise ValueError(
            "Firma DIAN invalida: el orden de referencias debe ser "
            "%(expected)s; encontrado %(found)s."
            % {
                "expected": " -> ".join(expected_order),
                "found": " -> ".join(reference_order),
            }
        )

    document_ref = references[0]
    transforms = document_ref.findall(f"{ds}Transforms/{ds}Transform")
    # El anexo (DC07) exige EXACTAMENTE un transform: enveloped-signature. Un
    # transform de canonicalizacion adicional dispara el rechazo SIGNPLGNS.
    if len(transforms) != 1 or transforms[0].get("Algorithm") != DIAN_ENVELOPED_SIGNATURE:
        raise ValueError(
            "Firma DIAN invalida: la referencia del documento debe tener un unico "
            "transform enveloped-signature (sin transform de canonicalizacion extra)."
        )
    if not any(r.get("Type") == DIAN_SIGNED_PROPERTIES_TYPE for r in references):
        raise ValueError("Firma DIAN invalida: falta referencia a xades:SignedProperties.")

    if signature.find(f"{ds}KeyInfo/{ds}KeyValue/{ds}RSAKeyValue") is None:
        raise ValueError("Firma DIAN invalida: KeyInfo debe contener ds:RSAKeyValue como el perfil aceptado.")

    if signature.find(f".//{xades_ns}SigningCertificateV2") is not None:
        raise ValueError("Firma DIAN invalida: no use SigningCertificateV2 para este anexo.")
    cert_nodes = signature.findall(f".//{xades_ns}SigningCertificate/{xades_ns}Cert")
    if not cert_nodes:
        raise ValueError(
            "Firma DIAN invalida: falta xades:Cert dentro de xades:SigningCertificate."
        )
    key_info_certs = signature.findall(f"{ds}KeyInfo/{ds}X509Data/{ds}X509Certificate")
    if not key_info_certs:
        raise ValueError("Firma DIAN invalida: ds:KeyInfo debe incluir X509Certificate.")
    for cert_node in cert_nodes:
        method = cert_node.find(f"{xades_ns}CertDigest/{ds}DigestMethod")
        if method is None or method.get("Algorithm") != DIAN_DIGEST:
            raise ValueError("Firma DIAN invalida: CertDigest debe usar sha256.")

    policy_identifier = signature.find(
        f".//{xades_ns}SignaturePolicyId/{xades_ns}SigPolicyId/{xades_ns}Identifier"
    )
    policy_digest_method = signature.find(
        f".//{xades_ns}SignaturePolicyId/{xades_ns}SigPolicyHash/{ds}DigestMethod"
    )
    policy_digest_value = signature.find(
        f".//{xades_ns}SignaturePolicyId/{xades_ns}SigPolicyHash/{ds}DigestValue"
    )
    if policy_identifier is None or (policy_identifier.text or "").strip() != DIAN_POLICY_ID:
        raise ValueError("Firma DIAN invalida: identificador de politica de firma incorrecto.")
    if policy_digest_method is None or policy_digest_method.get("Algorithm") != DIAN_POLICY_DIGEST_METHOD:
        raise ValueError("Firma DIAN invalida: DigestMethod de politica debe ser sha256.")
    if policy_digest_value is None or (policy_digest_value.text or "").strip() != DIAN_POLICY_DIGEST:
        raise ValueError("Firma DIAN invalida: DigestValue de politica no coincide con DIAN.")

    claimed_role = signature.find(
        f".//{xades_ns}SignerRole/{xades_ns}ClaimedRoles/{xades_ns}ClaimedRole"
    )
    if claimed_role is None or (claimed_role.text or "").strip() != DIAN_CLAIMED_ROLE:
        raise ValueError("Firma DIAN invalida: SignerRole/ClaimedRole debe ser 'supplier'.")

    # Verificacion real de cada DigestValue, canonicalizando como lo hace la DIAN:
    # C14N del documento completo y extraccion del subarbol referenciado.
    full_c14n = _c14n(root)
    canonical_tree = etree.fromstring(full_c14n)

    for reference in references:
        digest_value = reference.find(f"{ds}DigestValue")
        digest_method = reference.find(f"{ds}DigestMethod")
        uri = reference.get("URI", "")
        label = uri or "(documento)"
        if digest_method is None or digest_method.get("Algorithm") != DIAN_DIGEST:
            raise ValueError(
                "Firma DIAN invalida: DigestMethod debe ser sha256 para la referencia %(uri)s."
                % {"uri": label}
            )
        expected = _expected_reference_digest(root, canonical_tree, reference)
        if digest_value is None or (digest_value.text or "").strip() != expected:
            raise ValueError(
                "Firma DIAN invalida: DigestValue no coincide para la referencia %(uri)s."
                % {"uri": label}
            )

    signature_value = signature.find(f"{ds}SignatureValue")
    certificate_value = signature.find(f"{ds}KeyInfo/{ds}X509Data/{ds}X509Certificate")
    if signature_value is None or certificate_value is None:
        raise ValueError("Firma DIAN invalida: faltan SignatureValue o X509Certificate.")
    certificate = x509.load_der_x509_certificate(base64.b64decode(certificate_value.text or ""))
    try:
        certificate.public_key().verify(
            base64.b64decode(signature_value.text or ""),
            _c14n(signed_info),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
    except InvalidSignature as exc:
        raise ValueError("Firma DIAN invalida: SignatureValue no verifica localmente.") from exc
    return True


def _expected_reference_digest(live_root, canonical_tree, reference):
    """Digest esperado de una referencia, canonicalizado en contexto de documento."""
    ds = f"{{{DS_NS}}}"
    uri = reference.get("URI", "")
    if uri == "":
        # enveloped-signature: documento completo sin la firma.
        root_copy = deepcopy(live_root)
        _remove_existing_signature(root_copy)
        return _digest_sha256(_c14n(root_copy))
    if uri.startswith("#"):
        target_id = uri[1:]
        nodes = canonical_tree.xpath("//*[@Id=$t]", t=target_id)
        if len(nodes) != 1:
            raise ValueError(f"No fue posible resolver la referencia de firma {uri}.")
        return _digest_sha256(_c14n(nodes[0]))
    raise ValueError(f"Referencia de firma no soportada: {uri}.")


def load_pkcs12(binary_file, password):
    try:
        file_bytes = base64.b64decode(binary_file or b"", validate=True)
    except Exception as exc:
        raise ValueError("El archivo PKCS12 guardado no esta en formato base64 valido.") from exc
    if not file_bytes:
        raise ValueError("El archivo PKCS12 guardado esta vacio.")
    try:
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="PKCS#12 bundle could not be parsed as DER, falling back to parsing as BER.*",
            )
            private_key, certificate, additional_certificates = load_key_and_certificates(
                file_bytes, (password or "").encode("utf-8")
            )
    except Exception as exc:
        raise ValueError(
            "No fue posible abrir el archivo PKCS12. Esto normalmente indica "
            "archivo .p12/.pfx incorrecto, archivo corrupto o clave del certificado incorrecta."
        ) from exc
    if not private_key or not certificate:
        raise ValueError("No fue posible leer la llave privada o el certificado del archivo PKCS12.")
    cert_chain = [certificate]
    if additional_certificates:
        cert_chain.extend(additional_certificates)
    cert_chain = _sort_cert_chain(cert_chain)
    return private_key, cert_chain


def load_pem_material(pem_certificate, pem_key, password=None):
    cert_bytes = base64.b64decode(pem_certificate)
    key_bytes = base64.b64decode(pem_key)
    private_key = None
    encoded_password = (password or "").encode("utf-8") if password else None
    try:
        private_key = load_pem_private_key(
            key_bytes,
            password=encoded_password,
        )
    except TypeError:
        if encoded_password:
            private_key = load_pem_private_key(key_bytes, password=None)
        else:
            raise
    except ValueError as exc:
        if encoded_password and "private key is not encrypted" in str(exc).lower():
            private_key = load_pem_private_key(key_bytes, password=None)
        else:
            raise
    certificate = x509.load_pem_x509_certificate(cert_bytes)
    return private_key, [certificate]


def load_signing_material(binary_file=None, password=None, pem_certificate=None, pem_key=None):
    if pem_certificate and pem_key:
        return load_pem_material(pem_certificate, pem_key, password=password)
    return load_pkcs12(binary_file, password)


def sign_xml(xml_bytes, binary_file=None, password=None, pem_certificate=None, pem_key=None):
    private_key, cert_chain = load_signing_material(
        binary_file=binary_file,
        password=password,
        pem_certificate=pem_certificate,
        pem_key=pem_key,
    )
    root = etree.parse(BytesIO(xml_bytes)).getroot()
    signed_root = _build_signature(root, private_key, cert_chain)
    signed_xml = etree.tostring(
        signed_root,
        encoding="UTF-8",
        xml_declaration=True,
        # No reformatear despues de firmar: cambios de espacios invalidan XMLDSig.
        pretty_print=False,
    )
    # lxml emite comillas simples en la declaracion XML; DIAN (.NET) puede
    # rechazarlas con NIE901.  Reemplazar SOLO la declaracion, que esta FUERA
    # del contenido firmado (XMLDSig no cubre la declaracion XML).
    signed_xml = signed_xml.replace(
        b"<?xml version='1.0' encoding='UTF-8'?>",
        b'<?xml version="1.0" encoding="UTF-8"?>',
        1,
    )
    validate_dian_signature_profile(signed_xml)
    return signed_xml
