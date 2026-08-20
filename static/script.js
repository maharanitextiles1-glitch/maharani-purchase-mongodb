
let currentPurchase=null;
const money=v=>new Intl.NumberFormat("en-IN",{style:"currency",currency:"INR",maximumFractionDigits:2}).format(Number(v)||0);
const fmt=v=>new Intl.NumberFormat("en-IN",{maximumFractionDigits:2}).format(Number(v)||0);
const productList=document.getElementById("productList");
const template=document.getElementById("productTemplate");
const emptyState=document.getElementById("emptyState");
document.getElementById("purchaseDate").valueAsDate=new Date();

function toast(msg){const t=document.createElement("div");t.className="toast";t.textContent=msg;document.body.appendChild(t);setTimeout(()=>t.remove(),2600);}
function preview(card,file){if(!file)return;const img=card.querySelector(".preview");img.src=URL.createObjectURL(file);img.style.display="block";card.querySelector(".photo-placeholder").style.display="none";}
function calcPricing(card){
 const cost=Number(card.querySelector(".price").value)||0,method=card.querySelector(".pricing-method").value,pct=Number(card.querySelector(".pricing-percent").value)||0,mrpInput=card.querySelector(".mrp");let mrp=Number(mrpInput.value)||0;
 if(!mrpInput.dataset.manual||mrpInput.dataset.manual==="false"){if(cost>0&&pct>0){if(method==="markup")mrp=cost*(1+pct/100);else if(method==="margin"&&pct<100)mrp=cost/(1-pct/100);else if(method==="markdown")mrp=cost*(1-pct/100);if(mrp>0)mrpInput.value=mrp.toFixed(2);}}
 const d=Number(card.querySelector(".discount").value)||0;card.querySelector(".selling-price").textContent=money(mrp>0?mrp*(1-d/100):0);
}
function updateCard(card){const q=Number(card.querySelector(".qty").value)||0,m=Number(card.querySelector(".meter").value)||0,p=Number(card.querySelector(".price").value)||0;card.querySelector(".line-total").textContent=money((q>0?q:m)*p);calcPricing(card);updateSummary();}
function addProduct(){
 const node=template.content.cloneNode(true),card=node.querySelector(".product-card");
 ["qty","meter","price","pricing-percent","discount"].forEach(c=>node.querySelector("."+c).addEventListener("input",()=>updateCard(card)));
 node.querySelector(".pricing-method").addEventListener("change",()=>updateCard(card));
 const mrp=node.querySelector(".mrp");mrp.addEventListener("input",()=>{mrp.dataset.manual=mrp.value?"true":"false";updateCard(card);});
 node.querySelector(".delete-btn").onclick=()=>{card.remove();updateSummary();};
 const up=node.querySelector(".upload-input"),cam=node.querySelector(".camera-input");
 node.querySelector(".upload-btn").onclick=()=>up.click();node.querySelector(".camera-btn").onclick=()=>cam.click();
 up.onchange=()=>{if(up.files?.[0]){cam.value="";preview(card,up.files[0]);}};
 cam.onchange=()=>{if(cam.files?.[0]){up.value="";preview(card,cam.files[0]);}};
 productList.appendChild(node);updateSummary();
}
function updateSummary(){
 const cards=[...document.querySelectorAll(".product-card")];let q=0,m=0,t=0;
 cards.forEach(c=>{const a=Number(c.querySelector(".qty").value)||0,b=Number(c.querySelector(".meter").value)||0,p=Number(c.querySelector(".price").value)||0;q+=a;m+=b;t+=(a>0?a:b)*p;});
 productCount.textContent=cards.length;totalQuantity.textContent=q;totalMeter.textContent=`${fmt(m)} m`;grandTotal.textContent=money(t);bottomQty.textContent=q;bottomMeter.textContent=`${fmt(m)} m`;bottomGrandTotal.textContent=money(t);emptyState.style.display=cards.length?"none":"block";
}
function clearForm(){productList.innerHTML="";["supplierName","supplierPlace","billNumber","orderedBy"].forEach(id=>document.getElementById(id).value="");transportMethod.value="";purchaseDate.valueAsDate=new Date();updateSummary();}
async function savePurchase(){
 const cards=[...document.querySelectorAll(".product-card")],supplier=supplierName.value.trim(),date=purchaseDate.value;
 if(!supplier)return toast("Enter supplier / party name.");if(!date)return toast("Select purchase date.");if(!cards.length)return toast("Add at least one product.");
 const items=[];
 for(let i=0;i<cards.length;i++){const c=cards[i],name=c.querySelector(".product-name").value.trim(),quantity=Number(c.querySelector(".qty").value)||0,meterQuantity=Number(c.querySelector(".meter").value)||0;if(!name)return toast(`Enter product name for item ${i+1}.`);if(quantity<=0&&meterQuantity<=0)return toast(`Enter quantity or meter for ${name}.`);
 items.push({name,subcategory:c.querySelector(".subcategory").value.trim(),brandName:c.querySelector(".brand-name").value.trim(),sizeValue:c.querySelector(".size-value").value.trim(),quantity,meterQuantity,purchasePrice:Number(c.querySelector(".price").value)||0,pricingMethod:c.querySelector(".pricing-method").value,pricingPercent:Number(c.querySelector(".pricing-percent").value)||0,mrp:Number(c.querySelector(".mrp").value)||0,discountPercent:Number(c.querySelector(".discount").value)||0,notes:c.querySelector(".notes").value.trim()});}
 const fd=new FormData();fd.append("supplier_name",supplier);fd.append("supplier_place",supplierPlace.value.trim());fd.append("purchase_date",date);fd.append("bill_number",billNumber.value.trim());fd.append("transport_method",transportMethod.value);fd.append("ordered_by",orderedBy.value.trim());fd.append("items",JSON.stringify(items));
 cards.forEach((c,i)=>{const up=c.querySelector(".upload-input").files?.[0],cam=c.querySelector(".camera-input").files?.[0];if(up)fd.append(`image_${i}`,up);else if(cam)fd.append(`camera_${i}`,cam);});
 saveBtn.disabled=true;saveBtn.textContent="Saving...";
 try{const r=await fetch("/api/purchases",{method:"POST",body:fd}),d=await r.json();if(!r.ok)throw new Error(d.error||"Could not save purchase.");toast("Purchase saved.");clearForm();loadHistory();}catch(e){toast(e.message);}finally{saveBtn.disabled=false;saveBtn.textContent="Save Purchase to Database";}
}
async function loadHistory(){
 historyList.innerHTML='<div class="empty-history">Loading...</div>';
 try{const r=await fetch("/api/purchases"),arr=await r.json();if(!arr.length){historyList.innerHTML='<div class="empty-history">No saved purchases yet.</div>';return;}historyList.innerHTML=arr.map(p=>`<div class="history-row"><div><strong>${esc(p.supplier_name)}</strong><small>${esc(p.supplier_place||"—")}</small></div><div><strong>${esc(p.purchase_date)}</strong><small>${esc(p.transport_method||"No transport")}</small></div><div><strong>${p.total_quantity||0} pcs / ${fmt(p.total_meter||0)} m</strong><small>Purchased</small></div><div><strong class="amount">${money(p.grand_total)}</strong><small>Total</small></div><div class="history-actions"><button class="secondary" onclick="viewPurchase('${p.id}')">View</button><button class="secondary danger" onclick="deletePurchase('${p.id}')">Delete</button></div></div>`).join("");}catch{historyList.innerHTML='<div class="empty-history">Could not load purchase history.</div>';}
}
async function viewPurchase(id){
 const r=await fetch(`/api/purchases/${id}`),p=await r.json();if(!r.ok)return toast(p.error||"Could not open purchase.");currentPurchase=p;modalTitle.textContent=`Purchase ${p.id}`;
 modalContent.innerHTML=`<div class="meta-grid"><div><span>Supplier</span><strong>${esc(p.supplier_name)}</strong></div><div><span>Place</span><strong>${esc(p.supplier_place||"—")}</strong></div><div><span>Date</span><strong>${esc(p.purchase_date)}</strong></div><div><span>Bill / Order No.</span><strong>${esc(p.bill_number||"—")}</strong></div><div><span>Transport</span><strong>${esc(p.transport_method||"—")}</strong></div><div><span>Ordered By</span><strong>${esc(p.ordered_by||"—")}</strong></div></div><div class="detail-list">${p.items.map(i=>`<div class="detail-item">${i.image_url?`<img src="${i.image_url}">`:`<div class="no-img">No image</div>`}<div><strong>${esc(i.product_name)}</strong><small>${esc(i.subcategory||"")} ${i.brand_name?"• "+esc(i.brand_name):""} ${i.size_value?"• "+esc(i.size_value):""}</small><small>Qty ${i.quantity||0} • Meter ${fmt(i.meter_quantity||0)} • Purchase ${money(i.purchase_price)}</small><small>${i.pricing_method?esc(i.pricing_method)+" "+fmt(i.pricing_percent)+"% • ":""}MRP ${money(i.mrp)} • Discount ${fmt(i.discount_percent)}% • Selling ${money(i.selling_price)}</small></div><strong>${money(i.line_total)}</strong></div>`).join("")}</div><div class="modal-total">${p.total_quantity||0} pcs • ${fmt(p.total_meter||0)} m • ${money(p.grand_total)}</div>`;
 detailModal.classList.add("show");
}
async function deletePurchase(id){if(!confirm("Delete this purchase?"))return;const r=await fetch(`/api/purchases/${id}`,{method:"DELETE"});if(!r.ok)return toast("Could not delete.");toast("Purchase deleted.");loadHistory();}


function printPurchase(){
  if(!currentPurchase) return toast("Open a purchase first.");

  const p = currentPurchase;
  const w = window.open("", "_blank");

  const rows = (p.items || []).map((i, n) => `
    <tr>
      <td>${n + 1}</td>
      <td>${i.image_url ? `<img src="${i.image_url}" class="product-photo" alt="Product image">` : "No photo"}</td>
      <td>${esc(i.product_name || "")}</td>
      <td>${esc(i.subcategory || "")}</td>
      <td>${esc(i.brand_name || "")}</td>
      <td>${esc(i.size_value || "")}</td>
      <td>${i.quantity || 0}</td>
      <td>${fmt(i.meter_quantity || 0)} m</td>
      <td>${money(i.purchase_price || 0)}</td>
      <td>${money(i.mrp || 0)}</td>
      <td>${fmt(i.discount_percent || 0)}%</td>
      <td>${money(i.selling_price || 0)}</td>
      <td>${money(i.line_total || 0)}</td>
      <td>${esc(i.notes || "")}</td>
    </tr>
  `).join("");

  const whatsappText = encodeURIComponent(
    `Maharani Wedding Collections - Purchase Details\n\n` +
    `Supplier: ${p.supplier_name || "—"}\n` +
    `Place: ${p.supplier_place || "—"}\n` +
    `Purchase Date: ${p.purchase_date || "—"}\n` +
    `Bill / Order No.: ${p.bill_number || "—"}\n` +
    `Transport: ${p.transport_method || "—"}\n` +
    `Ordered By: ${p.ordered_by || "—"}\n\n` +
    (p.items || []).map((i, n) =>
      `${n + 1}. ${i.product_name || ""} | Qty ${i.quantity || 0} | Meter ${fmt(i.meter_quantity || 0)} | Purchase Rate ${money(i.purchase_price || 0)} | MRP ${money(i.mrp || 0)} | Discount ${fmt(i.discount_percent || 0)}% | Selling ${money(i.selling_price || 0)} | Total ${money(i.line_total || 0)}`
    ).join("\n") +
    `\n\nGrand Total: ${money(p.grand_total || 0)}`
  );

  w.document.write(`
    <html>
    <head>
      <meta charset="utf-8">
      <title>Purchase Details</title>
      <style>
        *{box-sizing:border-box}
        body{font-family:Arial,sans-serif;color:#222;padding:18px;margin:0;background:#fff}
        .toolbar{display:flex;justify-content:flex-end;gap:8px;margin-bottom:14px}
        .toolbar a,.toolbar button{border:0;border-radius:8px;padding:10px 14px;font-weight:700;text-decoration:none;cursor:pointer}
        .whatsapp-btn{background:#25D366;color:#fff}
        .print-btn{background:#8d1738;color:#fff}
        .header{border-bottom:2px solid #8d1738;padding-bottom:12px;margin-bottom:15px}
        h1{margin:0;color:#8d1738;font-size:22px}
        .subtitle{margin-top:4px;font-size:12px;color:#666}
        .meta{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:16px}
        .meta div{border:1px solid #ddd;border-radius:7px;padding:8px}
        .meta span{display:block;font-size:9px;color:#777;margin-bottom:3px;text-transform:uppercase}
        .meta strong{font-size:11px}
        table{width:100%;border-collapse:collapse;font-size:7.5px}
        th,td{border:1px solid #d9d9d9;padding:4px;vertical-align:top;text-align:left}
        th{background:#f6eef1;color:#5d1730}
        .product-photo{width:48px;height:48px;object-fit:cover;border-radius:5px}
        .totals{display:flex;justify-content:flex-end;gap:18px;margin-top:14px;padding-top:10px;border-top:1px solid #ddd;font-size:11px}
        .grand{color:#8d1738;font-size:17px;font-weight:700}
        .md-approval{margin-top:36px;border:1.5px solid #777;border-radius:8px;min-height:150px;padding:12px;page-break-inside:avoid}
        .md-approval h3{margin:0;color:#8d1738;font-size:13px}
        .approval-space{height:82px}
        .approval-bottom{display:grid;grid-template-columns:1fr 1fr;gap:32px}
        .approval-line{border-top:1px solid #777;padding-top:5px;font-size:9px;text-align:center;color:#666}
        .footer{margin-top:18px;font-size:8px;color:#888;text-align:center}
        @page{size:A4 landscape;margin:10mm}
        @media print{
          body{padding:0}
          .no-print{display:none!important}
        }
      </style>
    </head>
    <body>
      <div class="toolbar no-print">
        <a class="whatsapp-btn" href="https://wa.me/?text=${whatsappText}" target="_blank" rel="noopener noreferrer">Share on WhatsApp</a>
        <button class="print-btn" type="button" onclick="window.print()">Print</button>
      </div>

      <div class="header">
        <h1>Maharani Wedding Collections</h1>
        <div class="subtitle">Purchase Details</div>
      </div>

      <div class="meta">
        <div><span>Supplier / Party Name</span><strong>${esc(p.supplier_name || "—")}</strong></div>
        <div><span>Place</span><strong>${esc(p.supplier_place || "—")}</strong></div>
        <div><span>Purchase Date</span><strong>${esc(p.purchase_date || "—")}</strong></div>
        <div><span>Bill / Order No.</span><strong>${esc(p.bill_number || "—")}</strong></div>
        <div><span>Transport</span><strong>${esc(p.transport_method || "—")}</strong></div>
        <div><span>Ordered By</span><strong>${esc(p.ordered_by || "—")}</strong></div>
        <div><span>Total Quantity</span><strong>${p.total_quantity || 0} pcs</strong></div>
        <div><span>Total Meter</span><strong>${fmt(p.total_meter || 0)} m</strong></div>
        <div><span>Grand Total</span><strong>${money(p.grand_total || 0)}</strong></div>
      </div>

      <table>
        <thead>
          <tr>
            <th>#</th><th>Photo</th><th>Product Name</th><th>Subcategory</th><th>Brand Name</th><th>Size</th>
            <th>Quantity</th><th>Meter Qty</th><th>Purchase Rate</th><th>MRP</th><th>Discount</th>
            <th>Selling Price</th><th>Item Total</th><th>Notes</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>

      <div class="totals">
        <div><strong>Total Quantity:</strong> ${p.total_quantity || 0} pcs</div>
        <div><strong>Total Meter:</strong> ${fmt(p.total_meter || 0)} m</div>
        <div class="grand">Grand Total: ${money(p.grand_total || 0)}</div>
      </div>

      <div class="md-approval">
        <h3>MD Approval</h3>
        <div class="approval-space"></div>
        <div class="approval-bottom">
          <div class="approval-line">MD Signature</div>
          <div class="approval-line">Date</div>
        </div>
      </div>

      <div class="footer">Printed from Maharani Purchase Manager</div>
    </body>
    </html>
  `);

  w.document.close();
}
function esc(v){return String(v??"").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;").replaceAll("'","&#039;");}
addProductBtn.onclick=addProduct;emptyAddBtn.onclick=addProduct;saveBtn.onclick=savePurchase;clearBtn.onclick=clearForm;refreshHistoryBtn.onclick=loadHistory;printBtn.onclick=printPurchase;closeModalBtn.onclick=()=>detailModal.classList.remove("show");
document.querySelectorAll(".nav-btn").forEach(b=>b.onclick=()=>{document.querySelectorAll(".nav-btn").forEach(x=>x.classList.remove("active"));b.classList.add("active");document.querySelectorAll(".view").forEach(v=>v.classList.remove("active-view"));document.getElementById(b.dataset.view).classList.add("active-view");if(b.dataset.view==="historyView")loadHistory();});
window.viewPurchase=viewPurchase;window.deletePurchase=deletePurchase;updateSummary();loadHistory();
