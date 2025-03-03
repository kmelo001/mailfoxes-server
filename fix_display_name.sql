-- SQL script to fix the display name of "Exct - Auto" to "Stansberry Research - Free"

-- First, let's see what we're working with
SELECT id, name, email_address, display_name 
FROM email_sources 
WHERE display_name LIKE '%Exct%' OR display_name LIKE '%Auto%';

-- Update with exact match (if you're sure of the format)
UPDATE email_sources 
SET display_name = 'Stansberry Research - Free' 
WHERE display_name = 'Exct - Auto';

-- If the exact match doesn't work, try this pattern match
-- This will match any display name containing "Exct" followed by "Auto"
UPDATE email_sources 
SET display_name = 'Stansberry Research - Free' 
WHERE display_name LIKE '%Exct%Auto%';

-- Verify the update
SELECT id, name, email_address, display_name 
FROM email_sources 
WHERE display_name = 'Stansberry Research - Free';

-- If all else fails, here's how to update by ID
-- (Replace XX with the actual ID number from the first query)
-- UPDATE email_sources 
-- SET display_name = 'Stansberry Research - Free' 
-- WHERE id = XX;
