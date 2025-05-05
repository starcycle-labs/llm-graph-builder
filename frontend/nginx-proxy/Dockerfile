# Use the official NGINX image from Docker Hub
FROM nginx:alpine

# Install dependencies for OAuth2 Proxy
RUN apk add --no-cache curl && \
    curl -L https://github.com/oauth2-proxy/oauth2-proxy/releases/download/v7.2.0/oauth2-proxy-v7.2.0.linux-amd64.tar.gz | tar zx && \
    mv oauth2-proxy-v7.2.0.linux-amd64/oauth2-proxy /usr/local/bin/ && \
    rm -rf oauth2-proxy-v7.2.0.linux-amd64

# Copy the nginx configuration file
COPY default.conf /etc/nginx/conf.d/default.conf

# Copy OAuth2 Proxy configuration
COPY oauth2-proxy.cfg /etc/oauth2-proxy.cfg

# Start NGINX and OAuth2 Proxy
CMD ["sh", "-c", "oauth2-proxy --config /etc/oauth2-proxy.cfg & nginx -g 'daemon off;'"]
