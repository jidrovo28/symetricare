# xades/FirmaElectronica/invoice.py

class InfoToSignXml:
    def __init__(
        self,
        pathXmlToSign: str,
        pathXmlSigned: str,
        pathSignatureP12: str,
        passwordSignature: str
    ):
        self.pathXmlToSign = pathXmlToSign
        self.pathXmlSigned = pathXmlSigned
        self.pathSignatureP12 = pathSignatureP12
        self.passwordSignature = passwordSignature