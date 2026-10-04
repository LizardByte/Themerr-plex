import SwaggerUI from 'swagger-ui-dist/swagger-ui-bundle.js';
import 'swagger-ui-dist/swagger-ui.css';
import '../css/api_docs.css';

SwaggerUI({
    dom_id: '#swagger-ui',
    url: '/api/openapi.json',
    validatorUrl: null,
    withCredentials: true,
    requestInterceptor(request) {
        request.headers['X-CSRFToken'] = document.querySelector('meta[name="csrf-token"]').content;
        return request;
    },
});
