# URL-to-URL Product Matcher - Frontend

A modern, professional Next.js 14 frontend for the AI-powered product matching application.

## Features

- **Dashboard**: Overview with statistics and recent jobs
- **Jobs Management**: Create, view, and manage product matching jobs
- **Real-time Updates**: Auto-refresh for active jobs with progress tracking
- **Match Review**: Sortable, filterable table for reviewing product matches
- **Dark Mode**: Full dark mode support with Tailwind CSS
- **Responsive Design**: Mobile-first, responsive layout
- **Professional UI**: Clean, modern interface with loading states and error handling

## Tech Stack

- **Next.js 14** - React framework with App Router
- **TypeScript** - Type-safe development
- **Tailwind CSS** - Utility-first styling with dark mode
- **Lucide React** - Beautiful, consistent icons
- **Server Components** - Optimal performance with RSC

## Getting Started

### Prerequisites

- Node.js 18+ installed
- Backend API running on `http://localhost:8000` (or set `NEXT_PUBLIC_API_URL`)

### Installation

```bash
# Install dependencies
npm install

# Set up environment variables
cp .env.local.example .env.local
# Edit .env.local with your API URL
```

### Development

```bash
# Run development server
npm run dev

# Open browser
open http://localhost:3000
```

### Build for Production

```bash
# Build the application
npm run build

# Start production server
npm start
```

## Project Structure

```
apps/web/
├── src/
│   ├── app/                    # Next.js App Router pages
│   │   ├── layout.tsx         # Root layout with navigation
│   │   ├── page.tsx           # Dashboard page
│   │   ├── jobs/
│   │   │   ├── page.tsx       # Jobs list
│   │   │   ├── new/page.tsx   # Create new job
│   │   │   └── [id]/page.tsx  # Job details & matches
│   │   └── globals.css        # Global styles
│   │
│   ├── components/            # Reusable components
│   │   ├── JobCard.tsx        # Job card with status
│   │   ├── MatchTable.tsx     # Sortable match table
│   │   ├── ConfidenceBadge.tsx # Color-coded confidence tiers
│   │   ├── ProgressBar.tsx    # Progress indicator
│   │   └── LoadingSpinner.tsx # Loading states
│   │
│   └── lib/                   # Utilities and API client
│       ├── api.ts             # Backend API client
│       └── utils.ts           # Helper functions
│
├── public/                    # Static assets
├── .env.local                 # Environment variables (create this)
├── next.config.ts             # Next.js configuration
├── tailwind.config.ts         # Tailwind configuration
└── package.json               # Dependencies
```

## Environment Variables

Create a `.env.local` file in the root directory:

```env
# Backend API URL
NEXT_PUBLIC_API_URL=http://localhost:8000

# Supabase URL (if using Supabase features)
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
```

## Pages

### Dashboard (`/`)
- Overview statistics (total jobs, active jobs, completed jobs, matches)
- Recent jobs list (5 most recent)
- Quick actions (create new job)

### Jobs List (`/jobs`)
- All jobs with filtering by status
- Job cards showing progress, URLs, and stats
- Delete and run job actions

### New Job (`/jobs/new`)
- Form to create new matching job
- Source and target site URLs
- Optional categories for better matching
- Validation and error handling

### Job Details (`/jobs/[id]`)
- Job configuration and metadata
- Real-time progress tracking
- Statistics (total products, matches, match rate)
- Full match table with sorting and filtering
- Approve/reject individual matches
- Actions (run, refresh, delete)

## Components

### JobCard
Displays job information in a card format:
- Job name and status badge
- Source and target URLs
- Categories (if specified)
- Progress bar (for active jobs)
- Stats (products, matches)
- Actions (run, delete)

### MatchTable
Sortable, filterable table of product matches:
- Source and target product info with links
- Match score (0-100%)
- Confidence tier badge (color-coded)
- Match status (pending/approved/rejected)
- Approve/reject buttons
- Sort by score, confidence, status
- Filter by match status

### ConfidenceBadge
Color-coded badge for confidence tiers:
- **Exact Match** - Green
- **High Confidence** - Blue
- **Good Match** - Cyan
- **Likely Match** - Yellow
- **Manual Review** - Orange
- **No Match** - Red

### ProgressBar
Progress indicator for crawling/matching jobs:
- Percentage display
- Smooth animations
- Optional label

## API Integration

The frontend communicates with the FastAPI backend through `/src/lib/api.ts`:

```typescript
// Example usage
import { api } from '@/lib/api';

// Create a new job
const job = await api.jobs.create({
  name: 'My Job',
  site1_url: 'https://site1.com/products',
  site2_url: 'https://site2.com/items',
});

// Get job details
const jobDetails = await api.jobs.get(jobId);

// Get matches for a job
const matches = await api.jobs.matches(jobId);

// Approve a match
await api.matches.update(matchId, 'approved');
```

## Styling

The app uses Tailwind CSS with:
- Dark mode support (class-based)
- Consistent color palette
- Responsive breakpoints
- Custom utility classes
- Professional shadows and borders

### Dark Mode
Dark mode is enabled by default and respects system preferences. Toggle by adding/removing the `dark` class on the `<html>` element.

## Performance Optimizations

- **Server Components** - Default to Server Components for optimal performance
- **Dynamic Imports** - Code splitting for better load times
- **Image Optimization** - Next.js Image component (when needed)
- **Auto-refresh** - Efficient polling for active jobs only
- **Optimistic Updates** - Immediate UI updates for better UX

## Best Practices

### Error Handling
All API calls include try-catch blocks with user-friendly error messages:
```typescript
try {
  const data = await api.jobs.get(id);
} catch (err) {
  setError(err instanceof Error ? err.message : 'Failed to load data');
}
```

### Loading States
Every async operation shows a loading state:
- Page-level: `<LoadingPage />`
- Component-level: `<LoadingSpinner />`
- Button-level: Disabled state with spinner

### Type Safety
Full TypeScript coverage with strict mode:
- Typed API responses
- Type-safe props
- Inferred types from API

## Troubleshooting

### API Connection Issues
If you see connection errors:
1. Ensure backend is running on `http://localhost:8000`
2. Check `NEXT_PUBLIC_API_URL` in `.env.local`
3. Verify CORS settings in backend

### Build Errors
If build fails:
```bash
# Clear Next.js cache
rm -rf .next

# Reinstall dependencies
rm -rf node_modules package-lock.json
npm install

# Try building again
npm run build
```

### Dark Mode Issues
If dark mode isn't working:
1. Check `className="dark"` on `<html>` in `layout.tsx`
2. Verify Tailwind config has `darkMode: "class"`
3. Ensure `globals.css` has dark mode styles

## Contributing

1. Follow the existing code structure
2. Use TypeScript for type safety
3. Add loading and error states
4. Test dark mode
5. Follow Tailwind CSS conventions
6. Keep components small and focused

## License

MIT
