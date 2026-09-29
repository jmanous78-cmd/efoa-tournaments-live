const DATA="data/tournaments.json", KEY="efoa-live-v5", NOTIFY_KEY="efoa-browser-alerts-v2", ATH={lat:37.9838,lon:23.7275};
const ALERT_CONFIG="config/alerts.json";
let events=[],map,markers;
const _now=new Date(), _localToday=new Date(_now.getTime()-_now.getTimezoneOffset()*60000).toISOString().slice(0,10);
let state={level:"ALL",gender:"ALL",age:"ALL",union:"ALL",from:_localToday,to:"",deadline:"ALL",search:"",favorites:["Α14"],favoritesOnly:true,browserAlerts:false};
let serverAlertCategories=["Α14"];
const $=id=>document.getElementById(id), norm=s=>String(s||"").normalize("NFD").replace(/[\u0300-\u036f]/g,"").toUpperCase();

function cats(e){return e.categories||[]}
function unions(e){return e.unions?.length?e.unions:(e.union?[e.union]:[])}
function fmt(d){return d?new Intl.DateTimeFormat("el-GR",{day:"2-digit",month:"2-digit",year:"numeric"}).format(new Date(d+"T12:00:00")):"—"}
function fmtDT(d){return d?new Intl.DateTimeFormat("el-GR",{day:"2-digit",month:"2-digit",hour:"2-digit",minute:"2-digit"}).format(new Date(d)):"—"}
function hoursValue(v){return v?(new Date(v)-new Date())/36e5:null}
function deadlineEntries(e){
 return [
  {type:"registration",label:"Εγγραφή",field:"registration_deadline",value:e.registration_deadline},
  {type:"payment",label:"Πληρωμή",field:"payment_deadline",value:e.payment_deadline}
 ].filter(x=>x.value);
}
function mine(e){return cats(e).some(c=>state.favorites.includes(c))}
function km(a,b,c,d){const R=6371,r=x=>x*Math.PI/180,z=Math.sin(r(c-a)/2)**2+Math.cos(r(a))*Math.cos(r(c))*Math.sin(r(d-b)/2)**2;return 2*R*Math.asin(Math.sqrt(z))}
function save(){localStorage.setItem(KEY,JSON.stringify(state))}
function load(){
 try{Object.assign(state,JSON.parse(localStorage.getItem(KEY)||"{}"))}catch{}
 if(["OPEN","72","24"].includes(state.deadline))state.deadline="ALL";
}
function deadlineMatches(e){
 const rh=hoursValue(e.registration_deadline), ph=hoursValue(e.payment_deadline);
 switch(state.deadline){
  case "REG_OPEN": return rh!=null&&rh>=0;
  case "REG_72": return rh!=null&&rh>=0&&rh<=72;
  case "REG_24": return rh!=null&&rh>=0&&rh<=24;
  case "PAY_OPEN": return ph!=null&&ph>=0;
  case "PAY_72": return ph!=null&&ph>=0&&ph<=72;
  case "PAY_24": return ph!=null&&ph>=0&&ph<=24;
  case "NONE": return !e.registration_deadline&&!e.payment_deadline;
  default:return true;
 }
}
function match(e){
 if(state.level!=="ALL"&&e.level!==state.level)return false;
 if(state.favoritesOnly&&!mine(e))return false;
 if(state.gender!=="ALL"&&!cats(e).some(c=>c.startsWith(state.gender==="M"?"Μ":state.gender==="A"?"Α":"Κ")))return false;
 if(state.age!=="ALL"&&!cats(e).some(c=>c.endsWith(state.age)))return false;
 if(state.union!=="ALL"&&!unions(e).includes(state.union))return false;
 if(state.from&&e.end<state.from)return false;if(state.to&&e.start>state.to)return false;
 if(!deadlineMatches(e))return false;
 if(state.search&&!norm([e.title,e.venue,e.city,...unions(e),...cats(e)].join(" ")).includes(norm(state.search)))return false;
 return true;
}

function notifyState(){try{return JSON.parse(localStorage.getItem(NOTIFY_KEY)||"{}")}catch{return {}}}
function saveNotifyState(s){localStorage.setItem(NOTIFY_KEY,JSON.stringify(s))}
function notificationStatus(){
 const btn=$("enableAlerts"), status=$("alertStatus");
 const granted=("Notification" in window)&&Notification.permission==="granted";
 if(btn){btn.textContent=granted&&state.browserAlerts?"Browser alerts ενεργά":"Ενεργοποίηση browser alerts";btn.classList.toggle("enabled",granted&&state.browserAlerts)}
 if(status){status.textContent=`Background GitHub alerts: ${serverAlertCategories.join(", ")} · ξεχωριστά για εγγραφή & πληρωμή · Browser alerts: ${granted&&state.browserAlerts?"ενεργά όσο το site είναι ανοιχτό":"ανενεργά"}`}
}
function fireBrowserNotification(title,body,url){
 if(!state.browserAlerts||!("Notification" in window)||Notification.permission!=="granted")return;
 const n=new Notification(title,{body});
 n.onclick=()=>{window.focus();if(url)window.open(url,"_blank")};
}
function checkBrowserAlerts(list,{bootstrap=false}={}){
 if(!state.browserAlerts||!("Notification" in window)||Notification.permission!=="granted")return;
 const ns=notifyState(), known=new Set(ns.known||[]), sent=ns.sent||{};
 const relevant=list.filter(e=>mine(e)&&e.end>=_localToday);
 if(!ns.initialized||bootstrap){
   relevant.forEach(e=>known.add(e.id));
   ns.initialized=true;
 }else{
   relevant.forEach(e=>{
     if(!known.has(e.id)){
       fireBrowserNotification(`Νέο ${e.level} · ${cats(e).join(", ")}`,e.title,e.registration_url||e.source_url);
       known.add(e.id);
     }
   });
 }
 relevant.forEach(e=>{
   deadlineEntries(e).forEach(d=>{
     const h=hoursValue(d.value);if(h==null||h<0)return;
     const threshold=h<=24?24:h<=72?72:null;if(!threshold)return;
     const key=`${e.id}:${d.type}:${d.value}:${threshold}`;
     if(!sent[key]){
       fireBrowserNotification(`${d.label} σε ≤${threshold} ώρες`,`${e.title} · ${fmtDT(d.value)}`,e.registration_url||e.source_url);
       sent[key]=new Date().toISOString();
     }
   });
 });
 ns.known=[...known];ns.sent=sent;saveNotifyState(ns);
}
async function enableBrowserAlerts(){
 if(!("Notification" in window)){alert("Ο browser δεν υποστηρίζει notifications.");return}
 const permission=await Notification.requestPermission();
 state.browserAlerts=permission==="granted";save();notificationStatus();
 if(state.browserAlerts)checkBrowserAlerts(events,{bootstrap:false});
}
async function refreshData(){
 try{
  const d=await fetch(DATA+"?t="+Date.now(),{cache:"no-store"}).then(r=>r.json());
  const oldIds=new Set(events.map(e=>e.id));events=d.tournaments||[];
  render();checkBrowserAlerts(events,{bootstrap:oldIds.size===0});
 }catch(e){console.warn("Data refresh failed",e)}
}
async function loadAlertConfig(){
 try{const c=await fetch(ALERT_CONFIG+"?t="+Date.now(),{cache:"no-store"}).then(r=>r.json());serverAlertCategories=c.categories||["Α14"]}catch{}
 notificationStatus();
}

function favUI(){
 const all=["Α10","Α12","Α14","Α16","Α18","Κ10","Κ12","Κ14","Κ16","Κ18","Μ10","Μ12","Μ14","Μ16","Μ18"];
 $("favorites").innerHTML=all.map(c=>`<button class="fav ${state.favorites.includes(c)?"on":""}" data-c="${c}">${c}</button>`).join("");
 document.querySelectorAll(".fav").forEach(b=>b.onclick=()=>{
  state.favorites=state.favorites.includes(b.dataset.c)?state.favorites.filter(x=>x!==b.dataset.c):[...state.favorites,b.dataset.c];
  save();favUI();render()
 });
 $("favoritesOnly").checked=state.favoritesOnly
}
function countdownText(h){
 if(h<0)return "Έληξε";
 if(h<48)return `${Math.ceil(h)} ώρες`;
 return `${Math.ceil(h/24)} ημέρες`;
}
function deadlineTone(h){return h>=0&&h<=24?"urgent":h>=0&&h<=72?"warn":""}
function nextByType(list,type){
 return list.flatMap(e=>deadlineEntries(e).filter(d=>d.type===type).map(d=>({e,d,h:hoursValue(d.value)})))
  .filter(x=>x.h>=0).sort((a,b)=>new Date(a.d.value)-new Date(b.d.value))[0];
}
function deadlineHero(list){
 const box=$("nextDeadline"), reg=nextByType(list,"registration"), pay=nextByType(list,"payment");
 const item=(x,title)=>{
  if(!x)return `<div class="deadline-panel"><h3>${title}</h3><div class="meta">Δεν υπάρχει ενεργή δημοσιευμένη προθεσμία.</div></div>`;
  const {e,d,h}=x,tone=deadlineTone(h);
  return `<div class="deadline-panel ${tone}">
   <h3>${title} · ${e.level}</h3>
   <div class="countdown">${countdownText(h)}</div>
   <div class="deadline-date">${fmtDT(d.value)}</div>
   <div>${e.title} — ${e.venue||e.city||""}</div>
   <div class="links">${e.registration_url?`<a target="_blank" href="${e.registration_url}">e-ΕΦΟΑ</a>`:""}${e.proclamation_url?`<a target="_blank" href="${e.proclamation_url}">Προκήρυξη</a>`:""}</div>
  </div>`;
 };
 box.className="card hero";
 box.innerHTML=`<h2>Επόμενες προθεσμίες</h2><div class="deadline-grid">${item(reg,"📝 Εγγραφή / δήλωση")}${item(pay,"💳 Πληρωμή")}</div>`;
}
function week(list){
 const now=new Date(),limit=new Date(now.getTime()+30*864e5),next=list.filter(e=>new Date(e.end+"T23:59:59")>=now&&new Date(e.start+"T00:00:00")<=limit);
 $("wEvents").textContent=next.length;
 $("wDeadlines").textContent=next.reduce((n,e)=>n+deadlineEntries(e).filter(d=>hoursValue(d.value)>=0).length,0);
 const loc=next.filter(e=>e.lat!=null&&e.lon!=null).map(e=>({...e,dist:km(ATH.lat,ATH.lon,e.lat,e.lon)})).sort((a,b)=>a.dist-b.dist)[0];
 $("wNearest").textContent=loc?Math.round(loc.dist)+" km":"—";$("wNearestText").textContent=loc?`${loc.city||loc.venue} · ευθεία από Αθήνα`:"χωρίς γνωστή έδρα";
}
function deadlineBadge(d){
 const h=hoursValue(d.value),tone=h>=0&&h<=24?"urgent-b":h>=0&&h<=72?"warn-b":d.type==="payment"?"payment-b":"registration-b";
 const status=h<0?"έληξε":h<=24?"≤24h":h<=72?"≤72h":fmtDT(d.value);
 return `<span class="badge ${tone}">${d.type==="registration"?"📝":"💳"} ${d.label}: ${status}</span>`;
}
function render(){
 const list=events.filter(match).sort((a,b)=>a.start.localeCompare(b.start));
 $("count").textContent=list.length+" αποτελέσματα";deadlineHero(list);week(list);
 $("list").innerHTML=list.map(e=>`<article class="event">
  <h3>${e.title}</h3>
  <div class="meta">${fmt(e.start)} – ${fmt(e.end)} · ${e.venue||"Έδρα προς ανακοίνωση"}${e.city?" · "+e.city:""}</div>
  <div class="badges"><span class="badge">${e.level}</span>${cats(e).map(c=>`<span class="badge">${c}</span>`).join("")}${e.categories_status==="inferred-current-year"?'<span class="badge warn-b">Κατηγορίες προς επιβεβαίωση</span>':""}${mine(e)?'<span class="badge mine">★ Δική μου</span>':""}${deadlineEntries(e).map(deadlineBadge).join("")}</div>
  <div class="links">${e.registration_url?`<a target="_blank" href="${e.registration_url}">e-ΕΦΟΑ</a>`:""}${e.source_url?`<a target="_blank" href="${e.source_url}">Πηγή</a>`:""}${e.proclamation_url?`<a target="_blank" href="${e.proclamation_url}">Προκήρυξη</a>`:""}</div>
 </article>`).join("")||'<div class="event">Δεν βρέθηκαν τουρνουά.</div>';
 markers.clearLayers();
 list.filter(e=>e.lat!=null&&e.lon!=null).forEach(e=>L.marker([e.lat,e.lon]).bindPopup(`<b>${e.title}</b><br>${e.venue||""}<br>${fmt(e.start)}–${fmt(e.end)}`).addTo(markers));
}
function bind(){
 ["level","gender","age","union","from","to","deadline","search"].forEach(id=>{let el=$(id);el.value=state[id]||"";el.oninput=()=>{state[id]=el.value;save();render()}});
 $("favoritesOnly").onchange=()=>{state.favoritesOnly=$("favoritesOnly").checked;save();render()};
 $("reset").onclick=()=>{localStorage.removeItem(KEY);location.reload()};
 $("enableAlerts").onclick=enableBrowserAlerts;
 notificationStatus();
}
Promise.all([fetch(DATA,{cache:"no-store"}).then(r=>r.json()),loadAlertConfig()]).then(([d])=>{
 events=d.tournaments||[];load();
 const us=[...new Set(events.flatMap(unions).filter(Boolean))].sort((a,b)=>a.localeCompare(b,"el"));
 $("union").innerHTML='<option value="ALL">Όλες οι Ενώσεις</option>'+us.map(u=>`<option>${u}</option>`).join("");
 map=L.map("map").setView([38.3,23.5],6);
 L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",{maxZoom:19,attribution:"&copy; OpenStreetMap"}).addTo(map);
 markers=L.markerClusterGroup();map.addLayer(markers);
 favUI();bind();render();notificationStatus();
 if(state.browserAlerts)checkBrowserAlerts(events,{bootstrap:!notifyState().initialized});
 setInterval(render,60000);setInterval(refreshData,10*60*1000)
});