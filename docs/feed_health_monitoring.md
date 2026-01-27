# Feed Health Monitoring System

Automatic RSS feed health checking and repair system for the ABQ Daily Intelligence pipeline.

## Features

### 🔍 Automatic Health Checks
- Monitors all 89+ RSS feeds daily
- Detects common issues: 404, 500, timeouts, parse errors, redirects
- Runs automatically before each daily RSS fetch
- Non-blocking: pipeline continues even if health check fails

### 🔧 Automatic Repairs
- **404 errors**: Searches for alternative URLs on the same domain
- **Redirects**: Automatically follows and updates feed URLs
- **Known fixes**: Pre-configured alternatives for common sources (NRCan, ECCC, etc.)
- **Common patterns**: Tests standard RSS URL patterns (`/feed/`, `/rss.xml`, etc.)

### 📊 Health Tracking
- Stores historical health data in `data/feed_health.json`
- Calculates uptime statistics per feed
- Tracks failure patterns over time
- Keeps last 30 health checks per feed

### 📈 Reporting
- Daily health report logged before RSS fetch
- Shows healthy, degraded, and down feeds
- Lists automatic fixes applied
- Provides feed statistics and uptime percentages

## Usage

### Manual Health Checks

Check all feeds:
```bash
python scripts/check_feed_health.py
```

Check and apply automatic fixes:
```bash
python scripts/check_feed_health.py --fix
```

Check specific feed:
```bash
python scripts/check_feed_health.py --feed "Natural Resources Canada RSS"
```

Show feed statistics:
```bash
python scripts/check_feed_health.py --stats
```

### Automatic Integration

Health checks run automatically as **Stage 0** of the daily pipeline:
1. **Health Check** - Test feeds, apply fixes
2. **RSS Fetch** - Fetch articles from feeds
3. **Analysis** - Score and filter articles
4. **Email Generation** - Create HTML email
5. **Email Delivery** - Send via Gmail

The health check is non-blocking - the pipeline continues even if some feeds fail.

## Health Status Levels

| Status | Description |
|--------|-------------|
| **Healthy** | Feed working normally, returning articles |
| **Degraded** | Feed accessible but has issues (slow, parse errors, empty) |
| **Down** | Feed not accessible (404, 500, timeout) |
| **Fixed** | Issue automatically repaired by updating URL |
| **Unknown** | Unexpected error during health check |

## Common Issues and Automatic Fixes

### 404 Not Found
**Cause**: Feed URL changed or removed
**Auto-fix**:
1. Check known alternatives for the domain
2. Try common RSS URL patterns
3. Update `feeds.json` if working URL found

**Example**: Natural Resources Canada feed moved from `/api/rss/en/news` to new Canada News Centre API

### 500/502/503 Server Errors
**Cause**: Temporary server issues
**Action**: Logged as "Down", pipeline continues, will retry tomorrow

### Timeouts
**Cause**: Slow server response or network issues
**Action**: Logged as "Down", feed will be retried next run

### Redirects
**Cause**: Feed moved to new URL
**Auto-fix**: Follow redirect and update URL in `feeds.json`

### Parse Errors
**Cause**: Malformed XML/RSS or encoding issues
**Action**: Logged as "Degraded", feed still processed if parseable

### Empty Feed
**Cause**: Feed returns no articles
**Action**: Logged as "Degraded" - may indicate inactivity

## Configuration

### Known Domain Fixes

Pre-configured alternative URLs for common sources are defined in `feed_health.py`:

```python
known_fixes = {
    "natural-resources.canada.ca": [
        "https://api.io.canada.ca/io-server/gc/news/en/v2?dept=naturalresourcescanada...",
        "https://natural-resources.canada.ca/simply-science/rss.xml",
    ],
    "www.canada.ca": [
        "https://www.canada.ca/en/environment-climate-change.atom.xml",
    ],
}
```

To add new known fixes, edit `src/utils/feed_health.py` and add entries to the `_get_known_fixes()` method.

### Timeout Settings

Default timeout: 30 seconds

Change for specific checks:
```bash
python scripts/check_feed_health.py --timeout 60
```

## Health Data Storage

### Location
```
data/feed_health.json
```

### Structure
```json
{
  "feeds": {
    "Natural Resources Canada RSS": {
      "checks": [
        {
          "timestamp": "2026-01-27T07:00:00",
          "status": "healthy",
          "issue": null
        }
      ],
      "total_checks": 45,
      "failures": 2
    }
  },
  "last_check": "2026-01-27T07:00:00"
}
```

### Data Retention
- Last 30 checks per feed
- Total check count and failure count preserved
- Uptime calculated as: `(total - failures) / total`

## Feed Statistics

View detailed statistics:
```bash
python scripts/check_feed_health.py --stats
```

Output:
```
============================================================
FEED HEALTH STATISTICS
============================================================

Natural Resources Canada RSS
  Uptime: 95.6%
  Total checks: 45
  Failures: 2
  Recent issues: 0

CBC News - Technology & Science
  Uptime: 98.1%
  Total checks: 52
  Failures: 1
  Recent issues: 0
```

## Integration with Daily Pipeline

The health check is integrated into `src/orchestrator/pipeline_runner.py` as Stage 0:

```python
def run(self) -> int:
    # Stage 0: Feed Health Check (non-blocking)
    self._stage_health_check()

    # Stage 1: RSS Fetch
    success, count = self._stage_rss_fetch()
    # ...
```

Health check results are logged but do not block the pipeline. Even if all feeds are down, the pipeline will attempt RSS fetch.

## Monitoring and Alerts

### Daily Logs
Health check results are logged in:
```
logs/daily_YYYY-MM-DD.log
```

Look for:
- `Feed health check complete` - success message
- `Applied X automatic fixes` - fixes applied
- `X feeds are currently down` - warning

### Error Logs
Feed failures are also logged in:
```
logs/errors_YYYY-MM-DD.log
```

### Weekly Health Report
Consider creating a weekly summary script that:
1. Aggregates feed health data from the past 7 days
2. Identifies persistently failing feeds
3. Calculates overall system health
4. Emails summary to administrator

## Troubleshooting

### Feed shows as "Down" but works in browser
**Solution**: Check if the feed requires specific headers or cookies. Update `feed_health.py` to add custom headers:

```python
response = requests.head(url, timeout=self.timeout,
                        headers={'User-Agent': 'ABQ-Bot/1.0'})
```

### False positives for slow feeds
**Solution**: Increase timeout for specific domains:

```python
# In check_feed()
timeout = self.timeout * 2 if 'slowdomain.com' in url else self.timeout
```

### Auto-fix not working for known domain
**Solution**: Add the domain to `_get_known_fixes()` with correct alternative URLs

### Health check taking too long
**Solution**:
- Reduce timeout: `--timeout 15`
- Run checks in parallel (future enhancement)
- Check for specific feeds: `--feed "Name"`

## Future Enhancements

- [ ] Parallel feed checking for faster execution
- [ ] ML-based pattern detection for finding alternative URLs
- [ ] Webhook notifications for critical failures
- [ ] Dashboard with real-time health metrics
- [ ] Automatic feed discovery from source homepages
- [ ] Integration with monitoring services (Pingdom, UptimeRobot)
- [ ] Weekly health digest email
- [ ] Automated feed pruning (disable after X consecutive failures)

## Related Files

- `src/utils/feed_health.py` - Core health checking module
- `scripts/check_feed_health.py` - Standalone health check tool
- `src/orchestrator/pipeline_runner.py` - Pipeline integration
- `config/feeds.json` - Feed configuration
- `data/feed_health.json` - Health history data
