from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import json
import time
import sqlite3
from datetime import datetime
import os
import stripe

app = Flask(__name__)
CORS(app)

# Stripe Configuration
STRIPE_SECRET_KEY = os.getenv('STRIPE_SECRET_KEY', 'sk_test_YOUR_KEY_HERE')
STRIPE_PUBLISHABLE_KEY = os.getenv('STRIPE_PUBLISHABLE_KEY', 'pk_test_YOUR_KEY_HERE')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET', 'whsec_YOUR_WEBHOOK_SECRET')

stripe.api_key = STRIPE_SECRET_KEY

# Production database path
db_path = os.path.join(os.getcwd(), 'botd.db')

# Pricing tiers with limits
TIERS = {
    'free': {'requests': 1000, 'price': 0},
    'starter': {'requests': 10000, 'price': 29},
    'pro': {'requests': 100000, 'price': 99}
}

# Stripe Price IDs
PRICE_IDS = {
    'starter': 'price_1T5XpELodupdv9dkQoBVdrv3',
    'pro': 'price_1T5XphLodupdv9dkzOEW6iSk'
}

def init_db():
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            api_key TEXT PRIMARY KEY, 
            tier TEXT DEFAULT 'free', 
            requests INTEGER DEFAULT 0,
            stripe_customer_id TEXT,
            email TEXT,
            created_at TEXT,
            last_reset TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

@app.route('/')
def home():
    return send_from_directory('.', 'dashboard.html')

@app.route('/api')
def api_info():
    return jsonify({
        "message": "BotD SaaS API is running", 
        "status": "active",
        "stripe_publishable_key": STRIPE_PUBLISHABLE_KEY
    })

@app.route('/api/register', methods=['POST'])
def register():
    data = request.json or {}
    api_key = f"botd_{int(time.time())}"
    email = data.get('email', '')
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO users (api_key, tier, requests, email, created_at, last_reset) 
        VALUES (?, ?, ?, ?, ?, ?)
    """, (api_key, 'free', 0, email, datetime.now().isoformat(), datetime.now().strftime('%Y-%m-01')))
    conn.commit()
    conn.close()
    
    return jsonify({'api_key': api_key, 'tier': 'free'})

@app.route('/api/detect', methods=['POST'])
def detect():
    api_key = request.headers.get('X-API-Key')
    if not api_key:
        return jsonify({'error': 'API key required'}), 401
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT tier, requests, last_reset FROM users WHERE api_key = ?", (api_key,))
    result = cursor.fetchone()
    conn.close()
    
    if not result:
        return jsonify({'error': 'Invalid API key'}), 401
    
    tier, requests, last_reset = result
    
    # Check if we need to reset monthly counter
    current_month = datetime.now().strftime('%Y-%m-01')
    if last_reset != current_month:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET requests = 0, last_reset = ? WHERE api_key = ?", 
                      (current_month, api_key))
        conn.commit()
        conn.close()
        requests = 0
    
    # Check limits
    limit = TIERS[tier]['requests']
    if requests >= limit:
        return jsonify({'error': f'Monthly limit exceeded. Upgrade to {tier} plan for more requests.'}), 429
    
    # Update usage
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET requests = requests + 1 WHERE api_key = ?", (api_key,))
    conn.commit()
    conn.close()
    
    # Bot detection
    user_agent = request.headers.get('User-Agent', '').lower()
    is_bot = any(word in user_agent for word in ['bot', 'crawler', 'spider', 'curl'])
    
    return jsonify({
        'is_bot': is_bot,
        'confidence': 0.8 if is_bot else 0.2,
        'timestamp': datetime.now().isoformat(),
        'requests_used': requests + 1,
        'requests_limit': limit,
        'tier': tier
    })

@app.route('/api/stats', methods=['GET'])
def get_stats():
    api_key = request.headers.get('X-API-Key')
    if not api_key:
        return jsonify({'error': 'API key required'}), 401
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT tier, requests, last_reset FROM users WHERE api_key = ?", (api_key,))
    result = cursor.fetchone()
    conn.close()
    
    if not result:
        return jsonify({'error': 'Invalid API key'}), 401
    
    tier, requests, last_reset = result
    limit = TIERS[tier]['requests']
    
    return jsonify({
        'tier': tier,
        'requests_used': requests,
        'requests_limit': limit,
        'requests_remaining': max(0, limit - requests),
        'price': TIERS[tier]['price']
    })

@app.route('/api/create-checkout-session', methods=['POST'])
def create_checkout_session():
    data = request.json
    tier = data.get('tier')
    api_key = data.get('api_key')
    email = data.get('email')
    
    if tier not in ['starter', 'pro']:
        return jsonify({'error': 'Invalid tier'}), 400
    
    # Get user info
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT stripe_customer_id FROM users WHERE api_key = ?", (api_key,))
    result = cursor.fetchone()
    conn.close()
    
    try:
        # Create or get customer
        customer_id = result[0] if result and result[0] else None
        if not customer_id:
            customer = stripe.Customer.create(email=email)
            customer_id = customer.id
            
            # Update user with customer ID
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET stripe_customer_id = ? WHERE api_key = ?", 
                          (customer_id, api_key))
            conn.commit()
            conn.close()
        
        # Create checkout session
        session = stripe.checkout.Session.create(
            customer=customer_id,
            payment_method_types=['card'],
            line_items=[{
                'price': PRICE_IDS[tier],
                'quantity': 1,
            }],
            mode='subscription',
            success_url=f"https://web-production-c3d23.up.railway.app/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"https://web-production-c3d23.up.railway.app/cancel",
            metadata={'api_key': api_key, 'tier': tier}
        )
        
        return jsonify({'sessionId': session.id})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/api/cancel-subscription', methods=['POST'])
def cancel_subscription():
    data = request.json
    api_key = data.get('api_key')
    
    # Get user's customer ID
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT stripe_customer_id FROM users WHERE api_key = ?", (api_key,))
    result = cursor.fetchone()
    conn.close()
    
    if not result or not result[0]:
        return jsonify({'error': 'No subscription found'}), 404
    
    try:
        # Cancel subscription
        subscriptions = stripe.Subscription.list(customer=result[0])
        if subscriptions.data:
            stripe.Subscription.modify(subscriptions.data[0].id, cancel_at_period_end=True)
        
        # Downgrade user to free
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET tier = 'free' WHERE api_key = ?", (api_key,))
        conn.commit()
        conn.close()
        
        return jsonify({'message': 'Subscription cancelled at end of period'})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/success')
def success():
    session_id = request.args.get('session_id')
    return send_from_directory('.', 'success.html')

@app.route('/cancel')
def cancel():
    return send_from_directory('.', 'cancel.html')

@app.route('/webhook', methods=['POST'])
def webhook():
    payload = request.get_data()
    sig_header = request.headers.get('stripe-signature')
    
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
        
        if event['type'] == 'customer.subscription.created':
            subscription = event['data']['object']
            api_key = subscription['metadata']['api_key']
            tier = subscription['metadata']['tier']
            
            # Upgrade user tier
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET tier = ? WHERE api_key = ?", (tier, api_key))
            conn.commit()
            conn.close()
            
        elif event['type'] == 'customer.subscription.deleted':
            subscription = event['data']['object']
            api_key = subscription['metadata']['api_key']
            
            # Downgrade to free
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET tier = 'free' WHERE api_key = ?", (api_key,))
            conn.commit()
            conn.close()
        
        return jsonify({'status': 'success'})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 400

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
