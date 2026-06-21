# Deployment Guide

This guide covers deploying Recollect in various environments, from local development to production servers.

## 🚀 Quick Deployment

### Local Development

```bash
# Clone repository
git clone https://github.com/sarox-dev/Recollect.git
cd recollect

# Configure environment
cp .env.example .env
# Edit .env if needed

# Start services
docker compose up -d

# Verify deployment
curl http://localhost:8000
```

### Production Server

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Deploy Recollect
git clone https://github.com/sarox-dev/Recollect.git
cd recollect
cp .env.example .env
# Edit .env for production settings

docker compose up -d

# Setup firewall
sudo ufw allow 8000
sudo ufw enable
```

## ⚙️ Configuration

### Environment Variables

Create `.env` file with production values:

```bash
# App Configuration
APP_PORT=8000

# SearXNG Configuration
SEARXNG_PORT=8080
SEARXNG_BASE_URL=http://searxng_api:8080
SEARXNG_INSTANCE_NAME=Recollect Search
```

### SearXNG Configuration

Customize `searxng/settings.yml`:

```yaml
general:
  debug: false
  instance_name: "Recollect Search"
  privacypolicy_url: false
  contact_url: false

search:
  safe_search: 0
  autocomplete: ""
  default_lang: "auto"

# Configure search engines
engines:
  - name: google
    engine: google
    shortcut: gg
  - name: duckduckgo
    engine: duckduckgo
    shortcut: ddg
```

## 🌐 Web Server Setup

### Nginx Reverse Proxy

```nginx
# /etc/nginx/sites-available/recollect
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

# SSL Configuration (Let's Encrypt)
server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Enable site:
```bash
sudo ln -s /etc/nginx/sites-available/recollect /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### Apache Reverse Proxy

```apache
# /etc/apache2/sites-available/recollect.conf
<VirtualHost *:80>
    ServerName your-domain.com

    ProxyPass / http://localhost:8000/
    ProxyPassReverse / http://localhost:8000/

    <Location />
        Require all granted
    </Location>
</VirtualHost>
```

Enable modules and site:
```bash
sudo a2enmod proxy proxy_http
sudo a2ensite recollect
sudo systemctl reload apache2
```

### SSL Certificate (Let's Encrypt)

```bash
# Install Certbot
sudo apt install certbot python3-certbot-nginx

# Get certificate
sudo certbot --nginx -d your-domain.com

# Auto-renewal
sudo crontab -e
# Add: 0 12 * * * /usr/bin/certbot renew --quiet
```

## 🐳 Docker Production Setup

### Docker Compose Override

Create `docker-compose.prod.yml`:

```yaml
version: '3.8'

services:
  app:
    environment:
      - ENVIRONMENT=production
    deploy:
      resources:
        limits:
          memory: 512M
        reservations:
          memory: 256M

  searxng:
    environment:
      - SEARXNG_DEBUG=false
    deploy:
      resources:
        limits:
          memory: 1G
        reservations:
          memory: 512M
```

Deploy with production config:
```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

### Docker Swarm

For multi-node deployment:

```bash
# Initialize swarm
docker swarm init

# Deploy stack
docker stack deploy -c docker-compose.yml recollect

# Check services
docker stack services recollect
```

## ☁️ Cloud Deployment

### AWS EC2

```bash
# Launch EC2 instance (t3.micro or t3.small)
# Ubuntu 22.04 LTS

# Security group rules:
# - SSH (22) - Your IP
# - HTTP (80) - 0.0.0.0/0
# - HTTPS (443) - 0.0.0.0/0
# - Custom TCP (8000) - localhost/32 (internal)

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Deploy Recollect
git clone https://github.com/sarox-dev/Recollect.git
cd recollect
docker compose up -d

# Setup domain (Route 53)
# Point A record to EC2 public IP
```

### DigitalOcean Droplet

```bash
# Create Ubuntu droplet (1GB RAM minimum)

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Deploy
git clone https://github.com/sarox-dev/Recollect.git
cd recollect
docker compose up -d

# Setup firewall
sudo ufw allow OpenSSH
sudo ufw allow 80
sudo ufw allow 443
sudo ufw enable
```

### Google Cloud Run

```yaml
# cloudbuild.yaml
steps:
  - name: 'gcr.io/cloud-builders/docker'
    args: ['build', '-t', 'gcr.io/$PROJECT_ID/recollect', '.']

  - name: 'gcr.io/cloud-builders/docker'
    args: ['push', 'gcr.io/$PROJECT_ID/recollect']

  - name: 'gcr.io/google.com/cloudsdktool/cloud-sdk'
    entrypoint: gcloud
    args:
      - run
      - deploy
      - recollect
      - --image=gcr.io/$PROJECT_ID/recollect
      - --platform=managed
      - --port=8000
      - --allow-unauthenticated
```

### Heroku

```yaml
# Dockerfile (modify for Heroku)
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
EXPOSE $PORT

CMD uvicorn app:app --host 0.0.0.0 --port $PORT
```

```yaml
# docker-compose.yml (Heroku)
version: '3.8'

services:
  app:
    build: .
    ports:
      - "$PORT:$PORT"
    environment:
      - SEARXNG_URL=https://searxng.herokuapp.com
```

## 🔧 Maintenance

### Updates

```bash
# Update Recollect
cd recollect
git pull origin main
docker compose build
docker compose up -d

# Update Docker images
docker compose pull
docker compose up -d
```

### Backup

```bash
# Backup SearXNG settings
cp searxng/settings.yml searxng/settings.yml.backup

# Backup environment
cp .env .env.backup
```

### Monitoring

```bash
# Check container health
docker compose ps

# View logs
docker compose logs -f

# Monitor resources
docker stats

# Check SearXNG status
curl http://localhost:8080
```

### Logs

```bash
# Application logs
docker compose logs app

# SearXNG logs
docker compose logs searxng

# System logs
sudo journalctl -u docker
```

## 🔒 Security Hardening

### Network Security

```bash
# Disable unused ports
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
sudo ufw allow 80
sudo ufw allow 443

# Fail2Ban for SSH protection
sudo apt install fail2ban
```

### Container Security

```yaml
# docker-compose.security.yml
services:
  app:
    security_opt:
      - no-new-privileges:true
    read_only: true
    tmpfs:
      - /tmp

  searxng:
    security_opt:
      - no-new-privileges:true
```

### SSL/TLS

```bash
# Force HTTPS redirect
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}
```

## 📊 Performance Tuning

### Resource Limits

```yaml
# docker-compose.perf.yml
services:
  app:
    deploy:
      resources:
        limits:
          cpus: '0.50'
          memory: 512M
        reservations:
          cpus: '0.25'
          memory: 256M

  searxng:
    deploy:
      resources:
        limits:
          cpus: '1.0'
          memory: 1G
        reservations:
          cpus: '0.5'
          memory: 512M
```

### Caching

```yaml
# SearXNG caching
search:
  cache:
    type: redis
    redis_url: redis://redis:6379
```

### Database (Future)

```yaml
# PostgreSQL for search history
services:
  db:
    image: postgres:15
    environment:
      POSTGRES_DB: recollect
      POSTGRES_USER: recollect
      POSTGRES_PASSWORD: secure_password
```

## 🚨 Troubleshooting

### Common Issues

**Port already in use**
```bash
# Find process using port
sudo lsof -i :8000

# Kill process
sudo kill -9 <PID>

# Or change port in .env
APP_PORT=8001
```

**Container fails to start**
```bash
# Check logs
docker compose logs

# Check disk space
df -h

# Restart Docker
sudo systemctl restart docker
```

**Search not working**
```bash
# Test SearXNG directly
curl "http://localhost:8080/search?q=test&format=json"

# Check network connectivity
docker compose exec app ping searxng_api
```

### Health Checks

```bash
# Application health
curl -f http://localhost:8000/ || echo "App unhealthy"

# SearXNG health
curl -f http://localhost:8080/ || echo "SearXNG unhealthy"
```

## 📈 Scaling

### Horizontal Scaling

```yaml
# docker-compose.scale.yml
services:
  app:
    scale: 3
    environment:
      - REDIS_URL=redis://redis:6379

  redis:
    image: redis:7-alpine
```

### Load Balancing

```nginx
upstream recollect_app {
    server localhost:8000;
    server localhost:8001;
    server localhost:8002;
}

server {
    listen 80;
    location / {
        proxy_pass http://recollect_app;
    }
}
```

## 🔄 Backup & Recovery

### Automated Backups

```bash
# Backup script
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
tar -czf backup_$DATE.tar.gz recollect/
# Upload to cloud storage
```

### Disaster Recovery

```bash
# Restore from backup
tar -xzf backup_latest.tar.gz
cd recollect
docker compose up -d
```

## 📞 Support

For deployment issues:
1. Check this guide
2. Review [Troubleshooting](troubleshooting.md)
3. Search existing issues
4. Open new issue with deployment details

---

*Last updated: April 2026*