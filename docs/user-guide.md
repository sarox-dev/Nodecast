# User Guide

Welcome to Recollect! This guide will help you get started with your self-hosted search engine.

## 🎯 What is Recollect?

Recollect is a privacy-focused, self-hosted search engine that combines web search with local knowledge management. It provides:

- **Unified Search**: Search across web, GitHub, and local files
- **Privacy First**: No tracking, no data collection
- **Google-like Interface**: Familiar search experience
- **Image Search**: Dedicated image search capabilities
- **Infinite Scroll**: Load more results as you browse

## 🚀 Quick Start

### Access Recollect

Once deployed, access Recollect at:
```
http://localhost:8000
```

Or your custom domain if configured.

### First Search

1. Open Recollect in your browser
2. Type your search query in the search box
3. Press Enter or click the search button
4. Browse results using tabs (All/Images)

## 🔍 Search Features

### Basic Search

Enter any query in the search box:
- **General queries**: "python tutorial", "machine learning"
- **Technical searches**: "docker compose nginx", "react hooks"
- **Research topics**: "quantum computing", "climate change"

### Search Categories

#### All (Default)
Searches across multiple search engines for comprehensive results including:
- Web pages
- Articles
- Documentation
- Forums

#### Images
Specialized image search returning:
- Photos
- Diagrams
- Screenshots
- Visual content

### Advanced Search

Use SearXNG's search syntax:
- **Exact phrases**: `"exact match"`
- **Exclude terms**: `python -snake`
- **Site search**: `site:github.com docker`
- **File types**: `filetype:pdf tutorial`

## 🎨 Interface Guide

### Search Bar
- **Location**: Top center of the page
- **Features**: Auto-focus, instant search
- **Shortcuts**: Press Enter to search

### Navigation Tabs
- **All**: General web search results
- **Images**: Image and visual content
- **Future**: Videos, News, Music (when enabled)

### Results Display

#### Text Results
Each result shows:
- **Title**: Clickable link to the source
- **URL**: Source website
- **Snippet**: Preview of content
- **Source**: Which search engine found it

#### Image Results
- **Thumbnail Grid**: Visual preview of images
- **Click to View**: Opens full-size image
- **Source Links**: Navigate to original page

### Infinite Scroll
- **Automatic Loading**: More results load as you scroll
- **No Pagination**: Seamless browsing experience
- **Performance**: Results load on demand

## ⚙️ Configuration

### Basic Settings

Most configuration is handled automatically, but you can customize:

#### SearXNG Settings
Edit `searxng/settings.yml` to:
- Change instance name
- Configure search engines
- Set privacy options
- Enable/disable features

#### Environment Variables
Modify `.env` for:
- Port numbers
- Instance names
- Debug settings

### Advanced Configuration

#### Search Engines
Enable/disable specific search engines in `searxng/settings.yml`:

```yaml
engines:
  - name: google
    engine: google
  - name: duckduckgo
    engine: duckduckgo
  - name: startpage
    engine: startpage
```

#### Privacy Settings
Configure privacy features:

```yaml
general:
  debug: false
  instance_name: "My Recollect"
  privacypolicy_url: false
```

## 🔒 Privacy & Security

### Privacy Features

- **No Tracking**: Recollect doesn't track your searches
- **No Data Storage**: Search queries aren't stored
- **Federated Search**: Uses multiple engines simultaneously
- **Self-Hosted**: You control your data

### Security Best Practices

- **Keep Updated**: Regularly update Docker images
- **Firewall**: Only expose necessary ports
- **HTTPS**: Use SSL certificates for production
- **Backups**: Backup your configuration

## 📱 Mobile Usage

Recollect works great on mobile devices:

### Mobile Features
- **Responsive Design**: Adapts to screen size
- **Touch Friendly**: Easy tapping and scrolling
- **Fast Loading**: Optimized for mobile networks

### Mobile Tips
- Use landscape mode for better results view
- Pinch to zoom on images
- Long-press links to open in new tabs

## 🛠️ Maintenance

### Regular Tasks

#### Updates
```bash
# Update Recollect
cd recollect
git pull
docker compose build
docker compose up -d
```

#### Backups
```bash
# Backup configuration
cp .env .env.backup
cp searxng/settings.yml searxng/settings.yml.backup
```

#### Monitoring
```bash
# Check service status
docker compose ps

# View recent activity
docker compose logs --tail=20
```

### Troubleshooting

#### Common Issues

**Search not working:**
- Check if SearXNG is running: `docker compose ps`
- Test SearXNG directly: `curl http://localhost:8080`

**Slow performance:**
- Check system resources: `docker stats`
- Restart services: `docker compose restart`

**Page not loading:**
- Verify port configuration in `.env`
- Check firewall settings

## 🔧 Customization

### Themes (Future)
Recollect currently uses a clean, Google-inspired theme. Future versions may include:
- Dark mode
- Custom color schemes
- Theme customization

### Search Engines
Add or remove search engines by editing `searxng/settings.yml`:

```yaml
engines:
  - name: wikipedia
    engine: wikipedia
    shortcut: wp
  - name: bing
    engine: bing
    shortcut: bi
```

### Categories
Enable additional search categories:

```yaml
categories:
  - general
  - images
  - videos
  - news
  - music
  - files
```

## 📊 Usage Statistics

### Monitoring Usage

Check container logs for usage patterns:
```bash
# Recent searches
docker compose logs app | grep "GET /search"

# Error rate
docker compose logs app | grep -i error | wc -l
```

### Performance Metrics

Monitor response times:
```bash
# Test search speed
time curl -s "http://localhost:8000/search?q=test" > /dev/null
```

## 🌐 Integration

### Browser Integration

#### Search Engine
Add Recollect as a search engine in your browser:
- **Chrome**: Settings → Search Engines → Add
- **Firefox**: Preferences → Search → Add

#### Bookmarklet
Create a bookmarklet for quick access:
```javascript
javascript:window.open('http://localhost:8000/?q='+encodeURIComponent(window.getSelection()));
```

### API Usage

Access Recollect programmatically:

```bash
# Search API
curl "http://localhost:8000/search?q=python&categories=general"

# Image search
curl "http://localhost:8000/search?q=cats&categories=images"
```

## 🤝 Community

### Getting Help

- **Documentation**: Check this user guide first
- **Issues**: Report bugs on GitHub
- **Discussions**: Ask questions in GitHub Discussions
- **Discord**: Join our community chat

### Contributing

Help improve Recollect:
- **Report Issues**: Found a bug? Let us know
- **Suggest Features**: Have an idea? Share it
- **Contribute Code**: Fix bugs or add features
- **Improve Docs**: Help make documentation better

## 📋 Best Practices

### Search Tips
- **Be Specific**: Use detailed queries for better results
- **Use Quotes**: `"exact phrase"` for precise matches
- **Combine Terms**: `python tutorial beginners` for focused results
- **Exclude Terms**: `python -snake` to filter results

### Performance Tips
- **Local Network**: Best performance on local network
- **Resource Allocation**: Ensure adequate RAM for search engines
- **Regular Updates**: Keep Docker images updated
- **Monitor Usage**: Check logs for performance issues

### Security Tips
- **Firewall**: Only expose necessary ports
- **Updates**: Regularly update all components
- **Backups**: Backup configuration regularly
- **Access Control**: Limit access to trusted users

## 🚀 Advanced Usage

### Custom Search Engines

Add specialized search engines:

```yaml
engines:
  - name: stackoverflow
    engine: stackoverflow
    shortcut: so
  - name: github
    engine: github
    shortcut: gh
```

### Result Filtering

Use SearXNG's filtering options:
- **Safe Search**: Filter adult content
- **Language**: Restrict to specific languages
- **Time Range**: Search within date ranges

### Keyboard Shortcuts (Future)

Planned keyboard shortcuts:
- `Ctrl+K`: Focus search bar
- `Tab`: Switch between tabs
- `Enter`: Perform search
- `Esc`: Clear search

## 📞 Support

### Self-Help Resources

1. **This Guide**: Comprehensive user documentation
2. **Troubleshooting**: [Common issues and solutions](troubleshooting.md)
3. **API Docs**: [Technical API reference](api.md)
4. **GitHub Issues**: Search existing problems

### Getting Support

If you need help:

1. **Check Documentation**: Review relevant guides
2. **Search Issues**: Look for similar problems
3. **Gather Information**: Collect logs and configuration
4. **Open Issue**: Provide detailed problem description

### Support Information

When asking for help, include:
- Recollect version/commit
- Docker version
- Browser and OS
- Steps to reproduce
- Error messages/logs
- Configuration files

## 🎉 What's Next

### Upcoming Features

- **Search History**: Save and revisit past searches
- **Collections**: Organize results into folders
- **Dark Mode**: Eye-friendly dark theme
- **Extensions**: Browser extensions for quick search
- **Mobile App**: Native mobile applications

### Roadmap

Check our [GitHub Issues](https://github.com/sarox-dev/Recollect/issues) for planned features and vote on what matters most to you.

---

*Thank you for using Recollect! Your feedback helps make it better for everyone.*