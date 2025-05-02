import multiprocessing

# Gunicorn configuration for production
bind = "0.0.0.0:7401"
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "eventlet"
worker_connections = 1000
timeout = 30
keepalive = 2
max_requests = 1000
max_requests_jitter = 50
graceful_timeout = 30
forwarded_allow_ips = "*"
accesslog = "logs/access.log"
errorlog = "logs/error.log"
loglevel = "info"
capture_output = True
enable_stdio_inheritance = True
reload = False
daemon = False
pidfile = "logs/gunicorn.pid" 