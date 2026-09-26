// Requête visiteur du comportement par défaut (bucket S3 du site, export statique Next.js
// avec trailingSlash: true → chaque route est un dossier contenant index.html).
// S3 via OAC ne résout pas l'index des sous-dossiers : on réécrit l'URI ici.
//   /           → /index.html
//   /x/         → /x/index.html
//   /x          → /x/index.html (réécriture interne, pas de redirection : la chaîne de
//                 requête reste intacte et le routeur Next normalise l'URL côté client)
//   /x/app.js   → inchangé (dernier segment avec une extension)
function handler(event) {
  var request = event.request;
  var method = request.method;
  if (method !== 'GET' && method !== 'HEAD') {
    return {
      statusCode: 405,
      statusDescription: 'Method Not Allowed',
      headers: { allow: { value: 'GET, HEAD' } }
    };
  }
  var uri = request.uri;
  if (uri.charAt(uri.length - 1) === '/') {
    request.uri = uri + 'index.html';
  } else {
    var last = uri.substring(uri.lastIndexOf('/') + 1);
    if (last.indexOf('.') === -1) {
      request.uri = uri + '/index.html';
    }
  }
  return request;
}
