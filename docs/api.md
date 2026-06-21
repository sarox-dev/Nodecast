# API Reference

This document provides detailed information about Recollect's API endpoints, request/response formats, and usage examples.

## 🌐 Base URL

```
http://localhost:8000
```

All API endpoints are served from the main application port.

## 📋 Endpoints

### GET /

Serves the main search interface HTML page.

**Response**: HTML page with search interface

**Status Codes**:
- `200` - Success

---

### GET /search

Performs a search query and returns results.

**Parameters**:

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `q` | string | Yes | - | Search query |
| `pageno` | integer | No | 1 | Page number for pagination |
| `categories` | string | No | "general" | Search category |

**Categories**:
- `"general"` - General web search
- `"images"` - Image search
- `"videos"` - Video search
- `"news"` - News search
- `"music"` - Music search
- `"files"` - File search

**Request Example**:
```bash
curl "http://localhost:8000/search?q=python%20tutorial&pageno=1&categories=general"
```

**Response Format**:
```json
{
  "results": [
    {
      "title": "Python Tutorial - W3Schools",
      "url": "https://www.w3schools.com/python/",
      "content": "Well organized and easy to understand Web building tutorials with lots of examples of how to use HTML, CSS, JavaScript, SQL, Python, PHP, Bootstrap, Java, XML and more.",
      "engine": "google",
      "parsed_url": [
        "https",
        "www.w3schools.com",
        "python",
        "",
        "",
        ""
      ],
      "template": "default.html",
      "engines": [
        "google"
      ],
      "positions": [
        1
      ],
      "score": 1.0,
      "category": "general"
    }
  ],
  "has_more": true
}
```

**Response Fields**:

| Field | Type | Description |
|-------|------|-------------|
| `results` | array | Array of search results |
| `has_more` | boolean | Whether more results are available |

**Result Object Fields**:

| Field | Type | Description |
|-------|------|-------------|
| `title` | string | Result title |
| `url` | string | Result URL |
| `content` | string | Result description/snippet |
| `engine` | string | Search engine that provided the result |
| `parsed_url` | array | Parsed URL components |
| `template` | string | Display template |
| `engines` | array | List of engines that returned this result |
| `positions` | array | Position rankings |
| `score` | number | Relevance score |
| `category` | string | Search category |

**Image Search Response**:
For image searches (`categories=images`), results include additional image-specific fields:

```json
{
  "results": [
    {
      "title": "Python Logo",
      "url": "https://www.python.org/static/img/python-logo.png",
      "content": "Python programming language logo",
      "img_src": "https://www.python.org/static/img/python-logo.png",
      "thumbnail": "https://www.python.org/static/img/python-logo.png",
      "engine": "google images",
      "category": "images"
    }
  ],
  "has_more": true
}
```

**Status Codes**:
- `200` - Success
- `400` - Bad request (missing required parameters)
- `500` - Internal server error

**Error Response**:
```json
{
  "detail": "Error message"
}
```

## 🔄 Pagination

Results are paginated with 20 results per page by default.

- Use `pageno` parameter to request specific pages
- `has_more` indicates if additional pages are available
- Frontend implements infinite scroll automatically

**Example Pagination**:
```bash
# Page 1
curl "http://localhost:8000/search?q=python&pageno=1"

# Page 2
curl "http://localhost:8000/search?q=python&pageno=2"
```

## 🖼️ Search Categories

### General Search
- Searches across multiple engines
- Returns text-based results
- Best for informational queries

### Image Search
- Specialized image search engines
- Returns image URLs and thumbnails
- Optimized for visual content

### Other Categories
- `videos` - Video content search
- `news` - Recent news articles
- `music` - Music and audio content
- `files` - Document and file search

## 📊 Rate Limiting

Currently no rate limiting is implemented. Future versions may include:
- Request per minute limits
- API key authentication
- Usage quotas

## 🔒 Security

### Input Validation
- Query parameters are validated
- HTML injection prevention
- URL encoding required

### Privacy
- No user tracking or data collection
- Searches processed in-memory only
- No persistent storage of queries

## 🧪 Testing Examples

### Basic Search
```bash
curl "http://localhost:8000/search?q=open%20source"
```

### Image Search
```bash
curl "http://localhost:8000/search?q=cats&categories=images"
```

### Paginated Search
```bash
curl "http://localhost:8000/search?q=python&pageno=2"
```

### Error Handling
```bash
# Missing query parameter
curl "http://localhost:8000/search"
# Returns 422 Unprocessable Entity
```

## 🔧 Integration Examples

### JavaScript (Frontend)
```javascript
async function search(query, category = 'general', page = 1) {
  const response = await fetch(`/search?q=${encodeURIComponent(query)}&categories=${category}&pageno=${page}`);
  const data = await response.json();
  return data;
}
```

### Python (External Integration)
```python
import requests

def search_recollect(query, category='general', page=1):
    url = "http://localhost:8000/search"
    params = {
        'q': query,
        'categories': category,
        'pageno': page
    }
    response = requests.get(url, params=params)
    return response.json()
```

### cURL (Testing)
```bash
# Save response to file
curl -s "http://localhost:8000/search?q=linux" -o results.json

# Pretty print JSON
curl -s "http://localhost:8000/search?q=linux" | python3 -m json.tool
```

## 🚨 Error Handling

### Common Errors

**400 Bad Request**
```json
{
  "detail": [
    {
      "loc": ["query", "q"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

**500 Internal Server Error**
```json
{
  "detail": "SearXNG service unavailable"
}
```

### Error Recovery
- Implement retry logic for 500 errors
- Check SearXNG service status
- Validate input parameters before requests

## 🔄 API Versioning

Current API version: v1 (implicit)

Future versions will use URL versioning:
```
/api/v1/search
/api/v2/search
```

## 📈 Monitoring

API metrics are not currently exposed. Future enhancements may include:
- Request count and latency
- Error rates
- Popular queries
- Search engine performance

## 🤝 Support

For API-related issues:
1. Check this documentation
2. Review [Troubleshooting Guide](troubleshooting.md)
3. Open an issue on GitHub
4. Join our Discord community

---

*This API documentation is automatically generated and maintained alongside the codebase.*