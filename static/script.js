
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
 try{const r=await fetch("/api/purchases",{method:"POST",body:fd}),d=await r.json();if(!r.ok)throw new Error(d.error||"Could not save purchase.");toast("DP saved.");clearForm();loadHistory();}catch(e){toast(e.message);}finally{saveBtn.disabled=false;saveBtn.textContent="Save DP to Database";}
}
async function loadHistory(){
  historyList.innerHTML='<div class="empty-history">Loading...</div>';
  const params=new URLSearchParams();
  const search=document.getElementById("historySearch")?.value.trim();
  const purchaser=document.getElementById("historyPurchaser")?.value.trim();
  const dateFrom=document.getElementById("historyDateFrom")?.value;
  const dateTo=document.getElementById("historyDateTo")?.value;
  if(search) params.set("search",search);
  if(purchaser) params.set("purchaser",purchaser);
  if(dateFrom) params.set("date_from",dateFrom);
  if(dateTo) params.set("date_to",dateTo);
  try{
    const r=await fetch(`/api/purchases${params.toString()?"?"+params.toString():""}`),arr=await r.json();
    if(!arr.length){historyList.innerHTML='<div class="empty-history">No DP records found.</div>';return;}
    historyList.innerHTML=arr.map(p=>`<div class="history-row"><div><strong>${esc(p.supplier_name)}</strong><small>${esc(p.supplier_place||"—")}</small></div><div><strong>${esc(p.purchase_date)}</strong><small>${esc(p.ordered_by||"No purchaser")}</small></div><div><strong>${p.total_quantity||0} pcs / ${fmt(p.total_meter||0)} m</strong><small>DP Qty</small></div><div><strong class="amount">${money(p.grand_total)}</strong><small>DP Total</small></div><div class="history-actions"><button class="secondary" onclick="viewPurchase('${p.id}')">View</button><button class="secondary" onclick="sharePurchase('${p.id}')">Share</button><button class="secondary danger" onclick="deletePurchase('${p.id}')">Delete</button></div></div>`).join("");
  }catch{historyList.innerHTML='<div class="empty-history">Could not load DP history.</div>';}
}
async function viewPurchase(id){
 const r=await fetch(`/api/purchases/${id}`),p=await r.json();if(!r.ok)return toast(p.error||"Could not open purchase.");currentPurchase=p;modalTitle.textContent=`Purchase ${p.id}`;
 modalContent.innerHTML=`<div class="meta-grid"><div><span>Supplier</span><strong>${esc(p.supplier_name)}</strong></div><div><span>Place</span><strong>${esc(p.supplier_place||"—")}</strong></div><div><span>Date</span><strong>${esc(p.purchase_date)}</strong></div><div><span>Bill / Order No.</span><strong>${esc(p.bill_number||"—")}</strong></div><div><span>Transport</span><strong>${esc(p.transport_method||"—")}</strong></div><div><span>Ordered By</span><strong>${esc(p.ordered_by||"—")}</strong></div></div><div class="detail-list">${p.items.map(i=>`<div class="detail-item">${i.image_url?`<img src="${i.image_url}">`:`<div class="no-img">No image</div>`}<div><strong>${esc(i.product_name)}</strong><small>${esc(i.subcategory||"")} ${i.brand_name?"• "+esc(i.brand_name):""} ${i.size_value?"• "+esc(i.size_value):""}</small><small>Qty ${i.quantity||0} • Meter ${fmt(i.meter_quantity||0)} • Purchase ${money(i.purchase_price)}</small><small>${i.pricing_method?esc(i.pricing_method)+" "+fmt(i.pricing_percent)+"% • ":""}MRP ${money(i.mrp)} • Discount ${fmt(i.discount_percent)}% • Selling ${money(i.selling_price)}</small></div><strong>${money(i.line_total)}</strong></div>`).join("")}</div><div class="modal-total">${p.total_quantity||0} pcs • ${fmt(p.total_meter||0)} m • ${money(p.grand_total)}</div>`;
 detailModal.classList.add("show");
}
async function deletePurchase(id){if(!confirm("Delete this purchase?"))return;const r=await fetch(`/api/purchases/${id}`,{method:"DELETE"});if(!r.ok)return toast("Could not delete.");toast("DP deleted.");loadHistory();}
function printPurchase(){
  if(!currentPurchase)return toast("Open a DP first.");
  const p=currentPurchase,w=window.open("","_blank");
  const rows=p.items.map((i,n)=>`<tr>
    <td>${n+1}</td>
    <td>${i.image_url?`<img src="${i.image_url}" style="width:55px;height:55px;object-fit:cover;border-radius:6px">`:""}</td>
    <td>${esc(i.product_name)}</td><td>${esc(i.subcategory||"")}</td><td>${esc(i.brand_name||"")}</td><td>${esc(i.size_value||"")}</td>
    <td>${i.quantity||0}</td><td>${fmt(i.meter_quantity||0)}</td><td>${money(i.purchase_price)}</td>
    <td>${i.pricing_method?esc(i.pricing_method)+" "+fmt(i.pricing_percent)+"%":"—"}</td><td>${money(i.mrp)}</td><td>${fmt(i.discount_percent)}%</td>
    <td>${money(i.selling_price)}</td><td>${money(i.line_total)}</td><td>${esc(i.notes||"")}</td>
  </tr>`).join("");
  w.document.write(`<html><head><title>DP ${esc(p.id)}</title><style>
  body{font-family:Arial,sans-serif;padding:18px;color:#222}h1{margin:0;color:#8d1738;font-size:22px}.sub{font-size:12px;color:#666;margin-top:4px}
  .meta{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:16px 0}.meta div{border:1px solid #ddd;padding:8px;border-radius:7px}.meta span{display:block;font-size:10px;color:#777;margin-bottom:3px}
  table{width:100%;border-collapse:collapse;font-size:8px}th,td{border:1px solid #ddd;padding:4px;text-align:left;vertical-align:top}th{background:#f6eef1}.total{text-align:right;font-size:18px;font-weight:700;color:#8d1738;margin-top:14px}@media print{body{padding:0}}
  </style></head><body><h1>Maharani Wedding Collections</h1><div class="sub">DP Record</div>
  <div class="meta"><div><span>Supplier / Party</span><b>${esc(p.supplier_name)}</b></div><div><span>Place</span><b>${esc(p.supplier_place||"—")}</b></div><div><span>DP Date</span><b>${esc(p.purchase_date)}</b></div><div><span>Bill / Order No.</span><b>${esc(p.bill_number||"—")}</b></div><div><span>Transport</span><b>${esc(p.transport_method||"—")}</b></div><div><span>Ordered By</span><b>${esc(p.ordered_by||"—")}</b></div><div><span>Total Quantity</span><b>${p.total_quantity||0} pcs</b></div><div><span>Total Meter</span><b>${fmt(p.total_meter||0)} m</b></div><div><span>DP Total</span><b>${money(p.grand_total)}</b></div></div>
  <table><thead><tr><th>#</th><th>Photo</th><th>Product</th><th>Subcategory</th><th>Brand</th><th>Size</th><th>Qty</th><th>Meter</th><th>Purchase Price</th><th>Markup/Margin/Markdown</th><th>MRP</th><th>Discount</th><th>Selling Price</th><th>Item Total</th><th>Notes</th></tr></thead><tbody>${rows}</tbody></table>
  <div class="total">DP Total: ${money(p.grand_total)}</div><script>window.onload=()=>setTimeout(()=>window.print(),300);<\/script></body></html>`);w.document.close();
}

async function sharePurchase(id){
  const r=await fetch(`/api/purchases/${id}`),p=await r.json();
  if(!r.ok)return toast(p.error||"Could not open DP.");
  const itemText=(p.items||[]).map((i,n)=>`${n+1}. ${i.product_name} | Qty ${i.quantity||0} | Meter ${fmt(i.meter_quantity||0)} | MRP ${money(i.mrp)} | Total ${money(i.line_total)}`).join("\\n");
  const text=`Maharani DP\\nSupplier: ${p.supplier_name}\\nPlace: ${p.supplier_place||"—"}\\nDate: ${p.purchase_date}\\nOrdered By: ${p.ordered_by||"—"}\\nTransport: ${p.transport_method||"—"}\\n\\n${itemText}\\n\\nDP Total: ${money(p.grand_total)}`;
  if(navigator.share){try{await navigator.share({title:"Maharani DP",text});}catch(e){}}
  else{window.prompt("Copy and share this DP:",text);}
}

function esc(v){return String(v??"").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;").replaceAll("'","&#039;");}
addProductBtn.onclick=addProduct;emptyAddBtn.onclick=addProduct;saveBtn.onclick=savePurchase;clearBtn.onclick=clearForm;refreshHistoryBtn.onclick=loadHistory;printBtn.onclick=printPurchase;closeModalBtn.onclick=()=>detailModal.classList.remove("show");
document.querySelectorAll(".nav-btn").forEach(b=>b.onclick=()=>{document.querySelectorAll(".nav-btn").forEach(x=>x.classList.remove("active"));b.classList.add("active");document.querySelectorAll(".view").forEach(v=>v.classList.remove("active-view"));document.getElementById(b.dataset.view).classList.add("active-view");if(b.dataset.view==="historyView")loadHistory();});
window.viewPurchase=viewPurchase;window.deletePurchase=deletePurchase;
document.getElementById("applyHistoryFilters")?.addEventListener("click",loadHistory);
document.getElementById("clearHistoryFilters")?.addEventListener("click",()=>{
  ["historySearch","historyPurchaser","historyDateFrom","historyDateTo"].forEach(id=>{const el=document.getElementById(id);if(el)el.value="";});
  loadHistory();
});
["historySearch","historyPurchaser"].forEach(id=>document.getElementById(id)?.addEventListener("keydown",e=>{if(e.key==="Enter")loadHistory();}));
document.getElementById("shareCurrentBtn")?.addEventListener("click",()=>{if(currentPurchase)sharePurchase(currentPurchase.id);});
window.sharePurchase=sharePurchase;
updateSummary();loadHistory();
