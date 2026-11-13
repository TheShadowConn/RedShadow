server_tokens off;
# 25 MB file plus multipart overhead; Django enforces the exact limit and answers 413 as JSON.
client_max_body_size 26m;
# Docker's embedded DNS, so backend IP changes after a recreate are picked up.
resolver 127.0.0.11 valid=10s ipv6=off;
