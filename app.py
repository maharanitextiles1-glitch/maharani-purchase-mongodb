
from flask import Flask, render_template, request, jsonify, Response, send_from_directory
from pymongo import MongoClient, DESCENDING
from bson import ObjectId
import gridfs, os, json
from datetime import datetime
from pathlib import Path
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_FOLDER = BASE_DIR / "uploads"
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024

MONGODB_URI = os.environ.get("MONGODB_URI", "").strip()
MONGODB_DB = os.environ.get("MONGODB_DB", "maharani_purchase").strip()
ALLOWED_EXTENSIONS = {"jpg","jpeg","png","webp","heic"}

client = MongoClient(MONGODB_URI) if MONGODB_URI else None
db = client[MONGODB_DB] if client else None
fs = gridfs.GridFS(db) if db is not None else None

if db is not None:
    db.purchases.create_index([("created_at", DESCENDING)])
    db.purchase_items.create_index("purchase_id")

def allowed_file(filename):
    return "." in filename and filename.rsplit(".",1)[1].lower() in ALLOWED_EXTENSIONS

def to_oid(value):
    try: return ObjectId(str(value))
    except: return None

def serialize_purchase(doc):
    d = dict(doc)
    d["id"] = str(d.pop("_id"))
    if isinstance(d.get("created_at"), datetime):
        d["created_at"] = d["created_at"].isoformat()
    return d

def serialize_item(doc):
    d = dict(doc)
    d["id"] = str(d.pop("_id"))
    d["purchase_id"] = str(d["purchase_id"])
    if isinstance(d.get("image_file_id"), ObjectId):
        d["image_file_id"] = str(d["image_file_id"])
        d["image_url"] = f"/product-image/{d['image_file_id']}"
    else:
        d["image_url"] = None
    return d

def save_image(file):
    if not file or not file.filename or not allowed_file(file.filename):
        return None
    if fs is None:
        return None
    return fs.put(file.stream, filename=secure_filename(file.filename),
                  content_type=file.mimetype or "application/octet-stream",
                  uploaded_at=datetime.utcnow())

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/api/health")
def health():
    if client is None:
        return jsonify({"ok":False,"mongodb":False,"error":"MONGODB_URI not configured"}), 503
    try:
        client.admin.command("ping")
        return jsonify({"ok":True,"mongodb":True,"database":MONGODB_DB})
    except Exception as e:
        return jsonify({"ok":False,"mongodb":True,"error":str(e)}),500

@app.route("/product-image/<file_id>")
def product_image(file_id):
    if fs is None:
        return jsonify({"error":"MongoDB not configured"}),404
    image_id = to_oid(file_id)
    if not image_id:
        return jsonify({"error":"Invalid image id"}),404
    try:
        f = fs.get(image_id)
        return Response(f.read(), mimetype=f.content_type or "application/octet-stream",
                        headers={"Cache-Control":"public, max-age=86400"})
    except:
        return jsonify({"error":"Image not found"}),404

@app.route("/api/purchases", methods=["GET"])
def list_purchases():
    if db is None: return jsonify([])
    docs = list(db.purchases.find().sort("created_at", DESCENDING))
    return jsonify([serialize_purchase(x) for x in docs])

@app.route("/api/purchases/<purchase_id>", methods=["GET"])
def get_purchase(purchase_id):
    if db is None: return jsonify({"error":"MongoDB not configured"}),503
    oid = to_oid(purchase_id)
    if not oid: return jsonify({"error":"Invalid purchase id"}),400
    purchase = db.purchases.find_one({"_id":oid})
    if not purchase: return jsonify({"error":"Purchase not found"}),404
    items = list(db.purchase_items.find({"purchase_id":oid}).sort("_id",1))
    result = serialize_purchase(purchase)
    result["items"] = [serialize_item(x) for x in items]
    return jsonify(result)

@app.route("/api/purchases", methods=["POST"])
def create_purchase():
    if db is None:
        return jsonify({"error":"MongoDB Atlas is not connected. Add MONGODB_URI."}),503

    supplier_name = request.form.get("supplier_name","").strip()
    supplier_place = request.form.get("supplier_place","").strip()
    purchase_date = request.form.get("purchase_date","").strip()
    bill_number = request.form.get("bill_number","").strip()
    transport_method = request.form.get("transport_method","").strip()
    ordered_by = request.form.get("ordered_by","").strip()

    if not supplier_name: return jsonify({"error":"Supplier / party name is required"}),400
    if not purchase_date: return jsonify({"error":"Purchase date is required"}),400

    try:
        items = json.loads(request.form.get("items","[]"))
    except:
        return jsonify({"error":"Invalid items data"}),400
    if not items: return jsonify({"error":"Add at least one product"}),400

    total_quantity,total_meter,grand_total = 0,0.0,0.0
    normalized=[]

    for index,item in enumerate(items):
        name = str(item.get("name","")).strip()
        qty = int(float(item.get("quantity",0) or 0))
        meter = float(item.get("meterQuantity",0) or 0)
        price = float(item.get("purchasePrice",0) or 0)
        method = str(item.get("pricingMethod","")).strip()
        pct = float(item.get("pricingPercent",0) or 0)
        mrp = float(item.get("mrp",0) or 0)
        discount_type = str(item.get("discountType","percentage") or "percentage").strip()
        disc = float(item.get("discountValue", item.get("discountPercent",0)) or 0)

        if not name: return jsonify({"error":f"Product name missing for item {index+1}"}),400
        if qty<=0 and meter<=0: return jsonify({"error":f"Enter quantity or meter quantity for {name}"}),400
        if disc < 0:
            return jsonify({"error":f"Discount cannot be negative for {name}"}),400
        if discount_type == "percentage" and disc > 100:
            return jsonify({"error":f"Discount percentage must be between 0 and 100 for {name}"}),400

        if mrp<=0 and price>0 and pct>0:
            if method=="markup": mrp = price*(1+pct/100)
            elif method=="margin" and pct<100: mrp = price/(1-pct/100)
            elif method=="markdown": mrp = price*(1-pct/100)

        if mrp > 0:
            if discount_type == "rupees":
                selling = max(mrp - disc, 0)
            else:
                selling = mrp * (1 - disc/100)
        else:
            selling = 0
        units = qty if qty>0 else meter
        line_total = units*price

        total_quantity += qty
        total_meter += meter
        grand_total += line_total

        up = request.files.get(f"image_{index}")
        cam = request.files.get(f"camera_{index}")
        selected = up if up and up.filename else cam
        image_id = save_image(selected)

        normalized.append({
            "product_name":name,
            "subcategory":str(item.get("subcategory","")).strip(),
            "brand_name":str(item.get("brandName","")).strip(),
            "size_value":str(item.get("sizeValue","")).strip(),
            "quantity":qty,
            "meter_quantity":meter,
            "purchase_price":price,
            "pricing_method":method,
            "pricing_percent":pct,
            "mrp":mrp,
            "discount_type":discount_type,
            "discount_value":disc,
            "discount_percent":disc if discount_type == "percentage" else 0,
            "selling_price":selling,
            "line_total":line_total,
            "notes":str(item.get("notes","")).strip(),
            "image_file_id":image_id
        })

    purchase = {
        "supplier_name":supplier_name,
        "supplier_place":supplier_place,
        "purchase_date":purchase_date,
        "bill_number":bill_number,
        "transport_method":transport_method,
        "ordered_by":ordered_by,
        "total_quantity":total_quantity,
        "total_meter":total_meter,
        "grand_total":grand_total,
        "created_at":datetime.utcnow()
    }

    purchase_id = db.purchases.insert_one(purchase).inserted_id
    for item in normalized:
        item["purchase_id"] = purchase_id
    db.purchase_items.insert_many(normalized)

    return jsonify({"success":True,"purchase_id":str(purchase_id),
                    "total_quantity":total_quantity,"total_meter":total_meter,
                    "grand_total":grand_total}),201

@app.route("/api/purchases/<purchase_id>", methods=["DELETE"])
def delete_purchase(purchase_id):
    if db is None: return jsonify({"error":"MongoDB not configured"}),503
    oid = to_oid(purchase_id)
    if not oid: return jsonify({"error":"Invalid purchase id"}),400

    items = list(db.purchase_items.find({"purchase_id":oid}))
    for item in items:
        image_id = item.get("image_file_id")
        if isinstance(image_id,ObjectId):
            try: fs.delete(image_id)
            except: pass

    db.purchase_items.delete_many({"purchase_id":oid})
    deleted = db.purchases.delete_one({"_id":oid}).deleted_count
    if not deleted: return jsonify({"error":"Purchase not found"}),404
    return jsonify({"success":True})

@app.route("/manifest.json")
def manifest():
    return send_from_directory(BASE_DIR/"static","manifest.json",mimetype="application/manifest+json")

@app.route("/service-worker.js")
def service_worker():
    r=send_from_directory(BASE_DIR/"static","service-worker.js",mimetype="application/javascript")
    r.headers["Service-Worker-Allowed"]="/"
    return r

if __name__=="__main__":
    app.run(host="0.0.0.0",port=int(os.environ.get("PORT","5002")),debug=True)
