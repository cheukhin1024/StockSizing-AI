import numpy as np
import pandas as pd
import yfinance as yf
import warnings
import matplotlib.pyplot as plt
import riskfolio as rp
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from io import BytesIO
import base64
import uvicorn
from fastapi.responses import HTMLResponse
import stripe
import bcrypt
import jwt
from datetime import datetime, timedelta

# Add your Stripe secret key
stripe.api_key = 'sk_test_51QHcHrG4CmYrOkCIH0C18daYxIl2yGibS6x0bIJ93k7CmQPr0IRxxM7Kgc8GtsYc7pctjuliI4sEMDMHpkiAyHou00exhjrvtd'

# Add these constants for plan limits
PLAN_LIMITS = {
    'free': 5,
    'basic': 15,
    'professional': 30
}

app = FastAPI()

class PortfolioInput(BaseModel):
    start_date: str
    end_date: str
    assets: list[str]

class UserLogin(BaseModel):
    email: str
    password: str

class UserSignup(BaseModel):
    name: str
    email: str
    password: str

@app.get("/check-subscription")
async def check_subscription(customer_id: str = None):
    if not customer_id:
        return {"plan": "free", "limit": PLAN_LIMITS['free']}
    
    try:
        # Get customer's subscriptions from Stripe
        subscriptions = stripe.Subscription.list(customer=customer_id)
        
        if not subscriptions.data:
            return {"plan": "free", "limit": PLAN_LIMITS['free']}
            
        # Get the active subscription
        active_sub = subscriptions.data[0]
        
        # Determine plan based on price ID
        if active_sub.plan.id == "prod_R9wHpXLvKu16b7": #Basic Plan ID
            return {"plan": "basic", "limit": PLAN_LIMITS['basic']}
        elif active_sub.plan.id == "prod_R9xut0IvAUI9oS": #Professional Plan ID
            return {"plan": "professional", "limit": PLAN_LIMITS['professional']}
        elif active_sub.plan.id == "prod_RA4l1NQIgu0jFj": #Free Plan ID
            return {"plan": "free", "limit": PLAN_LIMITS['free']}
            
    except Exception as e:
        print(f"Error checking subscription: {str(e)}")
        return {"plan": "free", "limit": PLAN_LIMITS['free']}

@app.post("/optimize_portfolio")
async def optimize_portfolio(input: PortfolioInput, request: Request):
    # Get customer ID from request headers or session
    customer_id = request.headers.get('customer-id')
    
    # Check subscription status
    subscription = await check_subscription(customer_id)
    asset_limit = subscription["limit"]
    
    # Check if number of assets exceeds plan limit
    if len(input.assets) > asset_limit:
        raise HTTPException(
            status_code=403,
            detail=f"Your current plan only allows up to {asset_limit} assets. Please upgrade your plan to add more assets."
        )
    
    try:
        # Download data
        data = yf.download(input.assets, start=input.start_date, end=input.end_date)
        data = data.loc[:, ('Adj Close', slice(None))]
        data.columns = input.assets

        Y = data[input.assets].pct_change().dropna()

        # Build portfolio object
        port = rp.HCPortfolio(returns=Y)
        
        # Estimate optimal portfolio
        w = port.optimization(model='HRP',
                              codependence='pearson',
                              rm='MV',
                              rf=0,
                              linkage='single',
                              max_k=10,
                              leaf_order=True)

        # Generate pie chart
        fig, ax = plt.subplots(1, 1, figsize=(5, 4))
        ax = rp.plot_pie(w=w,
                         title='Stock Sizing AI Portfolio Optimization',
                         others=0.05,
                         nrow=25,
                         cmap="tab20",
                         height=32,
                         width=40,
                         ax=ax)
        plt.tight_layout()

        # Convert plot to base64 string
        buffer = BytesIO()
        plt.savefig(buffer, format='png')
        buffer.seek(0)
        plot_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

        return {
            "weights": w.to_dict(),
            "plot": plot_base64
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/", response_class=HTMLResponse)
async def home():
    with open("index.html", encoding='utf-8') as f:
        return f.read()

@app.get("/optimize", response_class=HTMLResponse)
async def get_optimize():
    with open("optimize.html", encoding='utf-8') as f:
        return f.read()

@app.get("/pricing", response_class=HTMLResponse)
async def pricing_page():
    with open("pricing.html", encoding='utf-8') as f:
        return f.read()

@app.get("/faq", response_class=HTMLResponse)
async def faq_page():
    with open("faq.html", encoding='utf-8') as f:
        return f.read()

@app.get("/login", response_class=HTMLResponse)
async def login_page():
    with open("login.html", encoding='utf-8') as f:
        return f.read()

@app.post("/login")
async def login(user: UserLogin):
    try:
        # Here you would typically:
        # 1. Check if user exists in your database
        # 2. Verify password
        # 3. Create or get Stripe customer ID
        # 4. Generate JWT token
        
        # For demo, returning mock response
        return {"customer_id": "cus_example", "token": "jwt_token_example"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/signup")
async def signup(user: UserSignup):
    try:
        # Here you would typically:
        # 1. Check if email already exists
        # 2. Hash password
        # 3. Create user in your database
        # 4. Create Stripe customer
        # 5. Generate JWT token
        
        # Create Stripe customer
        customer = stripe.Customer.create(
            email=user.email,
            name=user.name
        )
        
        return {"customer_id": customer.id, "token": "jwt_token_example"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# Remove or comment out the following lines:
if __name__ == "__main__":
    uvicorn.run('main:app', host='127.0.0.1', port=8000)
