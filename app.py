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
    
    # Create cache table for LLM responses
    cur.execute('''
        CREATE TABLE IF NOT EXISTS cache (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
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

def process_text_for_word_cloud(text):
    """Process text to extract words for word cloud, removing common stop words."""
    if not text:
        return []
    
    # Convert to lowercase
    text = text.lower()
    
    # Remove common punctuation
    for char in '.,;:!?()[]{}"\'':
        text = text.replace(char, ' ')
    
    # Split into words
    words = text.split()
    
    # Common English stop words to exclude
    stop_words = {
        'a', 'an', 'the', 'and', 'or', 'but', 'if', 'because', 'as', 'what',
        'which', 'this', 'that', 'these', 'those', 'then', 'just', 'so', 'than',
        'such', 'both', 'through', 'about', 'for', 'is', 'of', 'while', 'during',
        'to', 'from', 'in', 'on', 'at', 'by', 'with', 'about', 'against', 'between',
        'into', 'through', 'during', 'before', 'after', 'above', 'below', 'up',
        'down', 'out', 'off', 'over', 'under', 'again', 'further', 'then', 'once',
        'here', 'there', 'when', 'where', 'why', 'how', 'all', 'any', 'both',
        'each', 'few', 'more', 'most', 'other', 'some', 'such', 'no', 'nor',
        'not', 'only', 'own', 'same', 'so', 'than', 'too', 'very', 's', 't',
        'can', 'will', 'don', 'should', 'now', 'i', 'me', 'my', 'myself', 'we',
        'our', 'ours', 'ourselves', 'you', 'your', 'yours', 'yourself',
        'yourselves', 'he', 'him', 'his', 'himself', 'she', 'her', 'hers',
        'herself', 'it', 'its', 'itself', 'they', 'them', 'their', 'theirs',
        'themselves', 'am', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
        'have', 'has', 'had', 'having', 'do', 'does', 'did', 'doing', 'would',
        'should', 'could', 'ought', 'i\'m', 'you\'re', 'he\'s', 'she\'s', 'it\'s',
        'we\'re', 'they\'re', 'i\'ve', 'you\'ve', 'we\'ve', 'they\'ve', 'i\'d',
        'you\'d', 'he\'d', 'she\'d', 'we\'d', 'they\'d', 'i\'ll', 'you\'ll',
        'he\'ll', 'she\'ll', 'we\'ll', 'they\'ll', 'isn\'t', 'aren\'t', 'wasn\'t',
        'weren\'t', 'hasn\'t', 'haven\'t', 'hadn\'t', 'doesn\'t', 'don\'t',
        'didn\'t', 'won\'t', 'wouldn\'t', 'shan\'t', 'shouldn\'t', 'can\'t',
        'cannot', 'couldn\'t', 'mustn\'t', 'let\'s', 'that\'s', 'who\'s', 'what\'s',
        'here\'s', 'there\'s', 'when\'s', 'where\'s', 'why\'s', 'how\'s', 'email',
        'emails', 'http', 'https', 'www', 'com', 'html', 'subject', 'body', 'text',
        'get', 'one', 'also', 'new', 'may', 'like', 'use', 'click', 'view', 'read'
    }
    
    # Filter out stop words and words less than 3 characters
    filtered_words = [word for word in words if word not in stop_words and len(word) > 2]
    
    return filtered_words

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
        
        email_sequences = cur.fetchall()
        
        # Get average spam score
        cur.execute("SELECT AVG(spam_score) FROM emails WHERE spam_score IS NOT NULL")
        avg_spam_score = cur.fetchone()[0] or 0
        
        # Get email frequency by day of week
        cur.execute("""
            SELECT 
                EXTRACT(DOW FROM received_at) AS day_of_week,
                COUNT(*) AS email_count
            FROM emails
            GROUP BY day_of_week
            ORDER BY day_of_week
        """)
        
        day_of_week_data = cur.fetchall()
        
        # Get emails from the past 7 days for word cloud
        cur.execute("""
            SELECT subject, body_text 
            FROM emails 
            WHERE received_at >= NOW() - INTERVAL '7 days'
        """)
        recent_emails = cur.fetchall()
        
        # Process text for word cloud
        all_words = []
        for email in recent_emails:
            # Process subject
            if email['subject']:
                all_words.extend(process_text_for_word_cloud(email['subject']))
            
            # Process body text
            if email['body_text']:
                all_words.extend(process_text_for_word_cloud(email['body_text']))
        
        # Count word frequencies
        word_counts = {}
        for word in all_words:
            if word in word_counts:
                word_counts[word] += 1
            else:
                word_counts[word] = 1
        
        # Convert to format needed for word cloud
        # Sort by frequency (descending) and take top 100 words
        word_cloud_data = [
            {"text": word, "value": count}
            for word, count in sorted(word_counts.items(), key=lambda x: x[1], reverse=True)[:100]
        ]
        
        # Close connection
        cur.close()
        conn.close()
        
        # Format data for template - ensure all data is JSON serializable
        labels = []
        values = []
        
        for row in email_sequences:
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
        
        # Process day of week data
        day_names = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
        dow_labels = []
        dow_values = []
        
        # Initialize with zeros for all days
        day_counts = {i: 0 for i in range(7)}
        
        # Fill in actual counts
        for row in day_of_week_data:
            day_index = int(row['day_of_week'])
            day_counts[day_index] = int(row['email_count'])
        
        # Find the most popular day
        most_popular_day_index = max(day_counts, key=day_counts.get)
        most_popular_day = day_names[most_popular_day_index]
        
        # Create ordered lists for the chart
        for i in range(7):
            dow_labels.append(day_names[i])
            dow_values.append(day_counts[i])
        
        # Pre-serialize the day of week data
        dow_labels_json = json.dumps(dow_labels)
        dow_values_json = json.dumps(dow_values)
        
        # Pre-serialize the word cloud data
        word_cloud_json = json.dumps(word_cloud_data)
        
        # Ensure avg_spam_score is a simple float
        avg_spam_score = float(round(avg_spam_score, 2)) if avg_spam_score is not None else 0.0
        
        return render_template('home.html', 
                             total_emails=int(total_emails) if total_emails is not None else 0,
                             source_count=int(source_count) if source_count is not None else 0,
                             avg_spam_score=avg_spam_score,
                             labels_json=labels_json,
                             values_json=values_json,
                             dow_labels_json=dow_labels_json,
                             dow_values_json=dow_values_json,
                             most_popular_day=most_popular_day,
                             word_cloud_json=word_cloud_json)
                             
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
        
        # Get pagination parameters
        page = request.args.get('page', '1')
        try:
            page = int(page)
            if page < 1:
                page = 1
        except ValueError:
            page = 1
        
        per_page = 25  # Number of emails per page
        
        # Build query based on filters
        base_query = 'FROM emails e LEFT JOIN email_sources s ON e.source_id = s.id'
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
        where_clause = ''
        if where_clauses:
            where_clause = ' WHERE ' + ' AND '.join(where_clauses)
        
        # First, get total count for pagination
        count_query = f'SELECT COUNT(*) {base_query}{where_clause}'
        cur.execute(count_query, params)
        total_emails = cur.fetchone()[0]
        
        # Calculate total pages
        total_pages = (total_emails + per_page - 1) // per_page  # Ceiling division
        
        # Ensure page is within valid range
        if page > total_pages and total_pages > 0:
            page = total_pages
        
        # Calculate offset
        offset = (page - 1) * per_page
        
        # Build final query with pagination
        query = f'SELECT e.*, s.name as source_name, s.display_name {base_query}{where_clause}'
        query += ' ORDER BY e.received_at DESC'
        query += f' LIMIT {per_page} OFFSET {offset}'
        
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
        start_index = offset + 1 if emails_list else 0
        end_index = offset + len(emails_list)
        email_count_display = f"{start_index}-{end_index} (of {total_emails})" if emails_list else f"0 (of {total_emails})"
        
        return render_template('new_inbox.html',
                             emails=emails_list,
                             sources=sources_list,
                             current_source=current_source,
                             email_count=email_count_display,
                             pagination={
                                 'page': page,
                                 'per_page': per_page,
                                 'total_pages': total_pages,
                                 'total_emails': total_emails
                             })
    
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

def get_recent_emails(days=7, source_id=None, limit=None):
    """Get emails from the past X days, optionally filtered by source and limited to a specific count."""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=DictCursor)
    
    query = """
        SELECT e.*, s.name as source_name, s.display_name 
        FROM emails e
        LEFT JOIN email_sources s ON e.source_id = s.id
        WHERE e.received_at >= NOW() - INTERVAL '%s days'
    """
    params = [days]
    
    if source_id:
        query += " AND e.source_id = %s"
        params.append(source_id)
    
    query += " ORDER BY e.received_at DESC"
    
    if limit:
        query += " LIMIT %s"
        params.append(limit)
    
    cur.execute(query, params)
    
    emails = [dict(email) for email in cur.fetchall()]
    cur.close()
    conn.close()
    
    return emails

def analyze_emails_with_llm(emails, stream=False):
    """Analyze emails using DeepSeek LLM with token counting and streaming support."""
    from openai import OpenAI
    import json
    from datetime import datetime
    import hashlib
    import tiktoken
    
    # If streaming is enabled, we don't use cache
    if not stream:
        # Create a cache key based on the time range and source
        source_ids = set([email.get('source_id') for email in emails if email.get('source_id')])
        source_key = '_'.join([str(sid) for sid in sorted(source_ids)]) if source_ids else 'all'
        
        oldest = min([email['received_at'] for email in emails], default=datetime.now())
        newest = max([email['received_at'] for email in emails], default=datetime.now())
        cache_key = f"email_analysis_{source_key}_{oldest.strftime('%Y%m%d')}_{newest.strftime('%Y%m%d')}"
        cache_key = hashlib.md5(cache_key.encode()).hexdigest()
        
        # Check if we have a cached result
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT value FROM cache WHERE key = %s AND created_at > NOW() - INTERVAL '1 day'", (cache_key,))
        cached = cur.fetchone()
        
        if cached:
            cur.close()
            conn.close()
            return json.loads(cached[0])
    
    # Initialize tiktoken for token counting
    try:
        encoding = tiktoken.encoding_for_model("gpt-4o")  # Close enough to DeepSeek's tokenizer
    except:
        encoding = tiktoken.get_encoding("cl100k_base")  # Fallback encoding
    
    # Set token budget (well below the 65,536 limit)
    MAX_TOKENS = 40000
    
    # System prompt - simplified
    system_prompt = "You are an expert email analyst. Analyze the provided email and give insights on themes, sentiment, promotions, and notable patterns."
    
    # Count tokens in our system prompt
    system_tokens = len(encoding.encode(system_prompt))
    
    # Reserve tokens for the response
    response_tokens = 8000
    
    # Available tokens for email content
    available_tokens = MAX_TOKENS - system_tokens - response_tokens
    
    # Sort emails by date (most recent first)
    sorted_emails = sorted(emails, key=lambda x: x['received_at'], reverse=True)
    
    # Prepare email data with token awareness
    email_data = []
    current_tokens = 0
    
    for email in sorted_emails:
        # Create email entry with full content
        email_entry = {
            'from': email['from_address'],
            'subject': email['subject'],
            'date': email['received_at'].strftime('%Y-%m-%d %H:%M:%S'),
            'source': email.get('display_name') or email.get('source_name'),
            'text': email.get('body_text', '') if email.get('body_text') else "No text content"
        }
        
        # Count tokens for this entry
        entry_json = json.dumps(email_entry)
        entry_tokens = len(encoding.encode(entry_json))
        
        # Check if adding this would exceed our budget
        if current_tokens + entry_tokens > available_tokens:
            # We've reached our token limit
            print(f"Reached token limit after {len(email_data)} emails. Current tokens: {current_tokens}, Entry tokens: {entry_tokens}")
            break
        
        # Add to our batch
        email_data.append(email_entry)
        current_tokens += entry_tokens
    
    print(f"Processing {len(email_data)} emails with approximately {current_tokens} tokens")
    
    # Create a simplified prompt for the LLM
    prompt = f"""
    Analyze this Marketbeat email and provide insights on:
    - Main themes and topics
    - Overall sentiment
    - Key promotions or offers
    - Notable patterns or strategies
    
    Email data: {json.dumps(email_data, indent=2)}
    """
    
    # Count total tokens in the request
    total_tokens = system_tokens + len(encoding.encode(prompt))
    print(f"Total tokens in request: {total_tokens}")
    
    if total_tokens > 65000:
        return f"Error: Token count ({total_tokens}) exceeds maximum limit. Please reduce the number of emails or content size."
    
    # Call the DeepSeek API
    client = OpenAI(
        api_key="sk-c68a67e660b74167886f051b790ca6fd",
        base_url="https://api.deepseek.com"
    )
    
    try:
        response = client.chat.completions.create(
            model="deepseek-reasoner",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            temperature=1.0,  # Recommended for data analysis
            stream=stream  # Enable streaming if requested
        )
        
        # If streaming is enabled, return the streaming response object
        if stream:
            return response
        
        # Otherwise, handle as before
        result = response.choices[0].message.content
        
        # Cache the result (only for non-streaming)
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO cache (key, value, created_at) VALUES (%s, %s, NOW()) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, created_at = NOW()",
            (cache_key, json.dumps(result))
        )
        conn.commit()
        cur.close()
        conn.close()
        
        return result
    except Exception as e:
        if not stream:  # Only close connection if not streaming
            cur.close()
            conn.close()
        return f"Error calling DeepSeek API: {str(e)}"

@app.route('/email-insights')
def email_insights():
    """Render the email insights page."""
    return render_template('email_insights.html')

@app.route('/email-search')
def email_search():
    """Render the email search page."""
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
        cur.close()
        conn.close()
        
        sources_list = [dict(source) for source in sources]
        
        return render_template('email_search.html', sources=sources_list)
    
    except Exception as e:
        print(f"Error: {str(e)}")
        return str(e), 500

@app.route('/api/email-search', methods=['POST'])
def api_email_search():
    """API endpoint to search and analyze emails with LLM."""
    try:
        data = request.json
        query = data.get('query', '')
        source_id = data.get('source_id')
        search_type = data.get('search_type', 'search')
        days = data.get('days', 7)  # Default to 7 days
        
        # Get emails from the specified time period
        emails = get_recent_emails(days=days, source_id=source_id, limit=None)
        
        if not emails:
            return jsonify({"error": f"No emails found from the past {days} days"}), 404
        
        # Prepare the prompt based on the query and search type
        prompt = f"""
        Analyze the following emails from the past {days} days and provide insights based on this query: "{query}"
        
        Focus on:
        - Main themes and topics discussed
        - Overall sentiment
        - Key promotions or offers mentioned
        - Notable patterns or strategies
        
        If the query is specific, prioritize answering that specific question.
        """
        
        if search_type == 'deep-research':
            prompt += """
            Please provide a more detailed and comprehensive analysis, including:
            - In-depth exploration of themes and topics
            - Detailed sentiment analysis with examples
            - Comprehensive breakdown of promotions and offers
            - Thorough analysis of patterns and strategies
            - Any additional insights that might be valuable
            """
        
        # Analyze emails with LLM using the custom prompt
        analysis = analyze_emails_with_custom_prompt(emails, prompt)
        
        return jsonify({"analysis": analysis, "email_count": len(emails)})
    
    except Exception as e:
        print(f"Error analyzing emails: {str(e)}")
        return jsonify({"error": str(e)}), 500

def analyze_emails_with_custom_prompt(emails, prompt, stream=False):
    """Analyze emails using DeepSeek LLM with a custom prompt."""
    from openai import OpenAI
    import json
    from datetime import datetime
    import hashlib
    import tiktoken
    
    # Create a cache key based on the emails and prompt
    prompt_hash = hashlib.md5(prompt.encode()).hexdigest()
    source_ids = set([email.get('source_id') for email in emails if email.get('source_id')])
    source_key = '_'.join([str(sid) for sid in sorted(source_ids)]) if source_ids else 'all'
    
    oldest = min([email['received_at'] for email in emails], default=datetime.now())
    newest = max([email['received_at'] for email in emails], default=datetime.now())
    cache_key = f"email_analysis_{source_key}_{oldest.strftime('%Y%m%d')}_{newest.strftime('%Y%m%d')}_{prompt_hash}"
    cache_key = hashlib.md5(cache_key.encode()).hexdigest()
    
    # Check if we have a cached result
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT value FROM cache WHERE key = %s AND created_at > NOW() - INTERVAL '1 day'", (cache_key,))
    cached = cur.fetchone()
    
    if cached:
        cur.close()
        conn.close()
        return json.loads(cached[0])
    
    # Initialize tiktoken for token counting
    try:
        encoding = tiktoken.encoding_for_model("gpt-4o")  # Close enough to DeepSeek's tokenizer
    except:
        encoding = tiktoken.get_encoding("cl100k_base")  # Fallback encoding
    
    # Set token budget (well below the 65,536 limit)
    MAX_TOKENS = 40000
    
    # System prompt
    system_prompt = "You are an expert email analyst. Analyze the provided emails and respond to the user's query with detailed insights."
    
    # Count tokens in our system prompt
    system_tokens = len(encoding.encode(system_prompt))
    
    # Reserve tokens for the response
    response_tokens = 8000
    
    # Available tokens for email content
    available_tokens = MAX_TOKENS - system_tokens - response_tokens - len(encoding.encode(prompt))
    
    # Sort emails by date (most recent first)
    sorted_emails = sorted(emails, key=lambda x: x['received_at'], reverse=True)
    
    # Prepare email data with token awareness
    email_data = []
    current_tokens = 0
    
    for email in sorted_emails:
        # Create email entry with full content
        email_entry = {
            'from': email['from_address'],
            'subject': email['subject'],
            'date': email['received_at'].strftime('%Y-%m-%d %H:%M:%S'),
            'source': email.get('display_name') or email.get('source_name'),
            'text': email.get('body_text', '') if email.get('body_text') else "No text content"
        }
        
        # Count tokens for this entry
        entry_json = json.dumps(email_entry)
        entry_tokens = len(encoding.encode(entry_json))
        
        # Check if adding this would exceed our budget
        if current_tokens + entry_tokens > available_tokens:
            # We've reached our token limit
            print(f"Reached token limit after {len(email_data)} emails. Current tokens: {current_tokens}, Entry tokens: {entry_tokens}")
            break
        
        # Add to our batch
        email_data.append(email_entry)
        current_tokens += entry_tokens
    
    print(f"Processing {len(email_data)} emails with approximately {current_tokens} tokens")
    
    # Create the full prompt with email data
    full_prompt = f"{prompt}\n\nEmail data: {json.dumps(email_data, indent=2)}"
    
    # Count total tokens in the request
    total_tokens = system_tokens + len(encoding.encode(full_prompt))
    print(f"Total tokens in request: {total_tokens}")
    
    if total_tokens > 65000:
        return f"Error: Token count ({total_tokens}) exceeds maximum limit. Please reduce the number of emails or content size."
    
    # Call the DeepSeek API
    client = OpenAI(
        api_key="sk-c68a67e660b74167886f051b790ca6fd",
        base_url="https://api.deepseek.com"
    )
    
    try:
        response = client.chat.completions.create(
            model="deepseek-reasoner",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": full_prompt}
            ],
            temperature=0.7,
            stream=stream
        )
        
        # If streaming is enabled, return the streaming response object
        if stream:
            return response
        
        # Otherwise, handle as before
        result = response.choices[0].message.content
        
        # Cache the result
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO cache (key, value, created_at) VALUES (%s, %s, NOW()) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, created_at = NOW()",
            (cache_key, json.dumps(result))
        )
        conn.commit()
        cur.close()
        conn.close()
        
        return result
    except Exception as e:
        if not stream:  # Only close connection if not streaming
            cur.close()
            conn.close()
        return f"Error calling DeepSeek API: {str(e)}"

@app.route('/api/email-metrics/<int:email_id>', methods=['GET'])
def get_email_metrics(email_id):
    """API endpoint to get metrics for a specific email."""
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=DictCursor)
        cur.execute('SELECT * FROM emails WHERE id = %s', (email_id,))
        email = cur.fetchone()
        cur.close()
        conn.close()

        if email is None:
            return jsonify({"error": "Email not found"}), 404

        # Process email to get metrics
        email_dict = process_email_data(dict(email))
        
        # Return only the metrics
        metrics = {
            "subject_length": email_dict.get('subject_length', 0),
            "word_count": email_dict.get('word_count', 0),
            "link_count": email_dict.get('link_count', 0),
            "spam_score": email_dict.get('spam_score', 0)
        }
        
        return jsonify(metrics)
    
    except Exception as e:
        print(f"Error getting email metrics: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/analyze-emails', methods=['POST'])
def analyze_emails():
    """API endpoint to analyze emails with LLM."""
    try:
        # Get only the most recent email from Marketbeat (source_id=2)
        emails = get_recent_emails(days=3, source_id=2, limit=1)
        
        if not emails:
            return jsonify({"error": "No Marketbeat emails found in the past 3 days"}), 404
        
        # Analyze emails with LLM
        analysis = analyze_emails_with_llm(emails)
        
        return jsonify({"analysis": analysis, "email_count": len(emails)})
    
    except Exception as e:
        print(f"Error analyzing emails: {str(e)}")
        return jsonify({"error": str(e)}), 500

# Streaming endpoint removed to fix 502 errors
# @app.route('/api/analyze-emails-stream', methods=['POST'])
# def analyze_emails_stream():
#     """Streaming API endpoint to analyze emails with LLM."""
#     try:
#         # Get only the most recent email from Marketbeat (source_id=2)
#         emails = get_recent_emails(days=3, source_id=2, limit=1)
#         
#         if not emails:
#             return jsonify({"error": "No Marketbeat emails found in the past 3 days"}), 404
#         
#         # Get streaming response
#         streaming_response = analyze_emails_with_llm(emails, stream=True)
#         
#         # Set up SSE streaming
#         def generate():
#             for chunk in streaming_response:
#                 if chunk.choices[0].delta.content:
#                     yield f"data: {json.dumps({'content': chunk.choices[0].delta.content})}\n\n"
#             yield f"data: {json.dumps({'done': True})}\n\n"
#         
#         return Response(generate(), mimetype='text/event-stream')
#     
#     except Exception as e:
#         print(f"Error analyzing emails: {str(e)}")
#         return jsonify({"error": str(e)}), 500

# Initialize the database when the app starts
init_db()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=True)
