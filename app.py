from flask import Flask, render_template, jsonify, request, redirect, url_for, flash, session
from datetime import datetime
import requests
from config import Config
from services.odoo_client import OdooClient
from services.vendor_scoring import VendorScoringEngine
from services.risk_engine import ProcurementRiskEngine
from services.ai_service import AIService
from services.approval_engine import ApprovalEngine
from services.ai_assistant import chat as assistant_chat, conversations_for
from services.location import get_location_provider
from data.seed_data import MOCK_QUOTATIONS
from data.db import load_prs, save_prs

MOCK_PURCHASE_REQUESTS = load_prs()
app = Flask(__name__)
app.config.from_object(Config)
app.secret_key = app.config.get('SECRET_KEY', 'default-dev-secret')

@app.after_request
def add_cors_headers(response):
    origin = request.headers.get('Origin')
    if origin in Config.CORS_ORIGINS:
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        response.headers['Access-Control-Allow-Methods'] = 'GET,POST,OPTIONS'
    return response

odoo = OdooClient()

MOCK_USERS = {
    "admin@demo.com": {"password": "password", "name": "System Admin", "role": "ADMIN"},
    "manager@demo.com": {"password": "password", "name": "Procurement Manager", "role": "MANAGER"},
    "finance@demo.com": {"password": "password", "name": "Finance Director", "role": "FINANCE"},
    "employee@demo.com": {"password": "password", "name": "Staff Employee", "role": "EMPLOYEE"}
}

def get_current_user():
    return session.get('user')

@app.before_request
def require_login():
    allowed_routes = ['landing', 'login', 'static', 'api_auth_me', 'api_auth_login']
    if request.endpoint not in allowed_routes and not get_current_user():
        if request.path.startswith('/api/'):
            return jsonify({"success": False, "error": "Authentication required."}), 401
        return redirect(url_for('login'))

scoring_engine = VendorScoringEngine()

def find_pr(pr_id):
    return next((pr for pr in MOCK_PURCHASE_REQUESTS if pr['id'] == pr_id), None)

def visible_prs(user):
    if user and user.get('role') != 'EMPLOYEE':
        return MOCK_PURCHASE_REQUESTS
    email = user.get('email') if user else None
    return [pr for pr in MOCK_PURCHASE_REQUESTS if pr.get('created_by') == email]

def build_comparison(pr):
    quotation = MOCK_QUOTATIONS[0]
    try:
        days_requested = (datetime.strptime(pr['delivery_date'], '%Y-%m-%d') - datetime.now()).days
        if days_requested <= 0:
            days_requested = 7
    except (TypeError, ValueError):
        days_requested = quotation['required_delivery_days']

    profiles = odoo.get_vendors()
    scored = VendorScoringEngine.score_vendors(quotation['bids'], profiles, days_requested, pr['budget'])
    for vendor in scored:
        profile = next((item for item in profiles if item['id'] == vendor['vendor_id']), {})
        vendor['profile'] = profile
        risk = ProcurementRiskEngine.evaluate_risk(
            vendor['raw_price'], pr['budget'], vendor['raw_delivery'], days_requested,
            profile.get('reliability', 100), profile.get('accuracy', 100), profile.get('rating', 100)
        )
        vendor.update(risk_score=risk['risk_score'], risk_level=risk['risk_level'], risks=risk['risks'])
    return scored

def serialize_comparison(pr):
    vendors = build_comparison(pr)
    recommended = vendors[0] if vendors else None
    explanation = AIService.generate_explanation(pr, vendors, recommended) if recommended else ''
    return {
        'request': pr,
        'vendors': vendors,
        'recommended': recommended,
        'explanation': explanation,
        'required_approval': ApprovalEngine.get_required_approvals(
            recommended['raw_price'] * pr['quantity']
        ) if recommended else None
    }

@app.route('/dashboard')
def dashboard():
    total_prs = len(MOCK_PURCHASE_REQUESTS)
    pending_approvals = sum(1 for pr in MOCK_PURCHASE_REQUESTS if pr['status'] in ['PENDING_APPROVAL', 'ANALYZING', 'DRAFT'])
    approved_prs = sum(1 for pr in MOCK_PURCHASE_REQUESTS if pr['status'] == 'APPROVED')
    rejected_prs = sum(1 for pr in MOCK_PURCHASE_REQUESTS if pr['status'] == 'REJECTED')
    po_created_prs = sum(1 for pr in MOCK_PURCHASE_REQUESTS if pr['status'] == 'PO_CREATED')
    
    pos = odoo.get_purchase_orders(limit=50)
    total_spend = sum(po.get('amount_total', 0) for po in pos)
    
    if total_spend >= 100000:
        formatted_spend = f"₹{total_spend / 100000:.1f} Lakhs"
    else:
        formatted_spend = f"₹{total_spend:,.0f}"
        
    vendors = odoo.get_vendors()
    for v in vendors:
        overall = (v.get('reliability', 85) + v.get('delivery_performance', 85) + 
                   v.get('accuracy', 85) + v.get('price_competitiveness', 85) + 
                   v.get('rating', 85)) / 5
        v['overall_score'] = overall
        
    vendors.sort(key=lambda x: x['overall_score'], reverse=True)
    top_vendors = vendors[:4]
    
    avg_vendor_score = sum(v['overall_score'] for v in vendors) / len(vendors) if vendors else 0
    risk_alerts = [v for v in vendors if v['overall_score'] < 80 or v.get('reliability', 100) < 80]
    
    recent_requests = MOCK_PURCHASE_REQUESTS[:5]
    
    status_data = {
        'labels': ['Pending/Analyzing', 'Approved', 'Rejected', 'PO Created'],
        'data': [pending_approvals, approved_prs, rejected_prs, po_created_prs]
    }
    
    return render_template('app.html', 
        stats={
            'total_prs': total_prs,
            'pending_approvals': pending_approvals,
            'approved_prs': approved_prs,
            'po_created_prs': po_created_prs,
            'total_spend': formatted_spend,
            'avg_vendor_score': round(avg_vendor_score),
            'risk_alert_count': len(risk_alerts)
        },
        top_vendors=top_vendors,
        recent_requests=recent_requests,
        risk_alerts=risk_alerts,
        recent_pos=pos[:5],
        status_data=status_data
    )

@app.route('/')
def landing():
    return render_template('app.html', page='landing')

@app.route('/purchase-requests')
def pr_list():
    return render_template('app.html')

@app.route('/purchase-request/create', methods=['GET', 'POST'])
def pr_create():
    if request.method == 'POST':
        product = request.form.get('product', '').strip()
        category = request.form.get('category', '')
        quantity = request.form.get('quantity', '')
        budget = request.form.get('budget', '')
        delivery_date = request.form.get('delivery_date', '')
        priority = request.form.get('priority', '')
        description = request.form.get('description', '')

        # Validation
        errors = []
        if not product:
            errors.append("Product is required.")
        if not delivery_date:
            errors.append("Required delivery date is required.")
        
        qty_val = 0
        try:
            qty_val = int(quantity)
            if qty_val <= 0:
                errors.append("Quantity must be a positive integer.")
        except (TypeError, ValueError):
            errors.append("Invalid quantity.")
            
        budget_val = 0.0
        try:
            budget_val = float(budget)
            if budget_val <= 0:
                errors.append("Budget must be a positive number.")
        except (TypeError, ValueError):
            errors.append("Invalid budget.")

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template('pr_create.html', form_data=request.form)
        
        # Add to mock data
        new_id = f"PR-{1000 + len(MOCK_PURCHASE_REQUESTS) + 1}"
        new_pr = {
            "id": new_id,
            "product": product,
            "category": category,
            "quantity": qty_val,
            "budget": budget_val,
            "delivery_date": delivery_date,
            "priority": priority,
            "description": description,
            "created_by": get_current_user().get('email'),
            "status": "ANALYZING"
        }
        # Insert at the beginning so newest shows first
        MOCK_PURCHASE_REQUESTS.insert(0, new_pr)
        save_prs(MOCK_PURCHASE_REQUESTS)
        flash(f"Purchase request {new_id} successfully created.", "success")
        return redirect(url_for('pr_detail', pr_id=new_id))

    return render_template('pr_create.html', form_data={})

@app.route('/purchase-requests/<pr_id>')
def pr_detail(pr_id):
    pr = next((p for p in MOCK_PURCHASE_REQUESTS if p['id'] == pr_id), None)
    if not pr:
        flash("Purchase Request not found.", "danger")
        return redirect(url_for('pr_list'))
    return render_template('pr_detail.html', pr=pr)

@app.route('/vendors/compare/<pr_id>')
def vendor_compare(pr_id):
    pr = next((p for p in MOCK_PURCHASE_REQUESTS if p['id'] == pr_id), None)
    if not pr:
        flash("Purchase Request not found.", "danger")
        return redirect(url_for('pr_list'))
    
    # Get bids and vendor profiles
    quotation = MOCK_QUOTATIONS[0]
    bids = quotation['bids']
    
    try:
        d_date = datetime.strptime(pr['delivery_date'], '%Y-%m-%d')
        days_requested = (d_date - datetime.now()).days
        if days_requested <= 0: days_requested = 7
    except:
        days_requested = quotation['required_delivery_days']
        
    vendor_profiles = odoo.get_vendors()
    
    scored_vendors = VendorScoringEngine.score_vendors(
        bids=bids, 
        vendor_profiles=vendor_profiles, 
        requested_delivery=days_requested,
        budget=pr['budget']
    )
    
    recommended = None
    for idx, v in enumerate(scored_vendors):
        profile = next((p for p in vendor_profiles if p['id'] == v['vendor_id']), {})
        v['profile'] = profile
        
        # Deterministic Risk Assignment via Risk Engine
        risk_evaluation = ProcurementRiskEngine.evaluate_risk(
            vendor_price=v['raw_price'],
            budget=pr['budget'],
            vendor_delivery=v['raw_delivery'],
            required_delivery=days_requested,
            reliability=profile.get('reliability', 100),
            accuracy=profile.get('accuracy', 100),
            rating=profile.get('rating', 100)
        )
        
        v['risk_score'] = risk_evaluation['risk_score']
        v['risk_level'] = risk_evaluation['risk_level']
        v['risks'] = risk_evaluation['risks']
        
        if v['risk_level'] == 'LOW': v['risk_color'] = 'success'
        elif v['risk_level'] == 'MEDIUM': v['risk_color'] = 'warning'
        elif v['risk_level'] == 'HIGH': v['risk_color'] = 'danger'
        else: v['risk_color'] = 'dark'
            
        # Select recommended vendor
        if idx == 0:
            v['is_recommended'] = True
            recommended = v
        else:
            v['is_recommended'] = False
            
    if recommended:
        recommended['explanation'] = AIService.generate_explanation(pr, scored_vendors, recommended)
        recommended['is_ai_generated'] = Config.AI_ENABLED and bool(Config.AI_API_KEY)
            
    # Update PR status to PENDING_APPROVAL after analysis completes
    if pr['status'] == 'ANALYZING':
        pr['status'] = 'PENDING_APPROVAL'
        save_prs(MOCK_PURCHASE_REQUESTS)

    return render_template('vendor_compare.html', pr=pr, vendors=scored_vendors, recommended=recommended)

@app.route('/approvals')
def approval_list():
    approvals_data = []
    for pr in MOCK_PURCHASE_REQUESTS:
        if pr.get('status') != 'PENDING_APPROVAL':
            continue
        # We need the recommended vendor info. Using the mock RFQ bids for the demo context.
        quotation = MOCK_QUOTATIONS[0]
        bids = quotation['bids']
        vendor_profiles = odoo.get_vendors()
        try:
            days_requested = (datetime.strptime(pr['delivery_date'], '%Y-%m-%d') - datetime.now()).days
            if days_requested <= 0: days_requested = 7
        except:
            days_requested = quotation['required_delivery_days']
            
        scored = VendorScoringEngine.score_vendors(bids, vendor_profiles, days_requested, pr['budget'])
        
        if scored:
            rec = scored[0]
            total_amount = rec['raw_price'] * pr['quantity']
            req_approval = ApprovalEngine.get_required_approvals(total_amount)
            
            # Re-evaluate risk for accurate badge coloring
            risk = ProcurementRiskEngine.evaluate_risk(
                rec['raw_price'], pr['budget'], rec['raw_delivery'], days_requested, 
                rec.get('reliability_score', 100), rec.get('accuracy_score', 100), rec.get('rating_score', 100)
            )
            
            approvals_data.append({
                'pr': pr,
                'total_amount': total_amount,
                'recommended_vendor': rec['vendor_name'],
                'vendor_score': rec['final_score'],
                'risk_level': risk['risk_level'],
                'risk_color': 'success' if risk['risk_level'] == 'LOW' else 'warning' if risk['risk_level'] == 'MEDIUM' else 'danger',
                'required_approval': req_approval
            })
            
    return render_template('approvals.html', approvals=approvals_data)

@app.route('/api/approve/<pr_id>', methods=['POST'])
def approve_pr(pr_id):
    user = get_current_user()
    pr = next((p for p in MOCK_PURCHASE_REQUESTS if p['id'] == pr_id), None)
    if not pr:
        return jsonify({"success": False, "error": "Not found"}), 404
    if pr.get('status') != 'PENDING_APPROVAL':
        return jsonify({"success": False, "error": "Only pending requests can be approved."}), 409
        
    quotation = MOCK_QUOTATIONS[0]
    scored = VendorScoringEngine.score_vendors(quotation['bids'], odoo.get_vendors(), 7, pr['budget'])
    rec = scored[0]
    total_amount = rec['raw_price'] * pr['quantity']
    
    # Backend Authorization Check
    req_app = ApprovalEngine.get_required_approvals(total_amount)
    if not ApprovalEngine.can_user_approve(user['role'], req_app):
        return jsonify({"success": False, "error": f"Unauthorized. {req_app} is required."}), 403
        
    pr['status'] = 'APPROVED'
    pr['approver'] = user['name']
    pr['approval_date'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    pr['selected_vendor_id'] = rec['vendor_id']
    
    # Push to Odoo PO Generator
    try:
        po_id = odoo.create_purchase_order(rec['vendor_id'], [{
            'product_id': 101, # Default mock product ID map 
            'product_qty': pr['quantity'],
            'price_unit': rec['raw_price']
        }], reference=pr['id'])
        
        pr['status'] = 'PO_CREATED'
        pr['po_id'] = po_id
        save_prs(MOCK_PURCHASE_REQUESTS)
        return jsonify({
            "success": True, 
            "po_id": po_id, 
            "vendor": rec['vendor_name'],
            "amount": total_amount,
            "odoo_url": Config.ODOO_URL
        })
    except Exception as e:
        # Keep request as APPROVED but fail to create PO
        pr['status'] = 'APPROVED'
        save_prs(MOCK_PURCHASE_REQUESTS)
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/reject/<pr_id>', methods=['POST'])
def reject_pr(pr_id):
    user = get_current_user()
    data = request.json
    reason = data.get('reason') if data else ""
    
    if not reason.strip():
        return jsonify({"success": False, "error": "Rejection reason is mandatory."}), 400
    
    pr = next((p for p in MOCK_PURCHASE_REQUESTS if p['id'] == pr_id), None)
    if not pr:
        return jsonify({"success": False, "error": "Not found"}), 404
    if pr.get('status') != 'PENDING_APPROVAL':
        return jsonify({"success": False, "error": "Only pending requests can be rejected."}), 409
        
    pr['status'] = 'REJECTED'
    pr['rejecter'] = user['name']
    pr['rejection_reason'] = reason
    pr['rejection_date'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    save_prs(MOCK_PURCHASE_REQUESTS)
    
    return jsonify({"success": True})

@app.route('/vendor-performance')
def vendor_performance():
    vendors = odoo.get_vendors()
    pos = odoo.get_purchase_orders(limit=200)
    
    performance_data = []
    categories = set()
    for v in vendors:
        cat = v.get('category', 'IT Hardware')
        categories.add(cat)
        po_count = len([po for po in pos if po.get('partner_id') and po['partner_id'][0] == v['id']])
        
        rel = v.get('reliability', 85)
        del_perf = v.get('delivery', 85)
        acc = v.get('accuracy', 85)
        price_comp = v.get('price_competitiveness', 85)
        rating = v.get('rating', 85)
        
        overall = (rel + del_perf + acc + price_comp + rating) / 5
        
        performance_data.append({
            'id': v['id'],
            'name': v['name'],
            'reliability': rel,
            'delivery_performance': del_perf,
            'accuracy': acc,
            'price_competitiveness': price_comp,
            'rating': rating,
            'overall': round(overall, 1),
            'po_count': po_count,
            'category': cat
        })
        
    performance_data.sort(key=lambda x: x['overall'], reverse=True)
    return render_template('vendor_performance.html', vendors=performance_data, categories=sorted(list(categories)))

@app.route('/api/vendors')
def api_vendors():
    vendors = odoo.get_vendors()
    return jsonify(vendors)

@app.route('/api/auth/me')
def api_auth_me():
    user = get_current_user()
    return jsonify({'authenticated': bool(user), 'user': user})

@app.route('/api/auth/login', methods=['POST'])
def api_auth_login():
    data = request.get_json(silent=True) or {}
    user = MOCK_USERS.get(data.get('email'))
    if not user or user['password'] != data.get('password'):
        return jsonify({'success': False, 'error': 'Invalid email or password.'}), 401
    session['user'] = {'email': data['email'], 'name': user['name'], 'role': user['role']}
    return jsonify({'success': True, 'user': session['user']})

@app.route('/api/auth/logout', methods=['POST'])
def api_auth_logout():
    session.clear()
    return jsonify({'success': True})

@app.route('/api/dashboard')
def api_dashboard():
    vendors = odoo.get_vendors()
    for vendor in vendors:
        vendor['overall_score'] = round(sum(vendor.get(key, 85) for key in (
            'reliability', 'delivery_performance', 'accuracy', 'price_competitiveness', 'rating'
        )) / 5, 1)
    orders = odoo.get_purchase_orders(limit=50)
    return jsonify({
        'stats': {
            'total_prs': len(MOCK_PURCHASE_REQUESTS),
            'pending_approvals': sum(pr['status'] in ['PENDING_APPROVAL', 'ANALYZING', 'DRAFT'] for pr in MOCK_PURCHASE_REQUESTS),
            'po_created': sum(pr['status'] == 'PO_CREATED' for pr in MOCK_PURCHASE_REQUESTS),
            'total_spend': sum(order.get('amount_total', 0) for order in orders)
        },
        'recent_requests': visible_prs(get_current_user())[:5],
        'recent_orders': orders[:5],
        'top_vendors': sorted(vendors, key=lambda item: item['overall_score'], reverse=True)[:5]
    })

@app.route('/api/purchase-requests', methods=['GET', 'POST'])
def api_purchase_requests():
    if request.method == 'GET':
        return jsonify(visible_prs(get_current_user()))
    data = request.get_json(silent=True) or {}
    required = ['product', 'quantity', 'budget', 'delivery_date']
    if any(not str(data.get(field, '')).strip() for field in required):
        return jsonify({'success': False, 'error': 'Product, quantity, budget, and delivery date are required.'}), 400
    try:
        quantity = int(data['quantity'])
        budget = float(data['budget'])
        if quantity <= 0 or budget <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'Quantity and budget must be positive numbers.'}), 400
    new_pr = {
        'id': f"PR-{1000 + len(MOCK_PURCHASE_REQUESTS) + 1}",
        'product': str(data['product']).strip(), 'category': data.get('category', 'Other'),
        'quantity': quantity, 'budget': budget, 'delivery_date': data['delivery_date'],
        'priority': data.get('priority', 'Medium'), 'description': data.get('description', '').strip(),
        'status': 'ANALYZING',
        'created_by': get_current_user().get('email')
    }
    MOCK_PURCHASE_REQUESTS.insert(0, new_pr)
    save_prs(MOCK_PURCHASE_REQUESTS)
    return jsonify(new_pr), 201

@app.route('/api/purchase-requests/<pr_id>')
def api_purchase_request(pr_id):
    pr = find_pr(pr_id)
    if pr and pr not in visible_prs(get_current_user()):
        pr = None
    return jsonify(pr) if pr else (jsonify({'success': False, 'error': 'Not found'}), 404)

@app.route('/api/purchase-requests/<pr_id>/analyze', methods=['POST'])
def api_analyze_request(pr_id):
    pr = find_pr(pr_id)
    if not pr or pr not in visible_prs(get_current_user()):
        return jsonify({'success': False, 'error': 'Not found'}), 404
    build_comparison(pr)
    if pr['status'] == 'ANALYZING':
        pr['status'] = 'PENDING_APPROVAL'
        save_prs(MOCK_PURCHASE_REQUESTS)
    return jsonify(serialize_comparison(pr))

@app.route('/api/purchase-requests/<pr_id>/comparison')
def api_comparison(pr_id):
    pr = find_pr(pr_id)
    if not pr or pr not in visible_prs(get_current_user()):
        return jsonify({'success': False, 'error': 'Not found'}), 404
    return jsonify(serialize_comparison(pr))

@app.route('/api/approvals')
def api_approvals():
    return jsonify([serialize_comparison(pr) for pr in MOCK_PURCHASE_REQUESTS if pr['status'] == 'PENDING_APPROVAL'])

@app.route('/api/purchase-requests/<pr_id>/approve', methods=['POST'])
def api_approve_request(pr_id):
    return approve_pr(pr_id)

@app.route('/api/purchase-requests/<pr_id>/reject', methods=['POST'])
def api_reject_request(pr_id):
    return reject_pr(pr_id)

@app.route('/api/vendors/performance')
def api_vendor_performance():
    vendors = odoo.get_vendors()
    for vendor in vendors:
        vendor['overall'] = round(sum(vendor.get(key, 85) for key in (
            'reliability', 'delivery', 'accuracy', 'price_competitiveness', 'rating'
        )) / 5, 1)
    return jsonify(sorted(vendors, key=lambda item: item['overall'], reverse=True))

@app.route('/api/purchase-orders')
def api_purchase_orders():
    if get_current_user().get('role') == 'EMPLOYEE':
        return jsonify([])
    return jsonify(odoo.get_purchase_orders(limit=200))

@app.route('/api/analytics')
def api_analytics():
    orders = odoo.get_purchase_orders(limit=200)
    vendors = odoo.get_vendors()
    return jsonify({
        'spend': sum(order.get('amount_total', 0) for order in orders),
        'purchase_order_count': len(orders),
        'request_count': len(visible_prs(get_current_user())),
        'vendor_count': len(vendors),
        'risk_distribution': {
            'low': sum(1 for vendor in vendors if vendor.get('reliability', 100) >= 80),
            'attention': sum(1 for vendor in vendors if vendor.get('reliability', 100) < 80)
        }
    })

@app.route('/api/notifications')
def api_notifications():
    pending = [pr for pr in visible_prs(get_current_user()) if pr.get('status') == 'PENDING_APPROVAL']
    return jsonify([{
        'type': 'approval',
        'priority': 'high',
        'message': f"{pr['id']} requires approval",
        'route': f"/dashboard#detail/{pr['id']}"
    } for pr in pending])

@app.route('/api/integrations/status')
def api_integrations_status():
    return jsonify({
        'database_configured': bool(Config.DATABASE_URL),
        'database_backend': Config.DATABASE_BACKEND,
        'ai_provider': Config.AI_PROVIDER,
        'gemini_configured': bool(Config.GEMINI_API_KEY),
        'maps_configured': bool(Config.GOOGLE_MAPS_API_KEY),
        'odoo_demo_mode': Config.DEMO_MODE,
        'backend_url': Config.API_URL
    })

@app.route('/api/ai/chat', methods=['POST'])
def api_ai_chat():
    data = request.get_json(silent=True) or {}
    message = str(data.get('message', '')).strip()
    if not message:
        return jsonify({'success': False, 'error': 'Message is required.'}), 400
    return jsonify({'success': True, **assistant_chat(get_current_user(), message, data.get('conversationId'))})

@app.route('/api/ai/conversations')
def api_ai_conversations():
    return jsonify(conversations_for(get_current_user()))

@app.route('/api/vendors/search')
def api_vendor_search():
    query = request.args.get('query', '').strip()
    location = request.args.get('location', '').strip()
    if not query or not location:
        return jsonify({'success': False, 'error': 'Query and location are required.'}), 400
    try:
        results = get_location_provider().search_vendors(query, location, request.args.get('radius'))
        deduped = {item.get('place_id') or item.get('name'): item for item in results}
        if Config.DATABASE_BACKEND == 'postgres':
            try:
                from data.postgres_db import save_vendor_search
                save_vendor_search(get_current_user().get('email'), query, location, Config.LOCATION_PROVIDER, list(deduped.values()))
            except Exception:
                pass
        return jsonify({'success': True, 'results': list(deduped.values())})
    except (ValueError, RuntimeError, requests.RequestException) as error:
        return jsonify({'success': False, 'error': str(error)}), 502

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = MOCK_USERS.get(email)
        if user and user['password'] == password:
            session['user'] = {"email": email, "name": user['name'], "role": user['role']}
            flash(f"Welcome back, {user['name']}!", "success")
            return redirect(url_for('dashboard'))
        else:
            flash("Invalid email or password", "danger")
            
    return render_template('app.html')

@app.route('/logout')
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(host=Config.BACKEND_HOST, port=Config.BACKEND_PORT, debug=Config.DEBUG)
