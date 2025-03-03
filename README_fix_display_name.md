# Fix Display Name Script

This script will fix the display name of "Exct - Auto" to "Stansberry Research - Free" in the mailfoxes-server database.

## What This Script Does

The `fix_display_name.py` script:

1. Connects to the database
2. Searches for entries with display names matching "Exct - Auto" or similar patterns
3. Shows you exactly what it found before making any changes
4. Updates the display names to "Stansberry Research - Free"
5. Verifies the changes were made correctly
6. If no matches are found, it shows all display names in the database so you can identify the correct one

## Running on Render.com

To run this script on your production server:

1. Log in to your Render.com account
2. Navigate to the mailfoxes-server service
3. Click on the "Shell" tab
4. Upload the script using the file upload feature or by copying and pasting the content
5. Run the script:
   ```
   python fix_display_name.py
   ```

## What to Expect

The script will show you:
- What entries it found before updating
- What changes it's making
- Verification that the changes were made
- A summary of how many entries were updated

## Verification

After running the script:

1. Visit https://mailfoxes-server.onrender.com/inbox
2. Check that "Exct - Auto" is now displayed as "Stansberry Research - Free"
3. Also verify on https://mailfoxes-server.onrender.com/emails/view

If the display name is still not updated, you may need to:
- Clear your browser cache
- Wait a few minutes for the changes to propagate
- Check if there are any caching mechanisms in the application

## Troubleshooting

If the script doesn't find any matches:
1. It will show you all display names in the database
2. Look for anything similar to "Exct - Auto" in the list
3. You can then modify the script to target the exact display name you found
