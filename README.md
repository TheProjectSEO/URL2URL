# URL-to-URL Product Matcher

AI-powered product matching across e-commerce websites with a modern Next.js frontend.

## 🎯 Overview

This application crawls two e-commerce websites, extracts product information, and uses AI to match similar products across both sites. Perfect for price comparison, inventory matching, and competitive analysis.

## 📦 Project Structure

```
urltourl/
├── apps/
│   └── web/              # Next.js 14 Frontend (✅ Complete)
│       ├── src/
│       │   ├── app/      # Pages (Dashboard, Jobs, Matches)
│       │   ├── components/ # Reusable UI components
│       │   └── lib/      # API client & utilities
│       └── Documentation/
│
└── Documentation/        # Project-level docs
    ├── FRONTEND_COMPLETE.md
    ├── DEPLOYMENT_CHECKLIST.md
    └── PROJECT_SUMMARY.md
```

## ✨ Features

### Frontend (✅ Complete)
- **Dashboard** - Overview with stats and recent jobs
- **Job Management** - Create, run, and monitor matching jobs
- **Match Review** - Sortable, filterable results table
- **Real-time Updates** - Live progress tracking
- **Dark Mode** - Professional UI with responsive design
- **Type-Safe** - Full TypeScript coverage

## 🚀 Quick Start

### Prerequisites
- Node.js 18+
- Backend API running (separate project)

### Install & Run

```bash
# Navigate to frontend
cd apps/web

# Install dependencies
npm install

# Start development server
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) to view the app.

## 📚 Documentation

| Document | Description |
|----------|-------------|
| [`apps/web/README.md`](apps/web/README.md) | Complete frontend documentation |
| [`apps/web/QUICKSTART.md`](apps/web/QUICKSTART.md) | Get started in 3 minutes |
| [`apps/web/PAGES_OVERVIEW.md`](apps/web/PAGES_OVERVIEW.md) | Visual guide to all pages |
| [`FRONTEND_COMPLETE.md`](FRONTEND_COMPLETE.md) | Frontend completion summary |
| [`DEPLOYMENT_CHECKLIST.md`](DEPLOYMENT_CHECKLIST.md) | Production deployment guide |
| [`PROJECT_SUMMARY.md`](PROJECT_SUMMARY.md) | Complete project overview |

## 🎨 Screenshots

### Dashboard
- Overview statistics (jobs, matches, completion rate)
- Recent jobs with status and progress
- Quick actions (create new job)

### Jobs List
- All jobs with filtering by status
- Job cards with source/target URLs
- Run and delete actions

### Create Job
- Form to input source and target site URLs
- Optional categories for better matching
- Validation and error handling

### Job Details
- Real-time progress tracking
- Match results table (sortable/filterable)
- Approve/reject individual matches
- Statistics (products, matches, match rate)

## 🛠 Technology Stack

- **Next.js 16** - React framework with App Router
- **React 19** - UI library with Server Components
- **TypeScript 5** - Type-safe development
- **Tailwind CSS 4** - Utility-first styling
- **Lucide React** - Beautiful icons

## 🎯 Key Features

### Real-time Updates
- Auto-refresh every 5s for active jobs
- Live progress bars during crawling/matching
- Instant UI updates on actions

### Smart Matching
- AI-powered product similarity scoring
- Color-coded confidence tiers
- 6 confidence levels (Exact → No Match)

### User Experience
- Professional dark mode (default)
- Responsive design (mobile-first)
- Loading states for all async operations
- Comprehensive error handling
- Sortable, filterable results

## 📊 Confidence Tiers

| Tier | Score | Color | Description |
|------|-------|-------|-------------|
| Exact Match | 90-100% | 🟢 Green | Perfect match |
| High Confidence | 80-89% | 🔵 Blue | Very likely match |
| Good Match | 70-79% | 🔵 Cyan | Probable match |
| Likely Match | 60-69% | 🟡 Yellow | Possible match |
| Manual Review | 50-59% | 🟠 Orange | Needs review |
| No Match | <50% | 🔴 Red | Poor match |

## 🔧 Configuration

### Environment Variables

Create `apps/web/.env.local`:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
```

### Backend Integration

The frontend expects a backend API with these endpoints:

```
GET    /api/jobs              # List jobs
GET    /api/jobs/{id}         # Get job details
POST   /api/jobs              # Create job
POST   /api/jobs/{id}/run     # Run job
DELETE /api/jobs/{id}         # Delete job
GET    /api/jobs/{id}/matches # Get matches
PUT    /api/matches/{id}      # Update match status
GET    /api/stats             # Get statistics
```

## 🚀 Deployment

### Vercel (Recommended)

```bash
cd apps/web
vercel
```

### Docker

```bash
cd apps/web
docker build -t urltourl-frontend .
docker run -p 3000:3000 urltourl-frontend
```

### Self-Hosted

```bash
cd apps/web
npm run build
npm start
```

See [`DEPLOYMENT_CHECKLIST.md`](DEPLOYMENT_CHECKLIST.md) for detailed deployment instructions.

## 📈 Development

### Project Status

- ✅ Frontend - 100% Complete
- ⏳ Backend - (Separate project)
- ⏳ Database - (Separate project)

### Build & Test

```bash
# Build for production
npm run build

# Run production build
npm start

# Lint code
npm run lint
```

## 🎯 Use Cases

1. **Price Comparison** - Match products to compare prices across sites
2. **Inventory Matching** - Sync products between your stores
3. **Competitive Analysis** - Track competitor product offerings
4. **Dropshipping** - Match supplier products to your store
5. **Product Research** - Find similar products across marketplaces

## 🤝 Contributing

1. Follow existing code structure and patterns
2. Use TypeScript for all new files
3. Add loading and error states
4. Test dark mode and responsive design
5. Update documentation for new features

## 📝 License

MIT

## 🎊 Status

**Frontend**: ✅ Production Ready
**Last Updated**: 2026-01-08
**Version**: 1.0.0

---

**Built with**: Next.js 14 + TypeScript + Tailwind CSS
**Ready to**: Deploy to production and start matching products!
