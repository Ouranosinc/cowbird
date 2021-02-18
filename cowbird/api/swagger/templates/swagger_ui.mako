<!DOCTYPE html>
<head>
    <meta charset="UTF-8">
    <title>${api_title}</title>
    <link rel="stylesheet" type="text/css" href="https://unpkg.com/swagger-ui-dist@3.17.5/swagger-ui.css">
    <script src="https://unpkg.com/swagger-ui-dist@3.17.5/swagger-ui-standalone-preset.js"></script>
    <script src="https://unpkg.com/swagger-ui-dist@3.17.5/swagger-ui-bundle.js"></script>
    <script>
        addEventListener('DOMContentLoaded', function() {
            var api_urls = [
                { url: "${api_schema_path}", name: 'latest' },
                // disable other versions, only use latest
            ];
            window.ui = SwaggerUIBundle({
                url: "${api_schema_path}",
                urls: api_urls,
                dom_id: '#swagger-ui',
                deepLinking: true,
                docExpansion: 'none',
                presets: [
                    SwaggerUIBundle.presets.apis,
                    SwaggerUIStandalonePreset
                ],
                plugins: [
                    SwaggerUIBundle.plugins.DownloadUrl
                ],
                layout: "StandaloneLayout",
                validatorUrl: null,     // disable validator error messages not finding local routes
                tagsSorter: 'alpha',
                apisSorter : "alpha",
                operationsSorter: "alpha",
            });
        });
    </script>
</head>
<body>
<div id="swagger-ui"></div>
</body>
</html>
