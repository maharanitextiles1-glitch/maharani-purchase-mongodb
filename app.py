
from flask import Flask, render_template, request, jsonify, Response, send_from_directory, send_file
from pymongo import MongoClient, DESCENDING
from bson import ObjectId
import gridfs, os, json
from io import BytesIO
from datetime import datetime
from pathlib import Path
from werkzeug.utils import secure_filename
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, KeepTogether, Image as RLImage
)
from reportlab.lib.utils import ImageReader

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



def _pdf_money(value):
    try:
        return f"Rs. {float(value or 0):,.2f}"
    except Exception:
        return "Rs. 0.00"


def _pdf_num(value):
    try:
        n = float(value or 0)
        return f"{n:,.2f}".rstrip("0").rstrip(".")
    except Exception:
        return "0"


def _pdf_text(value, fallback="-"):
    text_value = str(value or "").strip()
    if not text_value:
        return fallback
    return (text_value
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;"))


def _discount_label(item):
    discount_type = item.get("discount_type", "percentage")
    value = item.get("discount_value", item.get("discount_percent", 0)) or 0
    if discount_type == "rupees":
        return _pdf_money(value)
    return f"{_pdf_num(value)}%"


def _gridfs_image_flowable(image_id, width=16*mm, height=16*mm):
    if not isinstance(image_id, ObjectId) or fs is None:
        return Paragraph("No photo", ParagraphStyle(
            "NoPhoto", fontName="Helvetica", fontSize=6.5, textColor=colors.HexColor("#8C8588")
        ))
    try:
        grid_file = fs.get(image_id)
        data = BytesIO(grid_file.read())
        image_reader = ImageReader(data)
        iw, ih = image_reader.getSize()
        scale = min(width / iw, height / ih)
        return RLImage(data, width=iw*scale, height=ih*scale)
    except Exception:
        return Paragraph("Photo unavailable", ParagraphStyle(
            "NoPhoto2", fontName="Helvetica", fontSize=6.2, textColor=colors.HexColor("#8C8588")
        ))


def build_purchase_history_pdf():
    buffer = BytesIO()
    page_size = landscape(A4)
    doc = SimpleDocTemplate(
        buffer,
        pagesize=page_size,
        rightMargin=10*mm,
        leftMargin=10*mm,
        topMargin=18*mm,
        bottomMargin=12*mm,
        title="Maharani Purchase History Report",
        author="Maharani Wedding Collections",
    )

    styles = getSampleStyleSheet()
    brand = colors.HexColor("#8D1738")
    brand_dark = colors.HexColor("#661027")
    blush = colors.HexColor("#F8EEF2")
    ink = colors.HexColor("#241E20")
    muted = colors.HexColor("#786E72")
    line = colors.HexColor("#E5DADD")
    soft = colors.HexColor("#FBF8F9")

    title_style = ParagraphStyle(
        "PremiumTitle", parent=styles["Title"], fontName="Helvetica-Bold",
        fontSize=22, leading=25, textColor=brand, spaceAfter=2*mm,
    )
    subtitle_style = ParagraphStyle(
        "PremiumSubtitle", parent=styles["Normal"], fontName="Helvetica",
        fontSize=8.5, leading=11, textColor=muted,
    )
    section_style = ParagraphStyle(
        "Section", parent=styles["Heading2"], fontName="Helvetica-Bold",
        fontSize=11.5, leading=14, textColor=brand_dark, spaceAfter=2*mm,
    )
    body_style = ParagraphStyle(
        "Body", parent=styles["Normal"], fontName="Helvetica",
        fontSize=7.2, leading=9.2, textColor=ink,
    )
    small_style = ParagraphStyle(
        "Small", parent=styles["Normal"], fontName="Helvetica",
        fontSize=6.5, leading=8.2, textColor=muted,
    )
    metric_label = ParagraphStyle(
        "MetricLabel", parent=small_style, fontName="Helvetica-Bold",
        fontSize=6.5, leading=8, textColor=muted,
    )
    metric_value = ParagraphStyle(
        "MetricValue", parent=body_style, fontName="Helvetica-Bold",
        fontSize=11.5, leading=13, textColor=brand,
    )

    purchases = list(db.purchases.find().sort("created_at", DESCENDING)) if db is not None else []
    purchase_ids = [p["_id"] for p in purchases]
    items_by_purchase = {pid: [] for pid in purchase_ids}
    if purchase_ids:
        for item in db.purchase_items.find({"purchase_id": {"$in": purchase_ids}}).sort("_id", 1):
            items_by_purchase.setdefault(item.get("purchase_id"), []).append(item)

    total_value = sum(float(p.get("grand_total", 0) or 0) for p in purchases)
    total_qty = sum(int(p.get("total_quantity", 0) or 0) for p in purchases)
    total_meter = sum(float(p.get("total_meter", 0) or 0) for p in purchases)

    story = []
    story.append(Paragraph("Maharani Wedding Collections", title_style))
    story.append(Paragraph("Purchase History Report", ParagraphStyle(
        "ReportName", parent=subtitle_style, fontName="Helvetica-Bold", fontSize=10, textColor=ink
    )))
    story.append(Paragraph(
        f"Generated {datetime.now().strftime('%d %b %Y, %I:%M %p')}", subtitle_style
    ))
    story.append(Spacer(1, 5*mm))

    metrics = [
        [Paragraph("TOTAL PURCHASES", metric_label), Paragraph("TOTAL QUANTITY", metric_label),
         Paragraph("TOTAL METER", metric_label), Paragraph("TOTAL VALUE", metric_label)],
        [Paragraph(str(len(purchases)), metric_value), Paragraph(f"{total_qty:,} pcs", metric_value),
         Paragraph(f"{_pdf_num(total_meter)} m", metric_value), Paragraph(_pdf_money(total_value), metric_value)],
    ]
    metric_table = Table(metrics, colWidths=[45*mm, 45*mm, 45*mm, 55*mm])
    metric_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), blush),
        ("BOX", (0,0), (-1,-1), 0.5, line),
        ("INNERGRID", (0,0), (-1,-1), 0.5, line),
        ("TOPPADDING", (0,0), (-1,-1), 4*mm),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4*mm),
        ("LEFTPADDING", (0,0), (-1,-1), 4*mm),
        ("RIGHTPADDING", (0,0), (-1,-1), 4*mm),
    ]))
    story.append(metric_table)
    story.append(Spacer(1, 5*mm))

    if not purchases:
        story.append(Paragraph("No purchases are available in the database.", body_style))

    for purchase_index, purchase in enumerate(purchases, 1):
        supplier = _pdf_text(purchase.get("supplier_name"))
        place = _pdf_text(purchase.get("supplier_place"))
        date = _pdf_text(purchase.get("purchase_date"))
        bill = _pdf_text(purchase.get("bill_number"))
        transport = _pdf_text(purchase.get("transport_method"))
        ordered_by = _pdf_text(purchase.get("ordered_by"))

        header_data = [[
            Paragraph(f"PURCHASE {purchase_index}", ParagraphStyle(
                "PurchaseChip", parent=small_style, fontName="Helvetica-Bold", textColor=colors.white,
                fontSize=7.3, leading=9
            )),
            Paragraph(supplier, ParagraphStyle(
                "Supplier", parent=section_style, fontSize=12.5, leading=14.5, spaceAfter=0
            )),
            Paragraph(_pdf_money(purchase.get("grand_total")), ParagraphStyle(
                "PurchaseTotal", parent=section_style, alignment=TA_RIGHT, fontSize=12.5, leading=14.5, spaceAfter=0
            )),
        ]]
        purchase_header = Table(header_data, colWidths=[26*mm, 135*mm, 35*mm])
        purchase_header.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (0,0), brand),
            ("BACKGROUND", (1,0), (-1,0), soft),
            ("BOX", (0,0), (-1,0), 0.6, line),
            ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
            ("LEFTPADDING", (0,0), (-1,-1), 3*mm),
            ("RIGHTPADDING", (0,0), (-1,-1), 3*mm),
            ("TOPPADDING", (0,0), (-1,-1), 2.4*mm),
            ("BOTTOMPADDING", (0,0), (-1,-1), 2.4*mm),
        ]))
        story.append(purchase_header)

        info_data = [
            [Paragraph("PLACE", metric_label), Paragraph("PURCHASE DATE", metric_label), Paragraph("BILL / ORDER NO.", metric_label),
             Paragraph("TRANSPORT", metric_label), Paragraph("ORDERED BY", metric_label)],
            [Paragraph(place, body_style), Paragraph(date, body_style), Paragraph(bill, body_style),
             Paragraph(transport, body_style), Paragraph(ordered_by, body_style)],
        ]
        info_table = Table(info_data, colWidths=[39*mm, 36*mm, 43*mm, 39*mm, 39*mm])
        info_table.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), blush),
            ("BOX", (0,0), (-1,-1), 0.45, line),
            ("INNERGRID", (0,0), (-1,-1), 0.35, line),
            ("VALIGN", (0,0), (-1,-1), "TOP"),
            ("TOPPADDING", (0,0), (-1,-1), 2*mm),
            ("BOTTOMPADDING", (0,0), (-1,-1), 2*mm),
            ("LEFTPADDING", (0,0), (-1,-1), 2.5*mm),
            ("RIGHTPADDING", (0,0), (-1,-1), 2.5*mm),
        ]))
        story.append(info_table)
        story.append(Spacer(1, 2.5*mm))

        items = items_by_purchase.get(purchase.get("_id"), [])
        item_rows = [[
            Paragraph("PHOTO", metric_label), Paragraph("PRODUCT", metric_label), Paragraph("CATEGORY / BRAND", metric_label),
            Paragraph("SIZE", metric_label), Paragraph("QTY", metric_label), Paragraph("METER", metric_label),
            Paragraph("PURCHASE RATE", metric_label), Paragraph("MRP", metric_label), Paragraph("DISCOUNT", metric_label),
            Paragraph("SELLING", metric_label), Paragraph("TOTAL", metric_label), Paragraph("NOTES", metric_label),
        ]]

        for item in items:
            product_name = _pdf_text(item.get("product_name"))
            category_brand = " / ".join(x for x in [str(item.get("subcategory") or "").strip(), str(item.get("brand_name") or "").strip()] if x) or "-"
            item_rows.append([
                _gridfs_image_flowable(item.get("image_file_id")),
                Paragraph(product_name, body_style),
                Paragraph(_pdf_text(category_brand), small_style),
                Paragraph(_pdf_text(item.get("size_value")), small_style),
                Paragraph(str(item.get("quantity", 0) or 0), body_style),
                Paragraph(_pdf_num(item.get("meter_quantity", 0)), body_style),
                Paragraph(_pdf_money(item.get("purchase_price", 0)), body_style),
                Paragraph(_pdf_money(item.get("mrp", 0)), body_style),
                Paragraph(_discount_label(item), body_style),
                Paragraph(_pdf_money(item.get("selling_price", 0)), body_style),
                Paragraph(_pdf_money(item.get("line_total", 0)), body_style),
                Paragraph(_pdf_text(item.get("notes")), small_style),
            ])

        if len(item_rows) == 1:
            item_rows.append([Paragraph("No items", small_style)] + [""]*11)

        col_widths = [18*mm, 31*mm, 29*mm, 16*mm, 12*mm, 13*mm, 24*mm, 21*mm, 20*mm, 21*mm, 23*mm, 31*mm]
        items_table = Table(item_rows, colWidths=col_widths, repeatRows=1)
        items_table.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), brand_dark),
            ("TEXTCOLOR", (0,0), (-1,0), colors.white),
            ("BOX", (0,0), (-1,-1), 0.45, line),
            ("INNERGRID", (0,0), (-1,-1), 0.3, line),
            ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, soft]),
            ("TOPPADDING", (0,0), (-1,-1), 1.6*mm),
            ("BOTTOMPADDING", (0,0), (-1,-1), 1.6*mm),
            ("LEFTPADDING", (0,0), (-1,-1), 1.5*mm),
            ("RIGHTPADDING", (0,0), (-1,-1), 1.5*mm),
        ]))
        story.append(items_table)

        totals_data = [[
            Paragraph(f"Quantity: <b>{int(purchase.get('total_quantity', 0) or 0)} pcs</b>", body_style),
            Paragraph(f"Meter: <b>{_pdf_num(purchase.get('total_meter', 0))} m</b>", body_style),
            Paragraph(f"Purchase Total: <b>{_pdf_money(purchase.get('grand_total', 0))}</b>", ParagraphStyle(
                "TotalRight", parent=body_style, alignment=TA_RIGHT, textColor=brand, fontName="Helvetica-Bold"
            )),
        ]]
        totals_table = Table(totals_data, colWidths=[55*mm, 55*mm, 86*mm])
        totals_table.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,-1), blush),
            ("BOX", (0,0), (-1,-1), 0.45, line),
            ("TOPPADDING", (0,0), (-1,-1), 2*mm),
            ("BOTTOMPADDING", (0,0), (-1,-1), 2*mm),
            ("LEFTPADDING", (0,0), (-1,-1), 2.5*mm),
            ("RIGHTPADDING", (0,0), (-1,-1), 2.5*mm),
        ]))
        story.append(totals_table)
        story.append(Spacer(1, 5*mm))

    def page_decor(canvas, doc_obj):
        canvas.saveState()
        width, height = page_size
        canvas.setFillColor(brand)
        canvas.rect(0, height-8*mm, width, 8*mm, fill=1, stroke=0)
        canvas.setFillColor(colors.HexColor("#6F666A"))
        canvas.setFont("Helvetica", 6.5)
        canvas.drawString(10*mm, 6*mm, "Maharani Purchase Manager")
        canvas.drawRightString(width-10*mm, 6*mm, f"Page {doc_obj.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=page_decor, onLaterPages=page_decor)
    buffer.seek(0)
    return buffer


@app.route("/api/purchases/history.pdf", methods=["GET"])
def purchase_history_pdf():
    if db is None:
        return jsonify({"error": "MongoDB not configured"}), 503
    pdf_buffer = build_purchase_history_pdf()
    filename = f"Maharani_Purchase_History_{datetime.now().strftime('%Y-%m-%d')}.pdf"
    return send_file(
        pdf_buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
        max_age=0,
    )

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
