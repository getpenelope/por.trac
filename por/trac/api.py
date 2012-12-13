from xmlrpclib import ServerProxy, Transport


class ProxyTransport(Transport):
    """
    Questo transport copia alcuni header (Cookie)
    dalla richiesta originale, funziona *unicamente* per le situazioni in cui
    il provider xmlrpc e il client utilizano la stessa autenticazione
    """
    def __init__(self, request, use_datetime=0):
        Transport.__init__(self, use_datetime)
        self.orig_request = request


    def send_content(self, connection, request_body):
        if self.orig_request and self.orig_request.headers.get('Cookie'):
            connection.putheader("Content-Type", "text/xml")
            connection.putheader("Content-Length", str(len(request_body)))
            connection.putheader("Cookie", self.orig_request.headers['Cookie'])
            connection.endheaders()
        if request_body:
            connection.send(request_body)


class TracXmlProxy(ServerProxy):
    def __init__(self, application_uri, request=None, **kwargs):
        if not kwargs.get('transport') and request:
            kwargs['transport'] = ProxyTransport(request)
        ServerProxy.__init__(self, '/'.join([application_uri, 'login', 'rpc']), **kwargs)



