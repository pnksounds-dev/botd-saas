import stripe
import os
from flask import request, jsonify

# Stripe Configuration
STRIPE_SECRET_KEY = os.getenv('STRIPE_SECRET_KEY', 'sk_test_...')  # Add your key
STRIPE_PUBLISHABLE_KEY = os.getenv('STRIPE_PUBLISHABLE_KEY', 'pk_test_...')  # Add your key

stripe.api_key = STRIPE_SECRET_KEY

# Price IDs (create these in Stripe Dashboard)
PRICE_IDS = {
    'starter': 'price_starter_monthly',  # Create in Stripe
    'pro': 'price_pro_monthly'          # Create in Stripe
}

def create_checkout_session(tier, success_url, cancel_url):
    """Create Stripe checkout session"""
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price': PRICE_IDS[tier],
                'quantity': 1,
            }],
            mode='subscription',
            success_url=success_url,
            cancel_url=cancel_url,
            customer_email=request.json.get('email') if request.json else None
        )
        return session
    except Exception as e:
        print(f"Stripe error: {e}")
        return None

def create_customer_portal_session(customer_id, return_url):
    """Create customer portal session for managing subscriptions"""
    try:
        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=return_url
        )
        return session
    except Exception as e:
        print(f"Portal error: {e}")
        return None

def handle_webhook_event(payload, sig_header):
    """Handle Stripe webhook events"""
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, os.getenv('STRIPE_WEBHOOK_SECRET')
        )
        
        if event['type'] == 'customer.subscription.created':
            handle_subscription_created(event['data']['object'])
        elif event['type'] == 'customer.subscription.deleted':
            handle_subscription_deleted(event['data']['object'])
        elif event['type'] == 'invoice.payment_succeeded':
            handle_payment_succeeded(event['data']['object'])
        
        return event
    except Exception as e:
        print(f"Webhook error: {e}")
        return None

def handle_subscription_created(subscription):
    """Handle new subscription"""
    customer_id = subscription['customer']
    tier = 'starter' if 'starter' in subscription['items']['data'][0]['price']['id'] else 'pro'
    
    # Update user tier in database
    # This would connect to your user database
    print(f"User {customer_id} subscribed to {tier}")

def handle_subscription_deleted(subscription):
    """Handle subscription cancellation"""
    customer_id = subscription['customer']
    
    # Downgrade user to free tier
    print(f"User {customer_id} subscription cancelled")

def handle_payment_succeeded(invoice):
    """Handle successful payment"""
    customer_id = invoice['customer']
    
    # Extend user access
    print(f"Payment succeeded for {customer_id}")
