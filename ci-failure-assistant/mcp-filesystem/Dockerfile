FROM node:24-alpine

RUN npm install --global \
    @modelcontextprotocol/server-filesystem@2.0.0 \
    supergateway@4.2.0 \
    && npm cache clean --force

USER node
EXPOSE 8000

CMD ["supergateway", "--stdio", "mcp-server-filesystem /data", "--outputTransport", "streamableHttp", "--streamableHttpPath", "/mcp", "--port", "8000", "--host", "0.0.0.0", "--healthEndpoint", "/healthz", "--healthCheck", "server", "--tools", "search_files", "--tools", "read_text_file"]
