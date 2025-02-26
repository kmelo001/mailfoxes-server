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
    if database_url:
        # Production database (Render)
        conn = psycopg2.connect(database_url)
    else:
        # Local development - use SQLite
        print("DATABASE_URL not set. Using local SQLite database for development.")
        import sqlite3
        conn = sqlite3.connect('mailfoxes.db')
        conn.row_factory = sqlite3.Row
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
    
    # Check if we're using SQLite
    is_sqlite = 'sqlite3.Connection' in str(type(conn))
    
    if is_sqlite:
        # SQLite version
        cur.execute('''
            CREATE TABLE IF NOT EXISTS email_sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email_address TEXT NOT NULL UNIQUE,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                display_name TEXT
            );
        ''')
        
        # SQLite doesn't have information_schema, so we check differently
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='emails';")
        table_exists = cur.fetchone() is not None
        
        if not table_exists:
            # Create new emails table with source_id
            # SQLite doesn't support arrays, so we'll store URLs as JSON
            cur.execute('''
                CREATE TABLE emails (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id INTEGER REFERENCES email_sources(id),
                    to_address TEXT,
                    from_address TEXT,
                    subject TEXT,
                    body_text TEXT,
                    body_html TEXT,
                    urls TEXT, -- Store as JSON string
                    received_at TIMESTAMP,
                    processed BOOLEAN DEFAULT 0
                );
            ''')
        else:
            # Check if processed column exists
            cur.execute("PRAGMA table_info(emails);")
            columns = cur.fetchall()
            column_exists = any(col[1] == 'processed' for col in columns)
            
            if not column_exists:
                cur.execute('ALTER TABLE emails ADD COLUMN processed BOOLEAN DEFAULT 0;')
        
        # Create indexes
        cur.execute('CREATE INDEX IF NOT EXISTS idx_sources_email ON email_sources(email_address);')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_emails_source_date ON emails(source_id, received_at);')
        
        # Check if display_name column exists
        cur.execute("PRAGMA table_info(email_sources);")
        columns = cur.fetchall()
        column_exists = any(col[1] == 'display_name' for col in columns)
        
        if not column_exists:
            cur.execute('ALTER TABLE email_sources ADD COLUMN display_name TEXT;')
    else:
        # PostgreSQL version
        cur.execute('''
            CREATE TABLE IF NOT EXISTS email_sources (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                email_address TEXT NOT NULL UNIQUE,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                display_name TEXT
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
                    processed BOOLEAN DEFAULT FALSE
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
    
    for source_id, display_name in display_names.items():
        cur.execute(
            "UPDATE email_sources SET display_name = %s WHERE id = %s AND (display_name IS NULL OR display_name = '')",
            (display_name, source_id)
        )
    
    conn.commit()
    cur.close()
    conn.close()

def extract_urls(text):
    """Extract URLs from text or HTML using a regex."""
    if not text:
        return []
    url_pattern = r'http[s]?://(?:[a-zA-Z0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
    return re.findall(url_pattern, text)

def process_email_data(email_dict):
    """Process email data to add computed fields."""
    if isinstance(email_dict['received_at'], str):
        email_dict['received_at'] = datetime.strptime(email_dict['received_at'], '%Y-%m-%d %H:%M:%S.%f')
    
    # Handle URLs field which could be a JSON string (SQLite) or an array (PostgreSQL)
    if 'urls' in email_dict:
        if isinstance(email_dict['urls'], str) and email_dict['urls'].startswith('['):
            try:
                # Try to parse as JSON if it's a string
                email_dict['urls'] = json.loads(email_dict['urls'])
            except:
                # If parsing fails, keep as is
                pass
    else:
        email_dict['urls'] = []
    
    # Add computed fields
    email_dict['subject_length'] = len(email_dict['subject']) if email_dict['subject'] else 0
    email_dict['word_count'] = len(email_dict['body_text'].split()) if email_dict['body_text'] else 0
    email_dict['link_count'] = len(email_dict['urls']) if email_dict['urls'] else 0
    email_dict['share_url'] = f"/emails/view/{email_dict['id']}"
    
    return email_dict

@app.route('/')
def home():
    return redirect('/emails/view')

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
        
        # Check if we're using SQLite
        is_sqlite = 'sqlite3.Connection' in str(type(conn))
        
        processed_value = "0" if is_sqlite else "FALSE"
        
        cur.execute(f'''
            SELECT id, urls, body_html, received_at 
            FROM emails 
            WHERE processed = {processed_value}
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
        
        # Check if we're using SQLite
        is_sqlite = 'sqlite3.Connection' in str(type(conn))
        
        processed_value = "1" if is_sqlite else "TRUE"
        
        cur.execute(f'''
            UPDATE emails 
            SET processed = {processed_value} 
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
        
        # Check if we're using SQLite
        is_sqlite = 'sqlite3.Connection' in str(type(conn))
        
        if is_sqlite:
            # SQLite version - doesn't support NULLS LAST
            cur.execute('SELECT id, name, email_address, description, display_name FROM email_sources ORDER BY CASE WHEN display_name IS NULL THEN 1 ELSE 0 END, display_name, name')
        else:
            # PostgreSQL version
            cur.execute('SELECT id, name, email_address, description, display_name FROM email_sources ORDER BY display_name NULLS LAST, name')
            
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
        urls = extract_urls(text_body) if text_body else extract_urls(html_body)

        # Find the source based on the to_address
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Check if we're using SQLite
        is_sqlite = 'sqlite3.Connection' in str(type(conn))
        
        # For SQLite, convert URLs to JSON string
        if is_sqlite:
            urls = json.dumps(urls)
        
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
                source_id, to_address, from_address, subject, body_text, body_html, urls, received_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (
            source_id,
            to_addr,
            from_addr,
            subject,
            text_body,
            email_body,
            urls,
            datetime.now()
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

@app.route('/emails/view')
def view_emails_html():
    """Render the main email dashboard."""
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=DictCursor)
        
        # Get all sources
        # Check if we're using SQLite
        is_sqlite = 'sqlite3.Connection' in str(type(conn))
        
        if is_sqlite:
            # SQLite version - doesn't support NULLS LAST
            cur.execute('SELECT * FROM email_sources ORDER BY CASE WHEN display_name IS NULL THEN 1 ELSE 0 END, display_name, name')
        else:
            # PostgreSQL version
            cur.execute('SELECT * FROM email_sources ORDER BY display_name NULLS LAST, name')
            
        sources = cur.fetchall()
        
        # Get current source from query params or default to 'all'
        current_source = request.args.get('source', 'all')
        if current_source != 'all':
            current_source = int(current_source)
        
        sort = request.args.get('sort', 'newest')
        limit = request.args.get('limit', '10')
        time_filter = request.args.get('time', 'all')
        
        # Check if we're using SQLite
        is_sqlite = 'sqlite3.Connection' in str(type(conn))
        
        query = 'SELECT * FROM emails'
        params = []
        
        # Add source filter
        if current_source != 'all':
            query += ' WHERE source_id = %s'
            params.append(current_source)
        
        if time_filter == 'week' or time_filter == 'month':
            query += ' AND ' if params else ' WHERE '
            
            if is_sqlite:
                # SQLite version - use datetime functions
                days = 7 if time_filter == 'week' else 30
                query += "received_at >= datetime('now', '-" + str(days) + " days')"
            else:
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
