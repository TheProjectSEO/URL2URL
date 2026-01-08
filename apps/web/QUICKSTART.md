# Quick Start Guide

Get the URL-to-URL Product Matcher frontend running in 3 minutes.

## Prerequisites

- Node.js 18+ installed
- Backend API running (see backend setup)

## Installation

```bash
# Navigate to the web directory
cd apps/web

# Install dependencies
npm install
```

## Configuration

The `.env.local` file is already created with default values:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_SUPABASE_URL=https://qyjzqzqqjimittltttph.supabase.co
```

If your backend is running on a different port or host, update `NEXT_PUBLIC_API_URL`.

## Run Development Server

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

## What You'll See

1. **Dashboard** - Stats overview and recent jobs
2. **Create Job** - Click "New Job" to create your first matching job
3. **Job Details** - View progress, matches, and approve/reject results

## Test the Application

### 1. Create a Test Job

Click "New Job" and fill in:
- **Name**: "Test Amazon vs eBay"
- **Source URL**: https://www.amazon.com/s?k=laptop
- **Target URL**: https://www.ebay.com/sch/i.html?_nkw=laptop
- Click "Create Job"

### 2. Run the Job

On the job details page:
- Click "Run Job" to start crawling and matching
- Watch the progress bar update in real-time
- See matches appear in the table

### 3. Review Matches

- Sort by score, confidence, or status
- Filter by pending/approved/rejected
- Click "Approve" or "Reject" for each match

## Production Build

```bash
# Build for production
npm run build

# Start production server
npm start
```

The production build will be optimized and ready to deploy.

## Common Issues

### API Connection Error

If you see "Failed to load jobs" or similar errors:

1. Ensure backend is running:
   ```bash
   cd ../backend
   uvicorn app.main:app --reload
   ```

2. Check the API URL in `.env.local` matches your backend

3. Verify CORS is enabled in the backend

### Port Already in Use

If port 3000 is taken:

```bash
# Run on a different port
PORT=3001 npm run dev
```

### Build Errors

```bash
# Clear cache and rebuild
rm -rf .next node_modules
npm install
npm run build
```

## Next Steps

- Read [README.md](./README.md) for full documentation
- Explore the [component architecture](./README.md#components)
- Learn about [API integration](./README.md#api-integration)
- Deploy to production (Vercel, Netlify, etc.)

## Support

Having issues? Check:
- Backend is running and accessible
- Environment variables are set correctly
- Node.js version is 18 or higher
- All dependencies installed (`npm install`)
