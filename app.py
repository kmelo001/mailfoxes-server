from flask import Flask, request, jsonify, render_template, Response, redirect
from datetime import datetime
import os
import re
import psycopg2
from psycopg2.extras import DictCursor
import json
from functools import wraps

app = Flask(__name__)

# Add API authentication token
API_TOKEN = os.environ.get('API_TOKEN')

def get_db_connection():
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        # For local development, use a default PostgreSQL connection string
        # This ensures consistent behavior between development and production
        print("DATABASE_URL not set. Using default PostgreSQL connection string.")
        database_url = "postgresql://postgres:postgres@localhost:5432/mailfoxes"
    
    # Always use PostgreSQL
    conn = psycopg2.connect(database_url)
    return conn

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token or token != f"Bearer {API_TOKEN}":
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    
    # PostgreSQL version
    cur.execute('''
        CREATE TABLE IF NOT EXISTS email_sources (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            email_address TEXT NOT NULL UNIQUE,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            display_name TEXT,
            parent_id INTEGER NULL REFERENCES email_sources(id),
            hidden BOOLEAN DEFAULT FALSE
        );
    ''')
    
    # Check if emails table exists
    cur.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_name = 'emails'
        );
    """)
    table_exists = cur.fetchone()[0]
    
    if not table_exists:
        # Create new emails table with source_id
        cur.execute('''
            CREATE TABLE emails (
                id SERIAL PRIMARY KEY,
                source_id INTEGER REFERENCES email_sources(id),
                to_address TEXT,
                from_address TEXT,
                subject TEXT,
                body_text TEXT,
                body_html TEXT,
                urls TEXT[],
                received_at TIMESTAMP,
                processed BOOLEAN DEFAULT FALSE,
                spam_score FLOAT
            );
        ''')
    else:
        # Add processed column if it doesn't exist
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.columns 
                WHERE table_name = 'emails' AND column_name = 'processed'
            );
        """)
        column_exists = cur.fetchone()[0]
        
        if not column_exists:
            cur.execute('ALTER TABLE emails ADD COLUMN processed BOOLEAN DEFAULT FALSE;')
            
        # Add spam_score column if it doesn't exist
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.columns 
                WHERE table_name = 'emails' AND column_name = 'spam_score'
            );
        """)
        column_exists = cur.fetchone()[0]
        
        if not column_exists:
            cur.execute('ALTER TABLE emails ADD COLUMN spam_score FLOAT;')
    
    # Create indexes
    cur.execute('''
        CREATE INDEX IF NOT EXISTS idx_sources_email 
        ON email_sources(email_address);
    ''')
    
    cur.execute('''
        CREATE INDEX IF NOT EXISTS idx_emails_source_date 
        ON emails(source_id, received_at DESC);
    ''')
    
    # Check if display_name column exists
    cur.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.columns 
            WHERE table_name = 'email_sources' AND column_name = 'display_name'
        );
    """)
    column_exists = cur.fetchone()[0]
    
    if not column_exists:
        cur.execute('ALTER TABLE email_sources ADD COLUMN display_name TEXT;')
        
    # Check if parent_id column exists
    cur.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.columns 
            WHERE table_name = 'email_sources' AND column_name = 'parent_id'
        );
    """)
    column_exists = cur.fetchone()[0]
    
    if not column_exists:
        cur.execute('ALTER TABLE email_sources ADD COLUMN parent_id INTEGER NULL REFERENCES email_sources(id);')
        
    # Check if hidden column exists
    cur.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.columns 
            WHERE table_name = 'email_sources' AND column_name = 'hidden'
        );
    """)
    column_exists = cur.fetchone()[0]
    
    if not column_exists:
        cur.execute('ALTER TABLE email_sources ADD COLUMN hidden BOOLEAN DEFAULT FALSE;')
    
    # First make sure all sources exist in the database
    # Update display names based on the spreadsheet data
    display_names = {
        1: "InvestorPlace - Free",
        2: "Marketbeat - Free",
        3: "Weiss Ratings - Free",
        4: "Brownstone Research - Free",
        5: "Wyatt Research - Free",
        6: "Banyan Hill - Free",
        7: "Tim Sykes - Paid",
        8: "Tim Sykes - Paid",
        9: "Banyan Hill - Free",
        10: "Paradigm Press - Free",
        11: "Paradigm Press - Free",
        12: "Angel Pub - Wealth Daily - Free",
        13: "Angel Pub - Energy Capital - Free",
        14: "Agora - MoneyMorning - Free",
        15: "Tradesmith - Free",
        16: "Daily Strike Alliance - Free",
        17: "Tradesmith - Free",
        18: "Tradesmith - Free",
        19: "Widemoat Research - Free",
        20: "Paradigm Press - Free",
        21: "Paradigm Press - Free",
        22: "Marketbeat - Free",
        23: "Southbank Research (UK) - AI Collision - Free",
        24: "Fat Tail Research (AUS) - Free",
        25: "Agora France - Free",
        26: "Omnia Research - Opportunistic Trader - Free",
        27: "Porter and Co - Free",
        28: "Oxford Club - Comunique - Paid",
        29: "Oxford Club - Comunique - Paid",
        30: "Teeka Tiwari - Free",
        31: "Weiss Ratings - Free",
        32: "Paradigm Press - Free"
    }
    
    # Make sure all sources exist in the database
    for source_id, display_name in display_names.items():
        # Check if the source exists
        cur.execute("SELECT COUNT(*) FROM email_sources WHERE id = %s", (source_id,))
        count = cur.fetchone()[0]
        
        if count == 0:
            # Source doesn't exist, create it with a placeholder email address
            placeholder_email = f"source{source_id}@mailfoxes.com"
            cur.execute(
                "INSERT INTO email_sources (id, name, email_address, display_name) VALUES (%s, %s, %s, %s)",
                (source_id, display_name, placeholder_email, display_name)
            )
        else:
            # Source exists, update its display name if needed
            cur.execute(
                "UPDATE email_sources SET display_name = %s WHERE id = %s AND (display_name IS NULL OR display_name = '')",
                (display_name, source_id)
            )
    
    # Now that all sources exist, set up inbox consolidations
    try:
        # 1. Marketbeat Duplicates (IDs 2 and 22)
        cur.execute("UPDATE email_sources SET parent_id = 2, hidden = TRUE WHERE id = 22")
        
        # 2. Banyan Hill Duplicates (IDs 6 and 9)
        cur.execute("UPDATE email_sources SET parent_id = 6, hidden = TRUE WHERE id = 9")
        
        # 3. Tradesmith Duplicates (IDs 15, 17 and 18)
        cur.execute("UPDATE email_sources SET parent_id = 17, hidden = TRUE WHERE id IN (15, 18)")
        
        # 4. Paradigm Press Inboxes (IDs 10, 11, 20, 21, and 32)
        cur.execute("UPDATE email_sources SET parent_id = 10, hidden = TRUE WHERE id IN (11, 20, 21, 32)")
        
        # 5. Weiss Ratings Duplicates (IDs 3 and 31)
        cur.execute("UPDATE email_sources SET parent_id = 3, hidden = TRUE WHERE id = 31")
        
        # 6. Hide paid sources
        cur.execute("UPDATE email_sources SET hidden = TRUE WHERE id IN (7, 8, 28, 29)")
    except Exception as e:
        print(f"Error setting up inbox consolidations: {str(e)}")
        # Continue with the rest of the initialization
    
    conn.commit()
    cur.close()
    conn.close()

def extract_urls(text):
    """Extract URLs from text or HTML using a regex."""
    if not text:
        return []
    url_pattern = r'http[s]?://(?:[a-zA-Z0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
    return re.findall(url_pattern, text)

def process_email_html(html_content):
    """Add target="_blank" to all links in the email HTML content."""
    if not html_content:
        return html_content
    
    # Use a regular expression to find all <a> tags and add target="_blank"
    pattern = r'<a\s+(?:[^>]*?\s+)?href="([^"]*)"([^>]*)>'
    replacement = r'<a href="\1" target="_blank" rel="noopener noreferrer"\2>'
    processed_html = re.sub(pattern, replacement, html_content)
    
    return processed_html

def get_spam_score(email_content):
    """Get spam score using the spamcheck library."""
    try:
        import spamcheck
        
        # We only need the score, not the full report
        result = spamcheck.check(email_content, report=False)
        return result['score']
    except ImportError:
        print("spamcheck library not installed. Install with: pip install spamcheck")
        return 0
    except Exception as e:
        print(f"Error checking spam score: {str(e)}")
        return 0  # Default score if API call fails

def process_email_data(email_dict):
    """Process email data to add computed fields."""
    if isinstance(email_dict['received_at'], str):
        email_dict['received_at'] = datetime.strptime(email_dict['received_at'], '%Y-%m-%d %H:%M:%S.%f')
    
    # Ensure URLs field is initialized
    if 'urls' not in email_dict:
        email_dict['urls'] = []
    
    # Process HTML content to add target="_blank" to links
    if 'body_html' in email_dict and email_dict['body_html']:
        email_dict['body_html'] = process_email_html(email_dict['body_html'])
    
    # Add computed fields
    email_dict['subject_length'] = len(email_dict['subject']) if email_dict['subject'] else 0
    
    # Calculate word count - if body_text is empty but body_html exists, extract text from HTML
    if not email_dict.get('body_text') and email_dict.get('body_html'):
        try:
            # Extract text from HTML (removing HTML tags)
            from bs4 import BeautifulSoup
            
            # Check if this is an analystratines.net email
            is_analystratines = False
            if 'from_address' in email_dict and email_dict['from_address']:
                if 'analystratines.net' in email_dict['from_address'].lower():
                    is_analystratines = True
                    print(f"Processing analystratines.net email: {email_dict.get('subject', 'No Subject')}")
            
            # Parse HTML and extract text
            text_from_html = BeautifulSoup(email_dict['body_html'], 'html.parser').get_text(separator=' ', strip=True)
            
            # Count words
            word_count = len(text_from_html.split())
            email_dict['word_count'] = word_count
            
            if is_analystratines:
                print(f"Extracted {word_count} words from HTML content")
                
        except ImportError:
            print("BeautifulSoup not installed. Install with: pip install beautifulsoup4")
            email_dict['word_count'] = 0
        except Exception as e:
            print(f"Error extracting text from HTML: {str(e)}")
            email_dict['word_count'] = 0
    else:
        email_dict['word_count'] = len(email_dict['body_text'].split()) if email_dict['body_text'] else 0
    
    email_dict['link_count'] = len(email_dict['urls']) if email_dict['urls'] else 0
    email_dict['share_url'] = f"/emails/view/{email_dict['id']}"
    
    # Ensure spam_score is available
    if 'spam_score' not in email_dict or email_dict['spam_score'] is None:
        email_dict['spam_score'] = 0
    
    return email_dict

@app.route('/')
def home():
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=DictCursor)
        
        # Get total emails
        cur.execute("SELECT COUNT(*) FROM emails")
        total_emails = cur.fetchone()[0]
        
        # Get email sources count (non-hidden)
        cur.execute("SELECT COUNT(*) FROM email_sources WHERE hidden = FALSE OR hidden IS NULL")
        source_count = cur.fetchone()[0]
        
        # Get emails by day for the last 30 days
        cur.execute("""
            SELECT 
                DATE_TRUNC('day', received_at) AS day,
                COUNT(*) AS email_count
            FROM emails
            WHERE received_at >= NOW() - INTERVAL '30 days'
            GROUP BY DATE_TRUNC('day', received_at)
            ORDER BY day
        """)
        
        email_timeline = cur.fetchall()
        
        # Get average spam score
        cur.execute("SELECT AVG(spam_score) FROM emails WHERE spam_score IS NOT NULL")
        avg_spam_score = cur.fetchone()[0] or 0
        
        # Close connection
        cur.close()
        conn.close()
        
        # Format data for template - ensure all data is JSON serializable
        labels = []
        values = []
        
        for row in email_timeline:
            # Convert datetime objects to strings to ensure JSON serializability
            if row['day']:
                formatted_date = row['day'].strftime('%b %d')
            else:
                formatted_date = 'Unknown'
                
            # Ensure count is a simple integer, not a database-specific type
            email_count = int(row['email_count']) if row['email_count'] is not None else 0
            
            labels.append(formatted_date)
            values.append(email_count)
        
        # Pre-serialize the data to JSON strings
        labels_json = json.dumps(labels)
        values_json = json.dumps(values)
        
        # Ensure avg_spam_score is a simple float
        avg_spam_score = float(round(avg_spam_score, 2)) if avg_spam_score is not None else 0.0
        
        return render_template('home.html', 
                             total_emails=int(total_emails) if total_emails is not None else 0,
                             source_count=int(source_count) if source_count is not None else 0,
                             avg_spam_score=avg_spam_score,
                             labels_json=labels_json,
                             values_json=values_json)
                             
    except Exception as e:
        print(f"Error: {str(e)}")
        return str(e), 500

@app.route('/sources/add', methods=['POST'])
def add_source():
    """Add a new email source."""
    try:
        name = request.form.get('name')
        email = request.form.get('email')
        description = request.form.get('description')
        display_name = request.form.get('display_name', name)  # Default to name if not provided
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # PostgreSQL supports ON CONFLICT
        cur.execute('''
            INSERT INTO email_sources (name, email_address, description, display_name)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (email_address) DO UPDATE 
            SET name = EXCLUDED.name,
                description = EXCLUDED.description,
                display_name = EXCLUDED.display_name
            RETURNING id
        ''', (name, email, description, display_name))
        new_id = cur.fetchone()[0]
        
        conn.commit()
        cur.close()
        conn.close()
        
        return redirect(f'/emails/view?source={new_id}')
        
    except Exception as e:
        return str(e), 500

@app.route('/sources/delete/<int:source_id>', methods=['POST'])
def delete_source(source_id):
    """Delete an email source."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # First update emails to remove the source_id
        cur.execute('UPDATE emails SET source_id = NULL WHERE source_id = %s', (source_id,))
        
        # Then delete the source
        cur.execute('DELETE FROM email_sources WHERE id = %s', (source_id,))
        
        conn.commit()
        cur.close()
        conn.close()
        
        return redirect('/emails/view')
        
    except Exception as e:
        return str(e), 500

@app.route('/api/unprocessed-emails')
@token_required
def get_unprocessed_emails():
    """API endpoint to fetch unprocessed emails"""
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=DictCursor)
        
        cur.execute('''
            SELECT id, urls, body_html, received_at 
            FROM emails 
            WHERE processed = FALSE
            ORDER BY received_at DESC
        ''')
        
        emails = [dict(email) for email in cur.fetchall()]
        cur.close()
        conn.close()
        
        return jsonify(emails)
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/mark-processed/<int:email_id>', methods=['POST'])
@token_required
def mark_email_processed(email_id):
    """API endpoint to mark email as processed"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute('''
            UPDATE emails 
            SET processed = TRUE 
            WHERE id = %s
        ''', (email_id,))
        
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({"status": "success"})
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/sources/details')
def source_details():
    """API endpoint to show detailed information about all sources"""
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=DictCursor)
        
        # PostgreSQL version
        cur.execute('''
            SELECT id, name, email_address, description, display_name, parent_id 
            FROM email_sources 
            WHERE hidden = FALSE OR hidden IS NULL
            ORDER BY display_name NULLS LAST, name
        ''')
            
        sources = [dict(source) for source in cur.fetchall()]
        
        cur.close()
        conn.close()
        
        return jsonify(sources)
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/parse-email', methods=['POST'])
def parse_email():
    print("==== Incoming SendGrid Parsed Email ====")
    print("Form data:", dict(request.form))

    try:
        # Get SendGrid's parsed fields
        to_addr = request.form.get('to', '')
        from_addr = request.form.get('from', '')
        subject = request.form.get('subject', '')
        text_body = request.form.get('text', '')
        html_body = request.form.get('html', '')
        
        # For forwarded emails, prefer HTML as it contains the forwarding format
        if html_body:
            email_body = html_body
        else:
            email_body = text_body
        
        # Extract URLs from text content first, fall back to HTML if no text
        extracted_urls = extract_urls(text_body) if text_body else extract_urls(html_body)
        
        # Ensure URLs are properly serialized for PostgreSQL array
        # Convert the list to a proper PostgreSQL array format
        urls_array = extracted_urls if extracted_urls else []
        
        # Calculate spam score
        raw_email = f"From: {from_addr}\nTo: {to_addr}\nSubject: {subject}\n\n{text_body}"
        spam_score = get_spam_score(raw_email)

        # Find the source based on the to_address
        conn = get_db_connection()
        cur = conn.cursor()
        
        # First check if we have a source for this email address
        cur.execute('SELECT id FROM email_sources WHERE email_address = %s', (to_addr,))
        source_result = cur.fetchone()
        source_id = source_result[0] if source_result else None
        
        # If no source exists, create one automatically
        if not source_id:
            # Create a display name from the domain
            domain = from_addr.split('@')[1]
            display_name = domain.split('.')[0].capitalize()
            if display_name.endswith('>'):
                display_name = display_name[:-1]  # Remove trailing '>' if present
            display_name += " - Auto"
            
            cur.execute('''
                INSERT INTO email_sources (name, email_address, description, display_name)
                VALUES (%s, %s, %s, %s)
                RETURNING id
            ''', (domain, to_addr, f'Auto-created from {from_addr}', display_name))
            source_id = cur.fetchone()[0]

        # Insert into database
        cur.execute('''
            INSERT INTO emails (
                source_id, to_address, from_address, subject, body_text, body_html, urls, received_at, spam_score
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (
            source_id,
            to_addr,
            from_addr,
            subject,
            text_body,
            email_body,
            urls_array,
            datetime.now(),
            spam_score
        ))
        new_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()

        print(f"Processed email: {subject}")
        return jsonify({"status": "success", "id": new_id}), 200

    except Exception as e:
        print(f"Error processing email: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/inbox')
def new_inbox():
    """Render the new inbox page."""
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=DictCursor)
        
        # Get all non-hidden sources
        cur.execute('''
            SELECT * FROM email_sources 
            WHERE hidden = FALSE OR hidden IS NULL
            ORDER BY display_name NULLS LAST, name
        ''')
            
        sources = cur.fetchall()
        
        # Get current source from query params or default to 'all'
        current_source = request.args.get('source', 'all')
        if current_source != 'all':
            current_source = int(current_source)
        
        # Get filter parameters
        competitor = request.args.get('competitor', 'all')
        tag = request.args.get('tag', '-')
        keyword_type = request.args.get('keyword_type', 'subject')
        keyword = request.args.get('keyword', '')
        start_date = request.args.get('start_date', '')
        end_date = request.args.get('end_date', '')
        
        # Build query based on filters
        query = 'SELECT e.*, s.name as source_name, s.display_name FROM emails e LEFT JOIN email_sources s ON e.source_id = s.id'
        params = []
        where_clauses = []
        
        # Add source/competitor filter
        if competitor != 'all':
            where_clauses.append('e.source_id = %s')
            params.append(int(competitor))
        
        # Add keyword filter
        if keyword:
            if keyword_type == 'subject':
                where_clauses.append('e.subject ILIKE %s')
                params.append(f'%{keyword}%')
            elif keyword_type == 'body':
                where_clauses.append('e.body_text ILIKE %s')
                params.append(f'%{keyword}%')
            else:  # All fields
                where_clauses.append('(e.subject ILIKE %s OR e.body_text ILIKE %s)')
                params.append(f'%{keyword}%')
                params.append(f'%{keyword}%')
        
        # Add date filters
        if start_date:
            where_clauses.append('e.received_at >= %s')
            params.append(start_date)
        
        if end_date:
            # Add 1 day to end_date to include the entire end date
            where_clauses.append('e.received_at < (%s::date + INTERVAL \'1 day\')')
            params.append(end_date)
        
        # Combine where clauses
        if where_clauses:
            query += ' WHERE ' + ' AND '.join(where_clauses)
        
        # Add order and limit
        query += ' ORDER BY e.received_at DESC LIMIT 100'
        
        # Execute query
        cur.execute(query, params)
        emails = cur.fetchall()
        
        # Close connection
        cur.close()
        conn.close()
        
        # Process emails
        emails_list = [process_email_data(dict(email)) for email in emails]
        sources_list = [dict(source) for source in sources]
        
        # Calculate email count for display
        email_count = len(emails_list)
        email_count_display = f"1-{email_count} (of {email_count})" if email_count > 0 else "0 (of 0)"
        
        return render_template('new_inbox.html',
                             emails=emails_list,
                             sources=sources_list,
                             current_source=current_source,
                             email_count=email_count_display)
    
    except Exception as e:
        print(f"Error: {str(e)}")
        return str(e), 500

@app.route('/emails/view')
def view_emails_html():
    """Render the main email dashboard."""
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=DictCursor)
        
        # Get all non-hidden sources
        cur.execute('''
            SELECT * FROM email_sources 
            WHERE hidden = FALSE OR hidden IS NULL
            ORDER BY display_name NULLS LAST, name
        ''')
            
        sources = cur.fetchall()
        
        # Get current source from query params or default to 'all'
        current_source = request.args.get('source', 'all')
        if current_source != 'all':
            current_source = int(current_source)
        
        sort = request.args.get('sort', 'newest')
        limit = request.args.get('limit', '10')
        time_filter = request.args.get('time', 'all')
        
        query = 'SELECT * FROM emails'
        params = []
        
        # Add source filter
        if current_source != 'all':
            # Get child sources (if any)
            cur.execute('SELECT id FROM email_sources WHERE parent_id = %s', (current_source,))
            child_sources = [row[0] for row in cur.fetchall()]
            
            # Include emails from both the current source and its children
            if child_sources:
                source_ids = [current_source] + child_sources
                placeholders = ', '.join(['%s'] * len(source_ids))
                query += f' WHERE source_id IN ({placeholders})'
                params.extend(source_ids)
            else:
                query += ' WHERE source_id = %s'
                params.append(current_source)
        
        if time_filter == 'week' or time_filter == 'month':
            query += ' AND ' if params else ' WHERE '
            
            # PostgreSQL version
            interval = '7 days' if time_filter == 'week' else '30 days'
            query += f"received_at >= NOW() - INTERVAL '{interval}'"
        
        query += ' ORDER BY received_at ' + ('DESC' if sort == 'newest' else 'ASC')
        query += ' LIMIT %s'
        params.append(int(limit))
        
        cur.execute(query, params)
        emails = cur.fetchall()
        cur.close()
        conn.close()

        emails_list = [process_email_data(dict(email)) for email in emails]
        sources_list = [dict(source) for source in sources]

        return render_template('emails.html', 
                             emails=emails_list,
                             sources=sources_list,
                             current_source=current_source,
                             current_sort=sort,
                             current_limit=limit,
                             current_time=time_filter)

    except Exception as e:
        print(f"Error: {str(e)}")
        return str(e), 500

@app.route('/emails/view/<int:email_id>')
def view_single_email(email_id):
    """Render a single email view."""
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=DictCursor)
        cur.execute('SELECT * FROM emails WHERE id = %s', (email_id,))
        email = cur.fetchone()
        cur.close()
        conn.close()

        if email is None:
            return "Email not found", 404

        email_dict = process_email_data(dict(email))
        
        # Only return the email content portion for AJAX requests
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return render_template('email_single.html', email=email_dict)
        
        # For direct access, return the full page with just this email
        return render_template('emails.html', 
                             emails=[email_dict],
                             current_sort='newest',
                             current_limit='10',
                             current_time='all')

    except Exception as e:
        print(f"Error: {str(e)}")
        return str(e), 500

# Initialize the database when the app starts
init_db()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=True)
