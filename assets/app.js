const DATA="data/tournaments.json", KEY="efoa-live-v4", ATH={lat:37.9838,lon:23.7275};
let events=[],map,markers;
const _now=new Date(), _localToday=new Date(_now.getTime()-_now.getTimezoneOffset()*60000).toISOString().slice(0,10);
let state={level:"ALL",gender:"ALL",age:"ALL",union:"ALL",from:_localToday,to:"",deadline:"ALL",search:"",favorites:["Α14"],favoritesOnly:true};
const $=id=>document.getElementById(id), norm=s=>String(s||"").normalize("NFD").replace(/[\u0300-\u036f]/g,"").toUpperCase();
function cats(e){return e.categories||[]}
function unions(e){return e.unions?.length?e.unions:(e.union?[e.union]:[])}
function fmt(d){return d?new Intl.DateTimeFormat("el-GR",{day:"2-digit",month:"2-digit",year:"numeric"}).format(new Date(d+"T12:00:00")):"—"}
function hours(e){return e.deadline?(new Date(e.deadline)-new Date())/36e5:null}
function mine(e){return cats(e).some(c=>state.favorites.includes(c))}
function km(a,b,c,d){const R=6371,r=x=>x*Math.PI/180,z=Math.sin(r(c-a)/2)**2+Math.cos(r(a))*Math.cos(r(c))*Math.sin(r(d-b)/2)**2;return 2*R*Math.asin(Math.sqrt(z))}
function save(){localStorage.setItem(KEY,JSON.stringify(state))}
function load(){try{Object.assign(state,JSON.parse(localStorage.getItem(KEY)||"{}"))}catch{}}
function match(e){
 if(state.level!=="ALL"&&e.level!==state.level)return false;
 if(state.favoritesOnly&&!mine(e))return false;
 if(state.gender!=="ALL"&&!cats(e).some(c=>c.startsWith(state.gender==="M"?"Μ":state.gender==="A"?"Α":"Κ")))return false;
 if(state.age!=="ALL"&&!cats(e).some(c=>c.endsWith(state.age)))return false;
 if(state.union!=="ALL"&&!unions(e).includes(state.union))return false;
 if(state.from&&e.end<state.from)return false;if(state.to&&e.start>state.to)return false;
 const h=hours(e);if(state.deadline==="OPEN"&&!(h>=0))return false;if(state.deadline==="72"&&!(h>=0&&h<=72))return false;if(state.deadline==="24"&&!(h>=0&&h<=24))return false;if(state.deadline==="NONE"&&e.deadline)return false;
 if(state.search&&!norm([e.title,e.venue,e.city,...unions(e),...cats(e)].join(" ")).includes(norm(state.search)))return false;
 return true;
}
function favUI(){const all=["Α10","Α12","Α14","Α16","Α18","Κ10","Κ12","Κ14","Κ16","Κ18","Μ10","Μ12","Μ14","Μ16","Μ18"];$("favorites").innerHTML=all.map(c=>`<button class="fav ${state.favorites.includes(c)?"on":""}" data-c="${c}">${c}</button>`).join("");document.querySelectorAll(".fav").forEach(b=>b.onclick=()=>{state.favorites=state.favorites.includes(b.dataset.c)?state.favorites.filter(x=>x!==b.dataset.c):[...state.favorites,b.dataset.c];save();favUI();render()});$("favoritesOnly").checked=state.favoritesOnly}
function deadlineHero(list){
 const open=list.filter(e=>hours(e)>=0).sort((a,b)=>new Date(a.deadline)-new Date(b.deadline));let box=$("nextDeadline");
 if(!open.length){box.className="card hero";box.innerHTML="<h3>Επόμενη προθεσμία</h3><div>Δεν υπάρχει δημοσιευμένο ενεργό deadline στις τρέχουσες επιλογές.</div>";return}
 const e=open[0],h=hours(e),cls=h<=24?"urgent":h<=72?"warn":"",count=h<48?`${Math.ceil(h)} ώρες`:`${Math.ceil(h/24)} ημέρες`;
 box.className="card hero "+cls;box.innerHTML=`<h3>Επόμενη προθεσμία · ${e.level} · ${cats(e).join(", ")}</h3><div class="countdown">${count}</div><div>${e.title} — ${e.venue||e.city||""}</div><div class="links">${e.registration_url?`<a target="_blank" href="${e.registration_url}">Δηλώσεις</a>`:""}${e.proclamation_url?`<a target="_blank" href="${e.proclamation_url}">Προκήρυξη</a>`:""}</div>`;
}
function week(list){
 const now=new Date(),limit=new Date(now.getTime()+30*864e5),next=list.filter(e=>new Date(e.end+"T23:59:59")>=now&&new Date(e.start+"T00:00:00")<=limit);
 $("wEvents").textContent=next.length;$("wDeadlines").textContent=next.filter(e=>hours(e)>=0).length;
 const loc=next.filter(e=>e.lat!=null&&e.lon!=null).map(e=>({...e,dist:km(ATH.lat,ATH.lon,e.lat,e.lon)})).sort((a,b)=>a.dist-b.dist)[0];
 $("wNearest").textContent=loc?Math.round(loc.dist)+" km":"—";$("wNearestText").textContent=loc?`${loc.city||loc.venue} · ευθεία από Αθήνα`:"χωρίς γνωστή έδρα";
}
function render(){
 const list=events.filter(match).sort((a,b)=>a.start.localeCompare(b.start));$("count").textContent=list.length+" αποτελέσματα";deadlineHero(list);week(list);
 $("list").innerHTML=list.map(e=>{const h=hours(e),dc=h==null?"":h<0?"Έληξε":h<=24?`≤24h`:h<=72?`≤72h`:`Deadline ${new Date(e.deadline).toLocaleString("el-GR")}`;return `<article class="event"><h3>${e.title}</h3><div class="meta">${fmt(e.start)} – ${fmt(e.end)} · ${e.venue||"Έδρα προς ανακοίνωση"}${e.city?" · "+e.city:""}</div><div class="badges"><span class="badge">${e.level}</span>${cats(e).map(c=>`<span class="badge">${c}</span>`).join("")}${e.categories_status==="inferred-current-year"?'<span class="badge warn-b">Κατηγορίες προς επιβεβαίωση</span>':""}${mine(e)?'<span class="badge mine">★ Δική μου</span>':""}${dc?`<span class="badge ${h<=24&&h>=0?"urgent-b":h<=72&&h>=0?"warn-b":""}">${dc}</span>`:""}</div><div class="links">${e.source_url?`<a target="_blank" href="${e.source_url}">Πηγή</a>`:""}${e.proclamation_url?`<a target="_blank" href="${e.proclamation_url}">Προκήρυξη</a>`:""}</div></article>`}).join("")||'<div class="event">Δεν βρέθηκαν τουρνουά.</div>';
 markers.clearLayers();list.filter(e=>e.lat!=null&&e.lon!=null).forEach(e=>L.marker([e.lat,e.lon]).bindPopup(`<b>${e.title}</b><br>${e.venue||""}<br>${fmt(e.start)}–${fmt(e.end)}`).addTo(markers));
}
function bind(){
 ["level","gender","age","union","from","to","deadline","search"].forEach(id=>{let el=$(id);el.value=state[id]||"";el.oninput=()=>{state[id]=el.value;save();render()}});
 $("favoritesOnly").onchange=()=>{state.favoritesOnly=$("favoritesOnly").checked;save();render()};
 $("reset").onclick=()=>{localStorage.removeItem(KEY);location.reload()}
}
fetch(DATA,{cache:"no-store"}).then(r=>r.json()).then(d=>{events=d.tournaments||[];load();const us=[...new Set(events.flatMap(unions).filter(Boolean))].sort((a,b)=>a.localeCompare(b,"el"));$("union").innerHTML='<option value="ALL">Όλες οι Ενώσεις</option>'+us.map(u=>`<option>${u}</option>`).join("");map=L.map("map").setView([38.3,23.5],6);L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",{maxZoom:19,attribution:"&copy; OpenStreetMap"}).addTo(map);markers=L.markerClusterGroup();map.addLayer(markers);favUI();bind();render();setInterval(render,60000)});