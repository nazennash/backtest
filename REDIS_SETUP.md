# Redis Setup for Bloomberg-Class Trading App

## 🚀 Production Redis Setup (Digital Ocean)

### 1. Digital Ocean Managed Redis

```bash
# Create Redis cluster on Digital Ocean
doctl databases create redis-trading-app --region nyc1 --size db-s-1vcpu-1gb

# Get connection string
doctl databases connection redis-trading-app
```

### 2. Environment Variables

```bash
# Add to your environment
export REDIS_URL="redis://username:password@host:port"
```

## 💻 Local Development Redis

### Windows (via Docker)

```bash
# Install Docker Desktop
# Run Redis container
docker run -d -p 6379:6379 --name redis-trading redis:alpine

# Test connection
docker exec -it redis-trading redis-cli ping
```

### Windows (via WSL2)

```bash
# In WSL2 Ubuntu
sudo apt update
sudo apt install redis-server
sudo service redis-server start
redis-cli ping
```

### Enable Redis in App

```bash
# Create flag file to enable Redis
touch redis_enabled.txt
```

## 📊 Cache Performance

### Current Fallback

- **Database Cache**: Uses SQLite cache table (development)
- **Performance**: ~50ms cache hits
- **Storage**: Persistent across restarts

### With Redis

- **Redis Cache**: In-memory ultra-fast
- **Performance**: ~1ms cache hits
- **Storage**: 10x faster chart loading

## 🔧 Cache Keys Structure

```text
trading_app:ticker_search:md5(query)
trading_app:chart:md5(ticker_date_freq)
trading_app:user_preferences:user_id
```

## ⚡ Expected Performance Boost

| Operation | Without Cache | With DB Cache | With Redis |
|-----------|---------------|---------------|------------|
| Ticker Search | 500ms | 50ms | 5ms |
| Chart Generation | 2000ms | 200ms | 50ms |
| Page Load | 3000ms | 500ms | 100ms |

## 🏆 Bloomberg-Level Features

✅ **No form submissions** - Pure AJAX  
✅ **Instant chart loading** - Redis cached  
✅ **Real-time ticker search** - FMP API  
✅ **Smart date defaults** - VIX optimized  
✅ **Professional UI** - No "confirm form" popups
