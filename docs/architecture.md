# Architecture Overview

This document provides a high-level overview of Recollect's system architecture, components, and design decisions.

## 🏗️ System Architecture

Recollect follows a microservices architecture with clear separation of concerns:

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Web Frontend  │    │   FastAPI App   │    │   SearXNG API   │
│                 │    │                 │    │                 │
│  HTML/CSS/JS    │◄──►│  Search Logic   │◄──►│  Web Search     │
│  (Port 8000)    │    │  (Port 5000)    │    │  (Port 8080)    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
                    ┌─────────────────────┐
                    │   Docker Compose    │
                    │   Orchestration     │
                    └─────────────────────┘
```

## 🧩 Components

### 1. Web Frontend
- **Technology**: Vanilla HTML/CSS/JavaScript
- **Purpose**: User interface for search and results display
- **Features**:
  - Google-like search interface
  - Tabbed search (All/Images)
  - Infinite scroll pagination
  - Responsive design

### 2. FastAPI Backend
- **Technology**: Python FastAPI
- **Purpose**: API server handling search requests and result processing
- **Features**:
  - RESTful API endpoints
  - Async request handling
  - JSON response formatting
  - Error handling and logging

### 3. SearXNG Service
- **Technology**: SearXNG (meta search engine)
- **Purpose**: Federated web search across multiple search engines
- **Features**:
  - Privacy-focused search
  - Multiple search categories (general, images, videos, etc.)
  - Configurable search engines
  - Result aggregation

## 🔄 Data Flow

### Search Request Flow

1. **User Input** → Web Frontend
   - User enters query in search bar
   - Selects search category (All/Images)

2. **Frontend Processing** → API Request
   - JavaScript captures input
   - Constructs API request with query and category
   - Sends AJAX request to `/search` endpoint

3. **Backend Processing** → SearXNG Query
   - FastAPI receives request
   - Validates parameters
   - Constructs SearXNG API request
   - Forwards request to SearXNG service

4. **Search Execution** → Result Aggregation
   - SearXNG queries configured search engines
   - Aggregates and ranks results
   - Returns JSON response

5. **Result Processing** → Frontend Display
   - Backend receives SearXNG response
   - Formats results for frontend consumption
   - Returns JSON to frontend

6. **UI Rendering** → User Display
   - Frontend receives results
   - Renders appropriate UI (text results or image grid)
   - Handles infinite scroll for pagination

## 📋 API Design

### Endpoints

- `GET /` - Serves the main search interface
- `GET /search` - Handles search queries
  - Parameters:
    - `q`: Search query (required)
    - `pageno`: Page number for pagination (default: 1)
    - `categories`: Search category (default: "general")

### Response Format

```json
{
  "results": [
    {
      "title": "Result Title",
      "url": "https://example.com",
      "content": "Result description...",
      "thumbnail": "https://example.com/image.jpg"  // For images
    }
  ],
  "has_more": true
}
```

## 🐳 Containerization

### Docker Services

- **app**: FastAPI application container
  - Base: `python:3.12-slim`
  - Exposes port 5000 internally
  - Mounts `./app` for development

- **searxng**: SearXNG search service
  - Base: `searxng/searxng:latest`
  - Exposes port 8080 internally
  - Mounts `./searxng` for configuration

### Networking

- **Internal**: Services communicate via Docker networks
- **External**: App exposed on port 8000, SearXNG bound to localhost:8080

## 🔒 Security Considerations

### Network Security
- SearXNG bound to localhost only (not exposed externally)
- App handles all external requests
- No direct external access to SearXNG

### Data Privacy
- No user data stored (currently)
- All searches processed in-memory
- SearXNG provides privacy-focused search

## 🚀 Scalability

### Current Limitations
- Single instance deployment
- No caching layer
- No database for persistence

### Future Enhancements
- Redis for result caching
- PostgreSQL for search history
- Load balancer for multiple instances
- Message queue for background processing

## 🛠️ Development Architecture

### Code Organization
```
app/
├── app.py              # Main FastAPI application
└── templates/          # HTML templates (future)

searxng/
└── settings.yml        # SearXNG configuration

docker/
└── app/
    └── Dockerfile      # App container definition
```

### Dependencies
- **Runtime**: fastapi, uvicorn, httpx, jinja2
- **Development**: Requirements in `requirements.txt`
- **Infrastructure**: Docker, docker-compose

## 📊 Performance Characteristics

### Response Times
- Typical search: 1-3 seconds
- Image search: 2-5 seconds
- Pagination: <1 second (cached results)

### Resource Usage
- Memory: ~200MB per service
- CPU: Minimal (async processing)
- Network: Dependent on search engines queried

## 🔄 Future Architecture

### Planned Components
- **Database**: PostgreSQL for search history
- **Cache**: Redis for result caching
- **Queue**: Celery for background tasks
- **Frontend**: React/Vue for enhanced UI

### Microservices Evolution
- Separate search service
- Result processing service
- User management service
- Analytics service

This architecture provides a solid foundation for a privacy-focused, scalable search platform while maintaining simplicity for development and deployment.