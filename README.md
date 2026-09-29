# PROCUREAI

PROCUREAI is an intelligent, automated procurement management system built for the modern enterprise. It connects a frontend portal with an underlying ERP system (Odoo) to evaluate vendors, calculate deterministic risk, request multi-tier approvals, and generate AI-driven natural language explanations for purchasing decisions.

## 🚀 Getting Started

### 1. Installation
Ensure you have Python 3.8+ installed. 
Clone the repository and install the required dependencies:
```bash
git clone https://github.com/sudhanshu-cyb/Prochure-Ai.git
cd Prochure-Ai
pip install -r requirements.txt
```

### 2. Environment Configuration
Create a `.env` file in the root folder based on the `.env.example` template:
```ini
# Copy the contents of .env.example into your new .env file
AI_API_KEY=your_openai_or_groq_key
AI_ENABLED=true
DEMO_MODE=true # Keep true unless connecting to a live Odoo database
```

### 3. Run the Application
Start the Flask development server:
```bash
python app.py
```
The server uses `BACKEND_HOST` and `BACKEND_PORT` from `.env`. With the example
configuration, open `http://127.0.0.1:8000` in your browser. The public landing
page is at `/`; the authenticated workspace is at `/dashboard`.

The backend reads `DATABASE_URL` for Prisma configuration, `GEMINI_API_KEY` and
`GEMINI_MODEL` when `AI_PROVIDER=gemini`, and `GOOGLE_MAPS_API_KEY` for future
map-enabled vendor workflows. Check non-secret integration state at
`GET /api/integrations/status` after signing in.

---

## 🔑 Demo Login Accounts
The application is locked behind a session-based authentication system. Use the following mock credentials to log in (Password for all is **`password`**):
* **Admin:** `admin@demo.com` (Full system access)
* **Manager:** `manager@demo.com`
* **Finance:** `finance@demo.com`
* **Employee:** `employee@demo.com`

---

## 📂 Project Structure & File Guide

If you are a teammate looking to make changes to the codebase, here is a guide to what each file does:

### Core Application
* **`app.py`**: The central nervous system of the application. Contains all the Flask routing (`/dashboard`, `/approvals`, `/purchase-requests`, etc.) and the login session logic. 
* **`config.py`**: Loads environment variables from `.env` and makes them available globally to the Flask app.

### Intelligence Layer (`/services/`)
This folder contains the brain of the application.
* **`vendor_scoring.py`**: Contains the deterministic algorithm that calculates a vendor's score out of 100 based on price (35%), delivery (25%), reliability (20%), accuracy (10%), and rating (10%).
* **`risk_engine.py`**: Evaluates the scored vendors to determine if they pose Budget, Delivery, Reliability, or Accuracy risks. It returns a risk level (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`).
* **`ai_service.py`**: Takes the data from the scoring engine and risk engine and passes it to an LLM (via your API key) to generate a natural language explanation of *why* a vendor was recommended.
* **`approval_engine.py`**: Determines what level of managerial or financial approval is required based on the total cost of the purchase.
* **`odoo_client.py`**: The XML-RPC client that handles communication with the Odoo ERP. It automatically mocks data if `DEMO_MODE=true`.

### Data Layer (`/data/`)
* **`seed_data.py`**: Contains the mock lists of Vendors, Products, and Quotations. If you want to change the fake vendor names or their stats for the dashboard, **edit this file**.
* **`db.py`**: A zero-installation JSON database wrapper. It ensures that any Purchase Requests created in the UI are saved to a local `.json` file so they don't disappear when the server restarts.

### Frontend (`/templates/` & `/static/`)
* **`templates/base.html`**: The master HTML layout. It contains the navigation bar, Bootstrap 5 imports, and global CSS styling. All other pages inherit from this.
* **`templates/*.html`**: Individual views for the Dashboard, Approvals table, Vendor Comparisons, and PR Creation.
* **`static/css/style.css`**: Additional custom styling overrides.

---

## 🛠 Testing
E2E testing scripts are provided in the root directory (e.g., `test_e2e.py`). You can run them to ensure the intelligence pipelines and approval mechanics are firing correctly without using the browser:
```bash
python test_e2e.py
```
