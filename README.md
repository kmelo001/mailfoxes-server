# Mailfoxes Server

Email analytics dashboard for tracking and analyzing emails from various sources.

## Live Application

The application is deployed and accessible at:
- [https://mailfoxes-server.onrender.com/inbox](https://mailfoxes-server.onrender.com/inbox)

## Environment Variables

For security reasons, sensitive information like database credentials should be stored as environment variables rather than hardcoded in the application. The following environment variables are used:

- `DATABASE_URL`: Connection string for the PostgreSQL database (required in production)
- `API_TOKEN`: Authentication token for API endpoints (required for API access)

## Setting Environment Variables

### Temporary (Session Only)

To set environment variables for the current terminal session:

```bash
# Set the database URL
export DATABASE_URL="postgresql://username:password@host:port/database_name"

# Set the API token
export API_TOKEN="your-secret-token"
```

### Permanent (Development)

For development, you can add these to your shell profile (~/.bashrc, ~/.zshrc, etc.):

```bash
# Add to your shell profile
echo 'export DATABASE_URL="postgresql://username:password@host:port/database_name"' >> ~/.zshrc
echo 'export API_TOKEN="your-secret-token"' >> ~/.zshrc
```

### Production (Render)

In production on Render:

1. Go to your Render dashboard
2. Select your web service
3. Go to the "Environment" tab
4. Add the environment variables there

## Running the Application

Start the Flask application:

```bash
python app.py
```

## Utility Scripts

### Count Emails

To count the total number of emails in the database:

```bash
# Make sure DATABASE_URL is set
python count_emails.py
```

## Security Considerations

- Never commit sensitive credentials to version control
- Regularly rotate API tokens and database passwords
- Use HTTPS for all production traffic
- Implement proper authentication for user access

## Features in Development

### AI Email Search (Beta)

A new AI-powered email search feature has been implemented that allows users to search and analyze emails using natural language queries. This feature is currently in beta testing and is not yet available on the home page.

#### Key Features:
- Search emails from the past 7 days using natural language queries
- Filter search by email source
- Two analysis modes:
  - **Search Mode**: Standard analysis providing basic insights
  - **Deep Research Mode**: Comprehensive analysis with detailed insights

#### Technical Implementation:
- Frontend: Modern search interface with source selection and mode options
- Backend: Flask API endpoint that retrieves emails and processes them with LLM
- LLM Integration: Uses DeepSeek API for email analysis
- Token Management: Implements token counting to handle large email volumes
- Caching: Caches analysis results to improve performance

#### How to Access:
The feature is accessible at `/email-search` but is not linked from the home page during testing.

#### Future Improvements:
- Streaming responses for faster feedback
- Enhanced analysis capabilities
- Better error handling and fallbacks
- UI refinements based on user feedback
