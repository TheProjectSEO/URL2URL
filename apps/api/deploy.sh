#!/bin/bash
# URL-to-URL API Deployment Script for Railway
# Run: ./deploy.sh

set -e

echo "============================================================"
echo "URL-TO-URL PRODUCT MATCHING API - RAILWAY DEPLOYMENT"
echo "============================================================"

# Check Railway CLI
if ! command -v railway &> /dev/null; then
    echo "Installing Railway CLI..."
    npm install -g @railway/cli
fi

echo ""
echo "Step 1: Login to Railway"
echo "========================"
railway login

echo ""
echo "Step 2: Initialize/Link Project"
echo "================================"
if [ ! -f ".railway" ]; then
    echo "Creating new Railway project..."
    railway init
fi

echo ""
echo "Step 3: Set Environment Variables"
echo "=================================="
echo "Setting SUPABASE_KEY..."
railway variables set SUPABASE_KEY="${SUPABASE_KEY:-eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InF5anpxenFxamltaXR0bHR0dHBoIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjEwNTk5OTksImV4cCI6MjA3NjYzNTk5OX0.YQA0wSqdri73o6WW4-BZl0i8oKlMNcj702nAZvWkR9o}"

echo "Setting PYTHON_ENV=production..."
railway variables set PYTHON_ENV=production

echo ""
echo "Step 4: Deploy"
echo "=============="
railway up --detach

echo ""
echo "Step 5: Get Deployment URL"
echo "=========================="
railway domain

echo ""
echo "============================================================"
echo "DEPLOYMENT COMPLETE!"
echo "============================================================"
echo ""
echo "Next steps:"
echo "1. Copy the deployment URL"
echo "2. Update frontend API_URL to point to Railway"
echo "3. Test: curl <railway-url>/api/health"
