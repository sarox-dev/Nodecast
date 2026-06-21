# Troubleshooting Guide

This guide helps you diagnose and resolve common issues with Recollect deployment and usage.

## 🔍 Quick Diagnosis

### Health Check Script

```bash
#!/bin/bash
echo "=== Recollect Health Check ==="

# Check Docker
echo "Docker status:"
docker --version
docker compose version

# Check containers
echo -e "\nContainer status:"
docker compose ps

# Check ports
echo -e "\nPort status:"
netstat -tlnp | grep -E "(8000|8080)" || echo "Ports not listening"

# Test services
echo -e "\nService tests:"
curl -s -o /dev/null -w "App: %{http_code}\n" http://localhost:8000/ || echo "App: FAILED"
curl -s -o /dev/null -w "SearXNG: %{http_code}\n" http://localhost:8080/ || echo "SearXNG: FAILED"

# Check logs
echo -e "\nRecent errors:"
docker compose logs --tail=5 2>&1 | grep -i error || echo "No recent errors"
```

Run the health check:
```bash
chmod +x health-check.sh
./health-check.sh
```

## 🚨 Common Issues

### 1. Containers Won't Start

**Symptoms:**
- `docker compose up` fails
- Containers exit immediately
- Error: "Container cannot start"

**Solutions:**

Check Docker resources:
```bash
# Check available resources
docker system df

# Check system resources
free -h
df -h

# Clean up Docker
docker system prune -a
```

Check logs:
```bash
docker compose logs
docker compose logs app
docker compose logs searxng
```

Rebuild containers:
```bash
docker compose build --no-cache
docker compose up -d
```

### 2. Port Already in Use

**Symptoms:**
- Error: "Port already in use"
- Cannot access http://localhost:8000

**Solutions:**

Find process using port:
```bash
# Linux/Mac
sudo lsof -i :8000
sudo lsof -i :8080

# Kill process
sudo kill -9 <PID>
```

Change ports in `.env`:
```bash
# Edit .env
APP_PORT=8001
SEARXNG_PORT=8081

# Restart services
docker compose up -d
```

### 3. Search Not Working

**Symptoms:**
- App loads but search returns no results
- Error: "SearXNG service unavailable"

**Solutions:**

Test SearXNG directly:
```bash
# Test SearXNG API
curl "http://localhost:8080/search?q=test&format=json"

# Check SearXNG logs
docker compose logs searxng
```

Test connectivity between containers:
```bash
# From app container
docker compose exec app curl http://searxng_api:8080/search?q=test

# Check network
docker compose exec app ping searxng_api
```

Check SearXNG configuration:
```bash
# View SearXNG settings
cat searxng/settings.yml

# Restart SearXNG
docker compose restart searxng
```

### 4. Slow Performance

**Symptoms:**
- Searches take >10 seconds
- App feels sluggish
- High CPU/memory usage

**Solutions:**

Check resource usage:
```bash
docker stats
```

Optimize SearXNG:
```yaml
# searxng/settings.yml
search:
  cache:
    type: redis
    redis_url: redis://redis:6379
```

Add Redis for caching:
```yaml
# docker-compose.yml
services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
```

### 5. Permission Errors

**Symptoms:**
- "Permission denied" errors
- Cannot write to mounted volumes

**Solutions:**

Fix file permissions:
```bash
# Set correct ownership
sudo chown -R $USER:$USER .

# Fix Docker permissions
sudo usermod -aG docker $USER
newgrp docker
```

Check volume mounts:
```bash
# Verify mount points
docker compose exec app ls -la /app
```

### 6. Database Connection Issues (Future)

**Symptoms:**
- Search history not saving
- "Connection refused" to database

**Solutions:**

Check database status:
```bash
docker compose ps db
docker compose logs db
```

Test connection:
```bash
docker compose exec db psql -U recollect -d recollect
```

Reset database:
```bash
docker compose down -v
docker compose up -d db
```

## 🔧 Advanced Troubleshooting

### Debug Mode

Enable debug logging:

```yaml
# searxng/settings.yml
general:
  debug: true
```

```python
# app/app.py (temporary)
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Network Debugging

Check Docker networks:
```bash
# List networks
docker network ls

# Inspect network
docker network inspect recollect_default

# Test connectivity
docker compose exec app nslookup searxng_api
```

### Log Analysis

Comprehensive log checking:
```bash
# All logs
docker compose logs > all_logs.txt

# Follow logs in real-time
docker compose logs -f

# Filter logs
docker compose logs | grep -i error
docker compose logs | grep -i timeout
```

### Container Inspection

Debug running containers:
```bash
# Enter container
docker compose exec app bash

# Check environment
env | grep -E "(SEARXNG|APP)"

# Test internal connectivity
curl http://searxng_api:8080/search?q=test
```

## 🐛 Specific Error Messages

### "ModuleNotFoundError"

**Error:** `ModuleNotFoundError: No module named 'fastapi'`

**Solution:**
```bash
# Rebuild container
docker compose build --no-cache app
docker compose up -d app
```

### "Connection refused"

**Error:** `Connection refused (searxng_api:8080)`

**Solution:**
```bash
# Check service status
docker compose ps

# Check .env configuration
cat .env | grep SEARXNG_BASE_URL

# Restart services
docker compose restart
```

### "Template not found"

**Error:** `TemplateNotFound: index.html`

**Solution:**
```bash
# Check template location
ls -la app/templates/

# Restart app
docker compose restart app
```

### "Port binding failed"

**Error:** `Port already in use`

**Solution:**
```bash
# Find conflicting service
sudo netstat -tlnp | grep :8000

# Change port in .env
sed -i 's/APP_PORT=8000/APP_PORT=8001/' .env
docker compose up -d
```

## 🔄 Recovery Procedures

### Complete Reset

```bash
# Stop and remove everything
docker compose down -v --remove-orphans

# Clean up Docker
docker system prune -a

# Remove local files
rm -rf searxng/settings.yml.backup

# Fresh start
git checkout .
cp .env.example .env
docker compose up -d
```

### Configuration Reset

```bash
# Backup current config
cp .env .env.backup
cp searxng/settings.yml searxng/settings.yml.backup

# Reset to defaults
cp .env.example .env
git checkout searxng/settings.yml

# Restart
docker compose up -d
```

### Database Reset (Future)

```bash
# Stop services
docker compose stop app

# Reset database
docker compose exec db dropdb recollect
docker compose exec db createdb recollect

# Run migrations
docker compose exec app alembic upgrade head

# Restart
docker compose start app
```

## 📊 Performance Monitoring

### Resource Monitoring

```bash
# Container stats
docker stats

# System resources
htop
iotop

# Network monitoring
sudo nload
```

### Application Metrics

```bash
# Response time testing
curl -w "@curl-format.txt" -o /dev/null -s "http://localhost:8000/search?q=test"

# Load testing
ab -n 100 -c 10 http://localhost:8000/
```

### Log Monitoring

```bash
# Monitor errors
docker compose logs -f | grep -i error

# Count requests
docker compose logs | grep "GET /search" | wc -l
```

## 🆘 Getting Help

### Before Asking for Help

1. **Run diagnostics:**
   ```bash
   ./health-check.sh
   ```

2. **Check documentation:**
   - This troubleshooting guide
   - [Deployment Guide](deployment.md)
   - [Development Guide](development.md)

3. **Search existing issues:**
   - GitHub Issues
   - GitHub Discussions

### Information to Provide

When reporting issues, include:

```bash
# System information
uname -a
docker --version
docker compose version

# Configuration
cat .env
cat docker-compose.yml

# Logs
docker compose logs --tail=50

# Reproduction steps
# What you did, what you expected, what happened
```

### Support Channels

- **GitHub Issues:** Bug reports and feature requests
- **GitHub Discussions:** General questions
- **Discord:** Real-time help

## 📋 Checklist

### Before Deployment
- [ ] Docker and Docker Compose installed
- [ ] Ports 8000 and 8080 available
- [ ] Sufficient disk space (>2GB)
- [ ] Sufficient RAM (>1GB)

### After Deployment
- [ ] Services running: `docker compose ps`
- [ ] App accessible: `curl http://localhost:8000`
- [ ] Search working: `curl "http://localhost:8000/search?q=test"`
- [ ] Logs clean: `docker compose logs | grep -i error`

### Performance Tuning
- [ ] Resource limits set
- [ ] Caching enabled
- [ ] Monitoring configured
- [ ] Backups scheduled

---

*This guide is continuously updated. Found a new issue? [Contribute a fix](https://github.com/sarox-dev/Recollect/blob/main/CONTRIBUTING.md)!*