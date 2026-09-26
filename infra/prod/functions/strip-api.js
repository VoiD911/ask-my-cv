function handler(event) {
  var request = event.request;
  var method = request.method;
  // Rejeter les méthodes non prises en charge avant la réécriture /api/ -> /.
  if (method !== 'GET' && method !== 'HEAD' && method !== 'POST') {
    return {
      statusCode: 405,
      statusDescription: 'Method Not Allowed'
    };
  }
  if (request.uri.indexOf('/api/') === 0) {
    request.uri = request.uri.substring(4);
  }
  return request;
}
