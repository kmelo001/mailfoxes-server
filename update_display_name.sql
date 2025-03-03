-- SQL command to update the display name of "Exct- Auto" to "Stansberry Research - Free"
UPDATE email_sources 
SET display_name = 'Stansberry Research - Free' 
WHERE display_name = 'Exct- Auto';

-- If the exact match doesn't work, try a pattern match
-- UPDATE email_sources 
-- SET display_name = 'Stansberry Research - Free' 
-- WHERE display_name LIKE '%Exct%Auto%';
