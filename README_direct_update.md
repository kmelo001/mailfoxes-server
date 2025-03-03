# Direct Display Name Update

This file contains instructions for directly updating the display name of "Exct- Auto" to "Stansberry Research - Free" in the mailfoxes-server database.

## The Script

The `update_display_name_direct.py` script will:

1. Connect to the database using the DATABASE_URL environment variable
2. Execute an SQL UPDATE command to change the display name
3. If no exact matches are found, try a pattern match
4. Commit the changes to the database
5. Report the number of rows affected

## Running on Render.com (Recommended)

Since the script needs to connect to the production database, it should be run on the server where the app is deployed:

1. Log in to your Render.com account
2. Navigate to the mailfoxes-server service
3. Click on the "Shell" tab
4. Upload the script using the file upload feature or by copying and pasting the content
5. Make the script executable:
   ```
   chmod +x update_display_name_direct.py
   ```
6. Run the script:
   ```
   python update_display_name_direct.py
   ```

## Verification

After running the script, verify the changes by visiting:
1. https://mailfoxes-server.onrender.com/inbox
2. https://mailfoxes-server.onrender.com/emails/view

The display name should now show as "Stansberry Research - Free" instead of "Exct- Auto".

## Troubleshooting

If the script doesn't update any rows:

1. The display name might be slightly different than "Exct- Auto"
2. You can check the exact display name with this SQL query:
   ```sql
   SELECT id, name, email_address, display_name 
   FROM email_sources 
   WHERE display_name LIKE '%Exct%' OR display_name LIKE '%Auto%';
   ```
3. Then update the script with the exact display name
