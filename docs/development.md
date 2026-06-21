# Development Guide

This guide covers everything you need to know to set up a development environment and contribute to Recollect.

## 🚀 Quick Setup

### Prerequisites

- **Docker & Docker Compose**: Latest versions
- **Git**: For version control
- **Python 3.12+**: For local development (optional)
- **VS Code**: Recommended editor with Docker extension

### Clone and Setup

```bash
# Clone the repository
git clone https://github.com/sarox-dev/Recollect.git
cd recollect

# Copy environment configuration
cp .env.example .env

# Start development environment
docker compose up -d

# Check logs
docker compose logs -f app
```

### Verify Installation

```bash
# Check container status
docker compose ps

# Test the application
curl http://localhost:8000

# Test search functionality
curl "http://localhost:8000/search?q=test"
```

## 🛠️ Development Workflow

### 1. Create Feature Branch

```bash
# Create and switch to feature branch
git checkout -b feature/your-feature-name

# Or for bug fixes
git checkout -b fix/issue-description
```

### 2. Development Process

```bash
# Start development environment
docker compose up -d

# Make your changes
# Edit files in ./app/

# Restart app container to see changes
docker compose restart app

# Test your changes
curl "http://localhost:8000/search?q=test"

# Check logs for errors
docker compose logs app
```

### 3. Testing

```bash
# Run basic functionality tests
curl -s http://localhost:8000 | grep "Recollect"

# Test search API
curl -s "http://localhost:8000/search?q=open%20source" | jq '.results | length'

# Test image search
curl -s "http://localhost:8000/search?q=cats&categories=images" | jq '.results[0].category'
```

### 4. Commit and Push

```bash
# Stage your changes
git add .

# Commit with descriptive message
git commit -m "feat: add image search functionality"

# Push to your branch
git push origin feature/your-feature-name
```

### 5. Create Pull Request

1. Go to GitHub repository
2. Click "Pull Request"
3. Select your feature branch
4. Fill out the PR template
5. Request review

## 📁 Project Structure

```
recollect/
├── app/                    # Main application
│   ├── app.py             # FastAPI application
│   └── templates/         # HTML templates (future)
├── searxng/               # SearXNG configuration
│   └── settings.yml       # Search engine settings
├── docker/                # Docker configurations
│   └── app/
│       └── Dockerfile     # App container definition
├── docs/                  # Documentation
├── tests/                 # Test files
├── .env.example           # Environment template
├── docker-compose.yml     # Container orchestration
├── requirements.txt       # Python dependencies
└── README.md              # Project overview
```

## 🔧 Development Tools

### Local Python Development

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt

# Run locally (without Docker)
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

### Docker Development

```bash
# Build specific service
docker compose build app

# Run with hot reload
docker compose up

# Execute commands in container
docker compose exec app bash

# View container logs
docker compose logs -f app
```

### VS Code Extensions

Recommended extensions for development:
- **Python** - Python language support
- **Docker** - Docker integration
- **Remote-Containers** - Develop inside containers
- **GitLens** - Enhanced Git capabilities

## 🧪 Testing Strategy

### Manual Testing

```bash
# Test different search types
curl "http://localhost:8000/search?q=python&categories=general"
curl "http://localhost:8000/search?q=python&categories=images"

# Test pagination
curl "http://localhost:8000/search?q=python&pageno=2"

# Test error handling
curl "http://localhost:8000/search"  # Missing query
```

### Automated Testing (Future)

```bash
# Run test suite (when implemented)
pytest

# Run with coverage
pytest --cov=app

# Run specific tests
pytest tests/test_search.py
```

## 🐛 Debugging

### Common Issues

**Container won't start**
```bash
# Check logs
docker compose logs app

# Check container status
docker compose ps

# Restart services
docker compose restart
```

**Search not working**
```bash
# Check SearXNG status
curl http://localhost:8080

# Check app connectivity
docker compose exec app curl http://searxng_api:8080/search?q=test
```

**Changes not reflected**
```bash
# Restart app container
docker compose restart app

# Rebuild if Dockerfile changed
docker compose build app
```

### Debug Mode

Enable debug logging in SearXNG:
```yaml
# searxng/settings.yml
general:
  debug: true
```

## 📝 Code Style

### Python Guidelines

- **Black**: Code formatting
- **isort**: Import sorting
- **PEP 8**: Python style guide
- **Type hints**: Use type annotations

### Commit Messages

Follow conventional commits:
```
feat: add new search category
fix: resolve pagination bug
docs: update API documentation
style: format code with black
refactor: extract search service
test: add unit tests
```

### Code Review Checklist

- [ ] Code follows style guidelines
- [ ] Tests pass (when available)
- [ ] Documentation updated
- [ ] No breaking changes without migration
- [ ] Security considerations addressed

## 🔒 Security Development

### Secure Coding Practices

- **Input Validation**: Always validate user inputs
- **Error Handling**: Don't expose internal errors
- **Dependencies**: Keep packages updated
- **Secrets**: Never commit secrets to code

### Environment Variables

```bash
# Never commit .env file
echo ".env" >> .gitignore

# Use .env.example as template
cp .env.example .env
```

## 🚀 Deployment

### Local Deployment

```bash
# Production build
docker compose -f docker-compose.yml up -d

# With custom environment
SEARXNG_PORT=9090 APP_PORT=3000 docker compose up -d
```

### Server Deployment

```bash
# Clone on server
git clone https://github.com/sarox-dev/Recollect.git
cd recollect

# Configure environment
cp .env.example .env
# Edit .env with production values

# Deploy
docker compose up -d

# Setup reverse proxy (nginx example)
# Configure nginx to proxy to localhost:8000
```

## 📊 Performance Optimization

### Profiling

```bash
# Profile Python code
python -m cProfile app.py

# Monitor container resources
docker stats

# Check response times
curl -w "@curl-format.txt" -o /dev/null -s "http://localhost:8000/search?q=test"
```

### Optimization Tips

- **Async/Await**: Use async for I/O operations
- **Caching**: Implement result caching
- **Pagination**: Load results on demand
- **Compression**: Enable gzip compression

## 🤝 Contributing Guidelines

### Issue Reporting

1. **Bug Reports**: Use bug report template
2. **Feature Requests**: Describe the problem and solution
3. **Questions**: Check docs first, then ask in Discussions

### Pull Request Process

1. **Fork** the repository
2. **Create** feature branch
3. **Develop** and test changes
4. **Update** documentation
5. **Submit** pull request
6. **Respond** to review feedback

### Code of Conduct

- Be respectful and inclusive
- Focus on constructive feedback
- Help newcomers learn
- Maintain professional communication

## 📚 Learning Resources

### FastAPI
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [FastAPI Tutorial](https://fastapi.tiangolo.com/tutorial/)

### SearXNG
- [SearXNG Documentation](https://docs.searxng.org/)
- [SearXNG GitHub](https://github.com/searxng/searxng)

### Docker
- [Docker Compose Guide](https://docs.docker.com/compose/)
- [Docker Best Practices](https://docs.docker.com/develop/dev-best-practices/)

## 🆘 Getting Help

### Community Support
- **GitHub Issues**: Bug reports and feature requests
- **GitHub Discussions**: General questions and discussions
- **Discord**: Real-time chat and support

### Documentation Issues
- Found a documentation bug? [Open an issue](https://github.com/sarox-dev/Recollect/issues/new?labels=documentation)
- Suggest improvements to this guide

---

Happy coding! 🎉