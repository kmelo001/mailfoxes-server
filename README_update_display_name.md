# Update Display Name Script

This repository contains scripts to update the display name of "Exc - Auto" to "Stansberry Research - Free" in the mailfoxes-server database.

## Background

The mailfoxes-server automatically creates display names for new email sources. When emails come from unknown sources, it creates a display name based on the domain name with " - Auto" appended. For example, emails from "exc.something" would get a display name of "Exc - Auto".

This script updates any email sources with "Exc" in the display name to use "Stansberry Research - Free" instead.

## Deployment Instructions

Since the script needs to connect to the production database, it needs to be run on the server where the app is deployed (or with access to the production database).

### Option 1: Run on Render.com (Recommended)

If the app is deployed on Render.com, you can use the Render Shell to run the script:

1. Log in to your Render.com account
2. Navigate to the mailfoxes-server service
3. Click on the "Shell" tab
4. Upload the script using the file upload feature or by copying and pasting the content
5. Run the script with:
   ```
   python update_exc_to_stansberry.py
   ```

### Option 2: Run Locally with Production Database Access

If you have access to the production database from your local machine:

1. Set the DATABASE_URL environment variable to point to the production database:
   ```
   export DATABASE_URL="your-production-database-url"
   ```
2. Run the script:
   ```
   python update_exc_to_stansberry.py
   ```

## Verification

After running the script, you can verify the changes by:

1. Visiting https://mailfoxes-server.onrender.com/inbox
2. Checking that "Exc - Auto" is now displayed as "Stansberry Research - Free"
3. Also verify on https://mailfoxes-server.onrender.com/emails/view

## Troubleshooting

If you encounter any issues:

1. Make sure the DATABASE_URL environment variable is correctly set
2. Check that the database user has permission to update the email_sources table
3. If no sources are found, try modifying the search query in the script to use a different pattern
