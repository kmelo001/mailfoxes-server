# Update "Exct - Auto" Display Name

This script will update the display name of "Exct - Auto" to "Stansberry Research - Free" in the mailfoxes-server database.

## What This Script Does

The `update_exct_display_name.py` script:

1. Shows all email sources in the database with their IDs, names, and display names
2. Searches for an exact match for "Exct - Auto"
3. If found, updates it to "Stansberry Research - Free" and verifies the change
4. If not found, shows potential matches and provides instructions for manual update

## Running on Render.com

To run this script on your production server:

1. Log in to your Render.com account
2. Navigate to the mailfoxes-server service
3. Click on the "Shell" tab
4. Upload the script using the file upload feature or by copying and pasting the content
5. Run the script:
   ```
   python update_exct_display_name.py
   ```

## What to Expect

The script will show you:
- All email sources in the database
- Whether it found an exact match for "Exct - Auto"
- What changes it's making (if any)
- Verification that the changes were made

If the script doesn't find an exact match, it will show potential matches and provide instructions for updating a specific record by ID:

```
python update_exct_display_name.py <id>
```

Where `<id>` is the ID of the record you want to update.

## Verification

After running the script, verify the changes by visiting:
- https://mailfoxes-server.onrender.com/inbox
- https://mailfoxes-server.onrender.com/emails/view

The display name should now show as "Stansberry Research - Free" instead of "Exct - Auto".

## Troubleshooting

If you encounter any issues:
1. Check the output of the script for error messages
2. Verify that the DATABASE_URL environment variable is set correctly
3. If no matches are found, use the broader search results to identify the correct record
