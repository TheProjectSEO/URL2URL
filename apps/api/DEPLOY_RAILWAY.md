# Railway Deployment Guide

## Quick Deploy (Copy & Paste)

Open your terminal and run these commands:

```bash
# 1. Navigate to API directory
cd /Users/adityaaman/Desktop/All\ Development/urltourl/apps/api

# 2. Login to Railway (opens browser)
railway login

# 3. Initialize new project
railway init

# 4. Set environment variables
railway variables set SUPABASE_KEY="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InF5anpxenFxamltaXR0bHR0dHBoIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjEwNTk5OTksImV4cCI6MjA3NjYzNTk5OX0.YQA0wSqdri73o6WW4-BZl0i8oKlMNcj702nAZvWkR9o"
railway variables set PYTHON_ENV=production

# 5. Deploy
railway up

# 6. Get public URL
railway domain
```

## After Deployment

Test the deployed API:
```bash
curl https://<your-railway-domain>/api/health
```

## Generate Project Token (for CI/CD)

After deployment, generate a project token:
1. Go to https://railway.app → Your Project → Settings → Tokens
2. Click "Generate Project Token"
3. Save it as `RAILWAY_TOKEN` in your CI/CD secrets

## Troubleshooting

**"Unauthorized" error**: Run `railway logout` then `railway login` again

**Build fails**: Check Docker logs with `railway logs --build`

**Health check fails**: Ensure `SUPABASE_KEY` is set correctly
