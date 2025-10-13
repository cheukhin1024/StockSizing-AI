import numpy as np
import pandas as pd
import warnings
import matplotlib.pyplot as plt
import riskfolio as rp
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from io import BytesIO
import base64
from fastapi.responses import HTMLResponse
import stripe
import os
import json
import bcrypt
import jwt
from datetime import datetime, timedelta
import requests

app = FastAPI()

# Stripe and auth configuration
stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "sk_test_51QHcHrG4CmYrOkCIH0C18daYxIl2yGibS6x0bIJ93k7CmQPr0IRxxM7Kgc8GtsYc7pctjuliI4sEMDMHpkiAyHou00exhjrvtd")
JWT_SECRET = os.getenv("JWT_SECRET", "dev_secret_change_me")
JWT_ALGORITHM = "HS256"
USERS_DB_PATH = os.getenv("USERS_DB_PATH", "users.json")


def _load_users():
    try:
        if not os.path.exists(USERS_DB_PATH):
            return {}
        with open(USERS_DB_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                migrated = {u.get("email"): u for u in data if u.get("email")}
                return migrated
            return data
    except Exception:
        return {}


def _save_users(users_dict: dict):
    with open(USERS_DB_PATH, "w", encoding="utf-8") as f:
        json.dump(users_dict, f, ensure_ascii=False, indent=2)


def _get_user(email: str):
    users = _load_users()
    return users.get(email.lower())


def _set_user(user: dict):
    users = _load_users()
    users[user["email"].lower()] = user
    _save_users(users)

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


@app.post("/optimize_portfolio")
async def optimize_portfolio(input: PortfolioInput, request: Request):
    try:
        # Initialize an empty dictionary to store DataFrames
        data_frames = {}

        # Tickers of assets
        symbols = input.assets

        # Downloading data
        for symbol in symbols:
            url = 'https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol=' + symbol + '&outputsize=full' + '&datatype=csv' + '&apikey=M37ZGKBJ36AUO0CB'
            df = pd.read_csv(url)
            # Select only timestamp and close columns
            df = df[['timestamp', 'close']]
            # Rename the 'close' column to the symbol name
            df = df.rename(columns={'close': symbol})
            # Store in the dictionary
            data_frames[symbol] = df

        # Start with the first symbol's dataframe
        result_df = data_frames[symbols[0]]

        # Join with the remaining dataframes on timestamp
        for symbol in symbols[1:]:
            result_df = pd.merge(result_df, data_frames[symbol], on='timestamp', how='inner')

        # Choose start time and end time
        start_date = input.start_date
        end_date = input.end_date

        # Filter data based on selected date range
        filtered_df = result_df[(result_df['timestamp'] >= start_date) & (result_df['timestamp'] <= end_date)]
        #print(filtered_df)

        # Sort by timestamp in ascending order (oldest first) for calculating proper returns
        filtered_df = filtered_df.sort_values('timestamp', ascending=False)

        # Calculate percentage change for all symbols
        for symbol in symbols:
            filtered_df[symbol] = filtered_df[symbol].pct_change()

        # Drop the first row as it will contain NaN values after pct_change
        filtered_df = filtered_df.dropna()

        # Display the resulting DataFrame with percentage changes
        #print(filtered_df)

        import riskfolio as rp

        # Create a returns DataFrame excluding the timestamp column
        returns_df = filtered_df[symbols]  # This creates a new DataFrame with only the asset columns

        # Building the portfolio object with only the returns data
        port = rp.HCPortfolio(returns=returns_df)
        
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
                         title='Portfolio Composition',
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

        if isinstance(w, pd.DataFrame) or isinstance(w, pd.Series):
            weights_dict = w.to_dict()
        else:
            weights_dict = dict(w)

        return {
            "weights": weights_dict,
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
        existing = _get_user(user.email)
        if not existing:
            raise HTTPException(status_code=401, detail="Invalid email or password")

        if not bcrypt.checkpw(user.password.encode("utf-8"), existing["password_hash"].encode("utf-8")):
            raise HTTPException(status_code=401, detail="Invalid email or password")

        payload = {
            "sub": existing["email"],
            "customer_id": existing.get("stripe_customer_id"),
            "exp": datetime.utcnow() + timedelta(hours=12),
        }
        token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        return {"customer_id": existing.get("stripe_customer_id"), "email": existing["email"], "name": existing.get("name"), "token": token}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/signup")
async def signup(user: UserSignup):
    try:
        if not stripe.api_key:
            raise HTTPException(status_code=500, detail="Stripe is not configured. Set STRIPE_SECRET_KEY.")

        existing = _get_user(user.email)
        if existing:
            raise HTTPException(status_code=409, detail="Email already registered")

        password_hash = bcrypt.hashpw(user.password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

        customer = stripe.Customer.create(
            email=user.email,
            name=user.name
        )

        new_user = {
            "name": user.name,
            "email": user.email.lower(),
            "password_hash": password_hash,
            "stripe_customer_id": customer.id,
        }
        _set_user(new_user)

        payload = {
            "sub": new_user["email"],
            "customer_id": new_user["stripe_customer_id"],
            "exp": datetime.utcnow() + timedelta(hours=12),
        }
        token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

        return {"customer_id": customer.id, "email": new_user["email"], "name": new_user["name"], "token": token}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/create_billing_portal_session")
async def create_billing_portal_session(request: Request):
    try:
        if not stripe.api_key:
            raise HTTPException(status_code=500, detail="Stripe is not configured. Set STRIPE_SECRET_KEY.")

        body = await request.json()
        return_url = body.get("return_url", "/optimize")
        customer_id = request.headers.get("customer-id")
        if not customer_id:
            raise HTTPException(status_code=401, detail="Missing customer id")

        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=return_url,
        )
        return {"url": session.url}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/signup", response_class=HTMLResponse)
async def signup_page():
    with open("signup.html", encoding='utf-8') as f:
        return f.read()

@app.get("/search_symbol/{keyword}")
async def search_symbol(keyword: str):
    try:
        url = f"https://www.alphavantage.co/query?function=SYMBOL_SEARCH&keywords={keyword}&apikey=M37ZGKBJ36AUO0CB"
        response = requests.get(url)
        data = response.json()
        
        if "bestMatches" in data:
            # Format the results to return only relevant information
            results = [
                {
                    "symbol": match["1. symbol"],
                    "name": match["2. name"],
                    "type": match["3. type"],
                    "region": match["4. region"]
                }
                for match in data["bestMatches"]
            ]
            return results  # Return all results
        return []
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Only run a development server if this file is executed directly.
if __name__ == "__main__":
    # Local development entry-point. Import uvicorn lazily so that the
    # main module can be imported without uvicorn being installed, which
    # is helpful for production environments where a different ASGI
    # server (e.g., gunicorn) is used.
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000)
