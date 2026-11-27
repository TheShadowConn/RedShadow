root /usr/share/nginx/html;
index index.html;

location = /healthz {
    access_log off;
    default_type text/plain;
    return 200 "ok\n";
}

# Sign-in, second-step and password endpoints: a second, coarser limit in front of Django's own throttles.
location ~ ^/api/v1/auth/(login|mfa/|password) {
    limit_req zone=authlimit burst=15 nodelay;
    limit_req_status 429;
    set $upstream http://backend:8000;
    proxy_pass $upstream;
    proxy_set_header Host $http_host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Request-ID $request_id;
    proxy_read_timeout 60s;
}

# Backup download and restore upload: large bodies and slow answers.
location /api/v1/system/ {
    limit_req zone=authlimit burst=15 nodelay;
    limit_req_status 429;
    client_max_body_size 2100m;
    proxy_request_buffering off;
    proxy_buffering off;
    set $upstream http://backend:8000;
    proxy_pass $upstream;
    proxy_set_header Host $http_host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Request-ID $request_id;
    proxy_read_timeout 600s;
    proxy_send_timeout 600s;
}

location /api/ {
    set $upstream http://backend:8000;
    proxy_pass $upstream;
    proxy_set_header Host $http_host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Request-ID $request_id;
    proxy_read_timeout 60s;
}

# Files are only reachable through Django: it authorises, then answers with X-Accel-Redirect.
# "internal" makes this location unreachable from outside, so /protected/... typed in a browser is 404.
location /protected/ {
    internal;
    alias /data/media/;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Content-Security-Policy "default-src 'none'; sandbox" always;
    add_header Cache-Control "private, no-store" always;
}

location /assets/ {
    expires 1y;
    try_files $uri =404;
}

location / {
    expires -1;
    try_files $uri /index.html;
}
