
from flask import Flask, render_template, request, jsonify, Response, send_from_directory
from pymongo import MongoClient, ReturnDocument, DESCENDING
from bson import ObjectId
import gridfs, os, json
from datetime import datetime
from pathlib import Path
from werkzeug.utils import secure_filename
from io import BytesIO
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics


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
            selling = max(mrp - disc, 0) if discount_type == "rupees" else mrp*(1-disc/100)
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


@app.route("/api/purchases/<purchase_id>", methods=["PUT"])
def update_purchase(purchase_id):
    if db is None:
        return jsonify({"error": "MongoDB not configured"}), 503

    try:
        oid = ObjectId(purchase_id)
    except Exception:
        return jsonify({"error": "Invalid purchase id"}), 400

    existing = db.purchases.find_one({"_id": oid})
    if not existing:
        return jsonify({"error": "Purchase not found"}), 404

    data = request.get_json(silent=True) or {}
    supplier_name = (data.get("supplier_name") or "").strip()
    purchase_date = (data.get("purchase_date") or "").strip()
    items = data.get("items") or []

    if not supplier_name:
        return jsonify({"error": "Supplier / party name is required"}), 400
    if not purchase_date:
        return jsonify({"error": "Purchase date is required"}), 400
    if not isinstance(items, list) or not items:
        return jsonify({"error": "At least one product is required"}), 400

    normalized_items = []
    total_quantity = 0
    total_meter = 0.0
    grand_total = 0.0

    for index, item in enumerate(items):
        name = (item.get("name") or "").strip()
        if not name:
            return jsonify({"error": f"Product name is required for item {index + 1}"}), 400

        quantity = int(float(item.get("quantity", 0) or 0))
        meter_quantity = float(item.get("meterQuantity", 0) or 0)
        purchase_price = float(item.get("purchasePrice", 0) or 0)
        pricing_method = (item.get("pricingMethod") or "").strip()
        pricing_percent = float(item.get("pricingPercent", 0) or 0)
        mrp = float(item.get("mrp", 0) or 0)
        discount_type = (item.get("discountType") or "percentage").strip()
        discount_value = float(item.get("discountValue", 0) or 0)

        if quantity <= 0 and meter_quantity <= 0:
            return jsonify({"error": f"Enter quantity or meter for {name}"}), 400

        units = quantity if quantity > 0 else meter_quantity
        line_total = units * purchase_price

        if mrp > 0:
            selling_price = max(mrp - discount_value, 0) if discount_type == "rupees" else mrp * (1 - discount_value / 100)
        else:
            selling_price = 0

        normalized_items.append({
            "purchase_id": oid,
            "product_name": name,
            "subcategory": (item.get("subcategory") or "").strip(),
            "brand_name": (item.get("brandName") or "").strip(),
            "size_value": (item.get("sizeValue") or "").strip(),
            "quantity": quantity,
            "meter_quantity": meter_quantity,
            "purchase_price": purchase_price,
            "pricing_method": pricing_method,
            "pricing_percent": pricing_percent,
            "mrp": mrp,
            "discount_type": discount_type,
            "discount_value": discount_value,
            "discount_percent": discount_value if discount_type == "percentage" else 0,
            "selling_price": selling_price,
            "line_total": line_total,
            "notes": (item.get("notes") or "").strip(),
        })

        total_quantity += quantity
        total_meter += meter_quantity
        grand_total += line_total

    db.purchases.update_one(
        {"_id": oid},
        {"$set": {
            "supplier_name": supplier_name,
            "supplier_place": (data.get("supplier_place") or "").strip(),
            "purchase_date": purchase_date,
            "transport_method": (data.get("transport_method") or "").strip(),
            "ordered_by": (data.get("ordered_by") or "").strip(),
            "total_quantity": total_quantity,
            "total_meter": total_meter,
            "grand_total": grand_total,
            "updated_at": datetime.utcnow(),
        }}
    )

    db.purchase_items.delete_many({"purchase_id": oid})
    if normalized_items:
        db.purchase_items.insert_many(normalized_items)

    updated = db.purchases.find_one({"_id": oid})
    return jsonify(serialize_purchase(updated))

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


def _pdf_money(value):
    try:
        value = float(value or 0)
    except Exception:
        value = 0
    return f"Rs. {value:,.2f}"

def _pdf_num(value):
    try:
        value = float(value or 0)
    except Exception:
        value = 0
    return f"{value:,.2f}".rstrip("0").rstrip(".")

def build_purchase_history_pdf(purchases):
    """Build a polished purchase-history PDF from MongoDB purchase documents."""
    buffer = BytesIO()
    page = landscape(A4)

    doc = SimpleDocTemplate(
        buffer,
        pagesize=page,
        rightMargin=10 * mm,
        leftMargin=10 * mm,
        topMargin=10 * mm,
        bottomMargin=10 * mm,
        title="Maharani Purchase History Report",
        author="Maharani Wedding Collections",
    )

    styles = getSampleStyleSheet()
    brand = colors.HexColor("#8D1738")
    soft = colors.HexColor("#F7EEF1")
    muted = colors.HexColor("#6F666A")
    line = colors.HexColor("#DED5D9")

    title_style = ParagraphStyle(
        "MaharaniTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=22,
        textColor=brand,
        alignment=TA_LEFT,
        spaceAfter=2,
    )
    sub_style = ParagraphStyle(
        "MaharaniSub",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=11,
        textColor=muted,
        alignment=TA_LEFT,
    )
    label_style = ParagraphStyle(
        "MetaLabel",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7,
        leading=8,
        textColor=muted,
        spaceAfter=2,
    )
    value_style = ParagraphStyle(
        "MetaValue",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=10,
        textColor=colors.HexColor("#231D20"),
    )
    table_header = ParagraphStyle(
        "TableHeader",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=6.8,
        leading=8,
        textColor=brand,
    )
    table_cell = ParagraphStyle(
        "TableCell",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=6.6,
        leading=8,
        textColor=colors.HexColor("#231D20"),
    )
    section_style = ParagraphStyle(
        "Section",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=13,
        textColor=brand,
        spaceBefore=6,
        spaceAfter=6,
    )

    total_qty = sum(int(p.get("total_quantity", 0) or 0) for p in purchases)
    total_meter = sum(float(p.get("total_meter", 0) or 0) for p in purchases)
    total_value = sum(float(p.get("grand_total", 0) or 0) for p in purchases)

    story = [
        Paragraph("MAHARANI WEDDING COLLECTIONS", title_style),
        Paragraph("PURCHASE HISTORY REPORT", sub_style),
        Spacer(1, 5 * mm),
    ]

    summary_data = [
        [
            Paragraph("TOTAL PURCHASES", label_style),
            Paragraph("TOTAL QUANTITY", label_style),
            Paragraph("TOTAL METER", label_style),
            Paragraph("TOTAL PURCHASE VALUE", label_style),
        ],
        [
            Paragraph(str(len(purchases)), value_style),
            Paragraph(f"{total_qty} pcs", value_style),
            Paragraph(f"{_pdf_num(total_meter)} m", value_style),
            Paragraph(_pdf_money(total_value), value_style),
        ],
    ]
    summary = Table(summary_data, colWidths=[65 * mm, 65 * mm, 65 * mm, 72 * mm])
    summary.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), soft),
        ("BOX", (0, 0), (-1, -1), 0.6, line),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, line),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.extend([summary, Spacer(1, 5 * mm)])

    for index, purchase in enumerate(purchases, start=1):
        story.append(Paragraph(f"Purchase {index}", section_style))

        meta_data = [
            [
                Paragraph("SUPPLIER / PARTY", label_style),
                Paragraph("PLACE", label_style),
                Paragraph("PURCHASE DATE", label_style),
                Paragraph("BILL / ORDER NO.", label_style),
                Paragraph("TRANSPORT", label_style),
                Paragraph("ORDERED BY", label_style),
            ],
            [
                Paragraph(str(purchase.get("supplier_name") or "-"), value_style),
                Paragraph(str(purchase.get("supplier_place") or "-"), value_style),
                Paragraph(str(purchase.get("purchase_date") or "-"), value_style),
                Paragraph(str(purchase.get("bill_number") or "-"), value_style),
                Paragraph(str(purchase.get("transport_method") or "-"), value_style),
                Paragraph(str(purchase.get("ordered_by") or "-"), value_style),
            ],
        ]
        meta = Table(meta_data, colWidths=[46 * mm, 39 * mm, 38 * mm, 42 * mm, 38 * mm, 40 * mm])
        meta.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), soft),
            ("BOX", (0, 0), (-1, -1), 0.5, line),
            ("INNERGRID", (0, 0), (-1, -1), 0.3, line),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.extend([meta, Spacer(1, 2.5 * mm)])

        items = list(db.purchase_items.find({"purchase_id": purchase["_id"]}).sort("_id", 1)) if db is not None else []

        rows = [[
            Paragraph("#", table_header),
            Paragraph("Product", table_header),
            Paragraph("Subcategory", table_header),
            Paragraph("Brand", table_header),
            Paragraph("Size", table_header),
            Paragraph("Qty", table_header),
            Paragraph("Meter", table_header),
            Paragraph("Purchase Rate", table_header),
            Paragraph("MRP", table_header),
            Paragraph("Discount", table_header),
            Paragraph("Selling Price", table_header),
            Paragraph("Item Total", table_header),
            Paragraph("Notes", table_header),
        ]]

        for item_index, item in enumerate(items, start=1):
            discount_value = item.get("discount_value", item.get("discount_percent", 0)) or 0
            if item.get("discount_type") == "rupees":
                discount_text = _pdf_money(discount_value)
            else:
                discount_text = f"{_pdf_num(discount_value)}%"

            rows.append([
                Paragraph(str(item_index), table_cell),
                Paragraph(str(item.get("product_name") or "-"), table_cell),
                Paragraph(str(item.get("subcategory") or "-"), table_cell),
                Paragraph(str(item.get("brand_name") or "-"), table_cell),
                Paragraph(str(item.get("size_value") or "-"), table_cell),
                Paragraph(str(item.get("quantity") or 0), table_cell),
                Paragraph(_pdf_num(item.get("meter_quantity", 0)), table_cell),
                Paragraph(_pdf_money(item.get("purchase_price", 0)), table_cell),
                Paragraph(_pdf_money(item.get("mrp", 0)), table_cell),
                Paragraph(discount_text, table_cell),
                Paragraph(_pdf_money(item.get("selling_price", 0)), table_cell),
                Paragraph(_pdf_money(item.get("line_total", 0)), table_cell),
                Paragraph(str(item.get("notes") or "-"), table_cell),
            ])

        item_table = Table(
            rows,
            repeatRows=1,
            colWidths=[
                7 * mm, 29 * mm, 27 * mm, 23 * mm, 18 * mm,
                12 * mm, 15 * mm, 23 * mm, 21 * mm, 19 * mm,
                22 * mm, 23 * mm, 27 * mm
            ],
        )
        item_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), soft),
            ("BOX", (0, 0), (-1, -1), 0.5, line),
            ("INNERGRID", (0, 0), (-1, -1), 0.25, line),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(item_table)

        purchase_total_data = [[
            Paragraph(f"<b>Total Quantity:</b> {purchase.get('total_quantity', 0) or 0} pcs", value_style),
            Paragraph(f"<b>Total Meter:</b> {_pdf_num(purchase.get('total_meter', 0))} m", value_style),
            Paragraph(f"<b>Purchase Total:</b> {_pdf_money(purchase.get('grand_total', 0))}", value_style),
        ]]
        purchase_total = Table(purchase_total_data, colWidths=[88 * mm, 88 * mm, 91 * mm])
        purchase_total.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.white),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ("ALIGN", (-1, 0), (-1, 0), "RIGHT"),
        ]))
        story.extend([purchase_total, Spacer(1, 4 * mm)])

    story.extend([
        Spacer(1, 4 * mm),
        Paragraph("Generated from Maharani Purchase Manager", sub_style),
    ])

    def draw_page(canvas, doc):
        canvas.saveState()
        width, height = page
        canvas.setStrokeColor(brand)
        canvas.setLineWidth(0.7)
        canvas.line(10 * mm, 8 * mm, width - 10 * mm, 8 * mm)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(muted)
        canvas.drawString(10 * mm, 4.5 * mm, "Maharani Wedding Collections")
        canvas.drawRightString(width - 10 * mm, 4.5 * mm, f"Page {doc.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=draw_page, onLaterPages=draw_page)
    buffer.seek(0)
    return buffer.getvalue()



@app.route("/api/reports/purchase-history.pdf", methods=["GET"])
def purchase_history_pdf_safe():
    if db is None:
        return jsonify({"error": "MongoDB not configured"}), 503

    purchases = list(db.purchases.find().sort("created_at", DESCENDING))
    if not purchases:
        return jsonify({"error": "No purchase history to share"}), 404

    try:
        pdf_bytes = build_purchase_history_pdf(purchases)
    except Exception as e:
        app.logger.exception("Failed to build purchase history PDF")
        return jsonify({"error": f"Could not create purchase PDF: {str(e)}"}), 500

    filename = f"maharani-purchase-history-{datetime.utcnow().strftime('%Y%m%d-%H%M')}.pdf"

    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )



@app.route("/api/meta/next-order-number")
def next_order_number():
    latest=db.purchases.find_one({"order_number":{"$type":"number"}},sort=[("order_number",DESCENDING)])
    return jsonify({"next_order_number":int(latest.get("order_number",0))+1 if latest else 1})

@app.route("/api/suppliers")
def supplier_suggestions():
    q=(request.args.get("q") or "").strip(); exact=request.args.get("exact")=="1"; match={}
    if q: match["supplier_name"]={"$regex":("^"+re.escape(q)+"$") if exact else ("^"+re.escape(q)),"$options":"i"}
    pipeline=[{"$match":match},{"$sort":{"created_at":-1}},{"$group":{"_id":{"$toLower":"$supplier_name"},"supplier_name":{"$first":"$supplier_name"},"supplier_place":{"$first":"$supplier_place"},"transport_method":{"$first":"$transport_method"},"ordered_by":{"$first":"$ordered_by"}}},{"$sort":{"supplier_name":1}},{"$limit":20},{"$project":{"_id":0}}]
    return jsonify(list(db.purchases.aggregate(pipeline)))

@app.route("/api/purchases/search-index")
def purchase_search_index():
    result={}
    for i in db.purchase_items.find({},{"purchase_id":1,"product_name":1,"subcategory":1,"brand_name":1,"size_value":1,"notes":1}):
        k=str(i.get("purchase_id")); result.setdefault(k,[]); result[k]+=[i.get("product_name") or "",i.get("subcategory") or "",i.get("brand_name") or "",i.get("size_value") or "",i.get("notes") or ""]
    return jsonify(result)

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
