import json, sys
from pathlib import Path

OUT = Path("_rating_pilot_2026_v9")
items = json.loads((OUT / "items_blinded.json").read_text(encoding="utf-8"))
runs = json.loads((OUT / "runs_blinded.json").read_text(encoding="utf-8"))
RETURN_TO = "An Le at lex@upstate.edu or Chunyu Liu at LiuCh@upstate.edu"
CODES = sorted(runs)
NCORE = len(next(iter(runs.values()))["core"])
NEXT = len(next(iter(runs.values()))["ext"])

CANDIDATES = [
    ("Anhedonia", "decreased sucrose preference",
     "Persistent loss of interest or pleasure in nearly all activities.",
     "reduced preference for a sweetened solution over plain water in a two bottle choice test"),
    ("Psychomotor agitation", "increased grooming behavior",
     "Psychomotor agitation or slowing, observable by others.",
     "greater than normal time spent in self directed grooming"),
    ("Insomnia", "increased wakefulness",
     "Difficulty initiating or maintaining sleep, nearly every day.",
     "greater than normal amount of time spent awake during the normal sleep period"),
]
live_h = {i["hpo_label"].strip().lower() for i in items}
live_m = {i["mp_label"].strip().lower() for i in items}
EX = next((dict(h=h, m=m, c=c, d=d) for h, m, c, d in CANDIDATES
           if h.lower() not in live_h and m.lower() not in live_m), None)
if EX is None:
    sys.exit("every candidate worked example collides with a live item; add another candidate")
print("worked example:", EX["h"], "/", EX["m"], "(verified absent from the item set)")

HTML = r"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Human-Mouse Phenotype Matching</title><style>
:root{--ink:#000000;--sec:#000000;--surf:#fbfaf8;--line:#a8a29a;--fv:#0b4f59;--fvl:#e2eff1;
      --alert:#8a1c2d;--panel:#fff;--dim:#e6e2dc;--ok:#255627;--okl:#e5f0e5}
*{box-sizing:border-box}
body{margin:0;background:var(--surf);color:var(--ink);
     font-family:"Segoe UI",-apple-system,Roboto,Helvetica,Arial,sans-serif;
     font-size:18px;line-height:1.6}
.wrap{max-width:960px;margin:0 auto;padding:24px 20px 70px}
h1{font-size:27px;font-weight:700;margin:0 0 4px}
h2{font-size:21px;font-weight:700;margin:26px 0 8px}
.by{font-size:18px;margin-bottom:18px}
.sub{font-size:18px;margin-bottom:18px}
.fine{font-size:18px;margin:10px 0 0}
.bar{height:6px;background:var(--line);border-radius:3px;overflow:hidden;margin:14px 0 6px}
.bar i{display:block;height:100%;background:var(--fv);width:0}
.meta{display:flex;justify-content:space-between;font-size:17px;margin-bottom:14px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:16px 20px}
.lab{font-size:16px;letter-spacing:.07em;text-transform:uppercase;color:var(--fv);
     font-weight:700;margin-bottom:8px}
.lab span{color:var(--ink);font-weight:400;letter-spacing:0;text-transform:none;font-size:17px}
.crit{font-size:21px;line-height:1.5}
.cols{display:grid;grid-template-columns:1fr 1px 1fr;gap:0 20px;margin-top:16px;
      border-top:1px solid var(--line);padding-top:14px}
.rule{background:var(--line);width:1px;height:100%}
.term{font-size:20px;font-weight:700;margin-bottom:4px}
.def{font-size:18px}
.id{font-size:17px;margin-top:6px}
.q{font-size:20px;font-weight:700;margin:0 0 4px}
.qh{font-size:18px;margin-bottom:12px}
.qblock{margin-top:22px}
.qblock.off{opacity:.62}
.btns{display:flex;gap:9px;flex-wrap:wrap}
button{font-family:inherit;font-size:18px;cursor:pointer;border-radius:8px;
       border:1px solid var(--line);background:#fff;padding:11px 15px;color:var(--ink);text-align:left}
button:hover:not(:disabled){border-color:var(--fv)}
button:disabled{cursor:default;color:var(--ink);background:var(--dim);border-color:var(--line)}
button b{display:block;font-size:18px;font-weight:700}
button i{display:block;font-style:normal;font-size:17px;color:var(--ink);margin-top:3px}
button.sel{background:var(--fvl);border-color:var(--fv);box-shadow:inset 0 0 0 1px var(--fv)}
.pos b{color:var(--fv)} .neg b{color:var(--alert)}
.ex button:disabled{color:var(--ink);background:#fff}
.foot{display:flex;gap:10px;align-items:center;margin-top:26px;flex-wrap:wrap;
      border-top:1px solid var(--line);padding-top:16px}
.foot button{padding:11px 16px;font-size:18px}
.note{background:var(--fvl);border-left:5px solid var(--fv);padding:16px 18px;font-size:18px;margin:16px 0}
.note .task{margin:10px 0 0}
.warn{background:#fdf3f4;border-left:5px solid var(--alert);padding:14px 17px;font-size:18px;
      margin:16px 0;display:none}
.okbox{background:var(--okl);border-left:5px solid var(--ok);padding:17px 19px;margin:16px 0;font-size:18px}
.ex{background:var(--panel);border:1px solid var(--line);border-radius:10px;
    padding:14px 18px;margin:12px 0 4px}
.exq{font-size:18px;margin:10px 0 0}
.exq b{color:var(--ink);font-weight:700}
.exl{font-size:18px;font-weight:700;margin:18px 0 8px}
.fields{display:flex;gap:14px;flex-wrap:wrap;margin:14px 0 18px}
.fields label{font-size:17px;display:block;margin-bottom:5px;font-weight:700}
input[type=text],select{font-family:inherit;font-size:18px;padding:10px 12px;
    border:1px solid var(--line);border-radius:8px;background:#fff;color:var(--ink);min-width:200px}
kbd{background:var(--dim);border:1px solid var(--line);border-radius:4px;padding:0 6px;
    font-size:17px;font-family:inherit;font-weight:700;color:var(--ink)}
.done{text-align:center;padding:36px 0}
ul{margin:6px 0 0;padding-left:20px}
li{margin-bottom:7px}
@media(max-width:760px){.cols{grid-template-columns:1fr;gap:0}
  .rule{width:100%;height:1px;margin:14px 0}}
</style></head><body><div class="wrap">

<h1>Human-Mouse Phenotype Matching</h1>
<div class="by">An Le, Liu Lab, Dept. of Psychiatry, SUNY Upstate Medical University</div>

<div id="gate">
 <div class="note"><b>What you are being asked to do.</b> Each screen shows one DSM-5-TR diagnostic
 criterion of a disorder, one human phenotype term the criterion resolves into, and one mouse
 phenotype term taken from the Mouse Genome Informatics database.
 <div class="task"><b>Your task:</b> judge whether the mouse phenotype is credible evidence about
 what the criterion describes. Evidence may be direct or indirect, and it does not have to cover the
 whole criterion.</div></div>
 <div class="fine">Criterion wording is paraphrased from DSM-5-TR rather than quoted. Please judge
 the criterion as written on the screen. Part one is __NC__ screens (about __MC__ minutes). Part two is
 __NE__ more (about __ME__ minutes). Both parts are needed for the study to reach its target
 precision.</div>

 <h2>A worked example</h2>
 <div class="ex">
   <div class="lab">DSM-5-TR criterion (paraphrased)</div>
   <div class="crit">__EXC__</div>
   <div class="cols">
     <div><div class="lab">Human phenotype term</div><div class="term">__EXH__</div></div>
     <div class="rule"></div>
     <div><div class="lab">Mouse phenotype term</div><div class="term">__EXM__</div>
       <div class="def">__EXD__</div></div>
   </div>
   <div class="exl">1. Does this mouse phenotype belong to the criterion?</div>
   <div class="btns" id="eb1"></div>
   <div class="exq"><b>Yes.</b> A reduced preference for a reward is evidence about loss of
   pleasure, even though no mouse reports losing interest.</div>
   <div class="exl">2. How closely does the mouse term map onto the human term?</div>
   <div class="btns" id="eb2"></div>
   <div class="exq"><b>Close rather than direct.</b> The human term names a reported experience and
   the mouse term names a behavioral assay of the same process.</div>
 </div>
 <div class="fine">The highlighted buttons above are the answers we would give.
 <b>You will not be asked to explain your answers.</b> The reasoning is shown here only so the two
 questions are clear.</div>

 <h2>Please tell us who you are</h2>
 <div class="fields">
  <div><label for="code">Rater code</label>
       <select id="code"><option value="">Select</option>__CODES__</select></div>
  <div><label for="rater">Name or initials</label>
       <input type="text" id="rater" placeholder="e.g. CL"></div>
  <div><label for="role">Primary role</label>
   <select id="role">
    <option value="">Select</option>
    <option>Psychiatrist</option><option>Psychologist</option>
    <option>Neuroscientist</option><option>Geneticist or genomicist</option>
    <option>Mouse phenotyping or model organism</option>
    <option>Trainee, resident or graduate student</option><option>Other</option>
   </select></div>
  <div><label for="board">Board certified in psychiatry</label>
   <select id="board"><option value="">Select</option><option>Yes</option>
    <option>No</option><option>Not applicable</option></select></div>
  <div><label for="years">Years since terminal degree</label>
   <select id="years"><option value="">Select</option><option>In training</option>
    <option>0 to 5</option><option>6 to 15</option><option>More than 15</option></select></div>
 </div>
 <div class="fine">Your rater code is in the invitation email. It sets the order you see the items in,
 so please use the one you were sent.</div>
 <div class="warn" id="nocode">Please select the rater code from your invitation email before
 beginning.</div>

 <div class="note"><b>Three practical points.</b>
 <ul><li>You are never shown an automated answer, a score, or the mouse line the phenotype came
 from.</li>
 <li>You may stop at any point and the file you have is still usable. Screens are ordered so that whatever you finish is a balanced sample. The page remembers where you were if you close it and come back on the same computer.</li>
 <li>Nothing is transmitted anywhere. A <b>Download answers</b> button is on every screen; when you
 finish, press it and email the file to <b>__RET__</b>.</li></ul></div>

 <p><button id="begin" class="pos" onclick="start()"><b>Begin</b></button></p>
</div>

<div id="app" style="display:none">
 <div class="bar"><i id="pb"></i></div>
 <div class="meta"><span id="cnt"></span><span id="eta"></span></div>
 <div class="card">
   <div class="lab">DSM-5-TR criterion (paraphrased) <span id="dis"></span></div>
   <div class="crit" id="crit"></div>
   <div class="cols">
     <div><div class="lab">Human phenotype term</div>
       <div class="term" id="hlab"></div><div class="id" id="hid"></div></div>
     <div class="rule"></div>
     <div><div class="lab">Mouse phenotype term</div>
       <div class="term" id="mlab"></div><div class="def" id="mdef"></div>
       <div class="id" id="mid"></div></div>
   </div>
 </div>

 <div class="qblock" id="qb1">
   <div class="q">1. Does this mouse phenotype belong to the criterion?</div>
   <div class="qh">Is it evidence about what the criterion describes, directly or indirectly?</div>
   <div class="btns" id="b1"></div>
 </div>

 <div class="qblock off" id="qb2">
   <div class="q">2. How closely does the mouse term map onto the human term?</div>
   <div class="qh">This one is about the two terms beside each other, not the criterion.</div>
   <div class="btns" id="b2"></div>
 </div>

 <div class="foot">
   <button onclick="back()">Back</button>
   <button id="next" onclick="fwd()" disabled>Next</button>
   <button onclick="dl()">Download answers</button>
   <span id="saved" style="font-size:17px"></span>
 </div>
</div>

<div id="coredone" style="display:none">
 <div class="done">
  <h1>Part one complete. Thank you.</h1>
  <div class="okbox"><b>Please download your answers now</b> so that nothing is lost if you are
  interrupted. You can download again at the end.
  <p style="margin:10px 0 0"><button class="pos" onclick="dl()"><b>Download answers</b></button></p></div>
  <p class="sub">Part two is __NE__ screens (about __ME__ minutes). Every pair in the study is rated by three people, and part two completes your share. Please continue if you can. If you have
  to stop here, download and email the file; part one is still usable.</p>
  <p><button onclick="goext()"><b>Continue to part two</b></button></p>
 </div>
</div>

<div id="fin" style="display:none" class="done">
 <h1>Done. Thank you.</h1>
 <p class="sub">Please press download and email the file to __RET__.</p>
 <p><button class="pos" onclick="dl()"><b>Download answers</b></button></p>
</div>

</div><script>
const ITEMS=__DATA__, RUNS=__RUNS__;
const Q1=[["yes","Yes","Y","evidence about this criterion"],
          ["no","No","N","not evidence about this criterion"],
          ["cannot","Cannot tell","C","not enough here to judge"]];
const Q2=[["direct","Direct","1","the same observable"],
          ["close","Close","2","different measure, same construct"],
          ["weak","Too weak","3","related but too distant"],
          ["unrelated","Unrelated","4","different construct"],
          ["unsure","Unsure","5","cannot judge"]];
const c1=v=>(v=="no"?"neg":v=="yes"?"pos":"");
const c2=v=>((v=="direct"||v=="close")?"pos":(v=="weak"||v=="unrelated")?"neg":"");
const BY={}; ITEMS.forEach(x=>BY[x.pid]=x);
let phase="core", plan=[], i=0, ans={core:[],ext:[]}, rater={}, t0=Date.now(),
    tPrev=Date.now(), cur={q1:null,q2:null}, revisit=false, K="facet_rating_v9";

function store(o){try{localStorage.setItem(K,JSON.stringify(o));}catch(e){}}
function recall(){try{return JSON.parse(localStorage.getItem(K)||"null");}catch(e){return null;}}
function save(){store({rater:rater,phase:phase,i:i,ans:ans,t0:t0});
 document.getElementById("saved").textContent="saved "+new Date().toLocaleTimeString();}

function face(s,cls){const b=document.createElement("button");
 b.className=cls; b.dataset.v=s[0];
 b.innerHTML="<b>"+s[1]+" <kbd>"+s[2]+"</kbd></b><i>"+s[3]+"</i>"; return b;}
function mkbtn(box,spec,cls,fn){
 const d=document.getElementById(box); d.innerHTML="";
 spec.forEach(s=>{const b=face(s,cls(s[0])); b.onclick=()=>fn(s[0]); d.appendChild(b);});}
function example(box,spec,base,sel){
 const d=document.getElementById(box); d.innerHTML="";
 spec.forEach(s=>{const b=face(s,base(s[0])+(s[0]==sel?" sel":"")); b.disabled=true;
  d.appendChild(b);});}

function paint(){
 mkbtn("b1",Q1,v=>c1(v)+(cur.q1==v?" sel":""),pick1);
 mkbtn("b2",Q2,v=>c2(v)+(cur.q2==v?" sel":""),pick2);
 const locked=!cur.q1;
 document.getElementById("qb2").className="qblock"+(locked?" off":"");
 [...document.getElementById("b2").children].forEach(b=>b.disabled=locked);
 document.getElementById("next").disabled=!(cur.q1&&cur.q2);}
function pick1(v){cur.q1=v; paint();}
function pick2(v){if(!cur.q1)return; cur.q2=v; paint(); if(!revisit) fwd();}

function record(){if(i<plan.length&&cur.q1&&cur.q2)
 ans[phase][i]={phase:phase,screen:i+1,pid:plan[i],q1:cur.q1,q2:cur.q2,ms:Date.now()-tPrev};}
function fwd(){if(!(cur.q1&&cur.q2))return; record(); i++; save(); draw();}
function back(){if(i>0){record(); i--; save(); draw();}}

function endphase(){
 document.getElementById("app").style.display="none";
 if(phase=="core"){document.getElementById("coredone").style.display="block";}
 else{document.getElementById("fin").style.display="block";}
 save();}

function goext(){
 phase="ext"; plan=RUNS[rater.code].ext; i=0;
 document.getElementById("coredone").style.display="none";
 document.getElementById("app").style.display="block"; draw();}

function draw(){
 if(i>=plan.length){endphase(); return;}
 const it=BY[plan[i]], prev=ans[phase][i];
 cur={q1:prev?prev.q1:null,q2:prev?prev.q2:null}; revisit=!!prev;
 document.getElementById("dis").textContent=it.disorder?("  |  "+it.disorder):"";
 document.getElementById("crit").textContent=it.criterion;
 document.getElementById("hlab").textContent=it.hpo_label;
 document.getElementById("hid").textContent=it.hpo_id;
 document.getElementById("mlab").textContent=it.mp_label;
 document.getElementById("mdef").textContent=it.mp_def;
 document.getElementById("mid").textContent=it.mp_id;
 document.getElementById("pb").style.width=Math.round(100*i/plan.length)+"%";
 const tag=(phase=="core"?"Screen ":"Extension ");
 document.getElementById("cnt").textContent=tag+(i+1)+" of "+plan.length;
 const done=ans[phase].filter(Boolean).length;
 if(done>=3){const per=(Date.now()-t0)/((ans.core.filter(Boolean).length)+(ans.ext.filter(Boolean).length))/1000;
  document.getElementById("eta").textContent="about "+
   Math.max(1,Math.round(per*(plan.length-i)/60))+" min left";}
 paint(); tPrev=Date.now();}

function start(){
 const code=document.getElementById("code").value;
 if(!code||!RUNS[code]){document.getElementById("nocode").style.display="block"; return;}
 rater={code:code,
        id:document.getElementById("rater").value.trim()||"anonymous",
        role:document.getElementById("role").value,
        board:document.getElementById("board").value,
        years:document.getElementById("years").value};
 phase="core"; plan=RUNS[code].core; i=0; ans={core:[],ext:[]}; K="facet_rating_v9_"+code;
 const d=recall();
 if(d&&d.ans&&((d.ans.core||[]).filter(Boolean).length||(d.ans.ext||[]).filter(Boolean).length)&&
    confirm("Resume your previous session on this computer?")){
   rater=d.rater; phase=d.phase; i=d.i; ans=d.ans; t0=d.t0;
   plan=RUNS[rater.code][phase];}
 document.getElementById("gate").style.display="none";
 document.getElementById("app").style.display="block"; draw();}

function dl(){record();
 const core=ans.core.filter(Boolean), ext=ans.ext.filter(Boolean);
 const out={instrument:"facet_rating_v9_k3", build:"v9_k3_168pairs_n12_judged", return_to:"__RET__",
  rater:rater, core_order:RUNS[rater.code].core, ext_order:RUNS[rater.code].ext,
  q1_scale:"yes|no|cannot", q2_scale:"direct|close|weak|unrelated|unsure",
  started:new Date(t0).toISOString(), finished:new Date().toISOString(),
  n_core:RUNS[rater.code].core.length, n_core_answered:core.length,
  n_ext:RUNS[rater.code].ext.length, n_ext_answered:ext.length,
  answers:core.concat(ext)};
 const b=new Blob([JSON.stringify(out,null,1)],{type:"application/json"});
 const a=document.createElement("a");a.href=URL.createObjectURL(b);
 a.download="facet_rating_"+(rater.code||"X")+"_"+
   ((rater.id||"anon").replace(/[^A-Za-z0-9]/g,"_"))+".json";a.click();}

document.addEventListener("keydown",e=>{
 if(document.getElementById("app").style.display=="none")return;
 if(e.target.tagName=="INPUT"||e.target.tagName=="SELECT")return;
 const k=(e.key||"").toLowerCase();
 if(!cur.q1){const m={"y":"yes","n":"no","c":"cannot"};
   if(m[k]){pick1(m[k]); e.preventDefault();} return;}
 const m={"1":"direct","2":"close","3":"weak","4":"unrelated","5":"unsure"};
 if(m[e.key]){pick2(m[e.key]); e.preventDefault();}});

example("eb1",Q1,c1,"yes"); example("eb2",Q2,c2,"close");
</script></body></html>"""

opts = "".join(f"<option>{c}</option>" for c in CODES)
HTML = (HTML.replace("__DATA__", json.dumps(items))
            .replace("__RUNS__", json.dumps(runs))
            .replace("__CODES__", opts)
            .replace("__NC__", str(NCORE)).replace("__NE__", str(NEXT)).replace("__MC__", str(round(NCORE * 40 / 60))).replace("__ME__", str(round(NEXT * 40 / 60)))
            .replace("__RET__", RETURN_TO)
            .replace("__EXC__", EX["c"]).replace("__EXH__", EX["h"])
            .replace("__EXM__", EX["m"]).replace("__EXD__", EX["d"]))

bad = sorted({c for c in HTML if ord(c) > 127})
if bad:
    sys.exit("non-ascii characters in output: " + repr(bad))
if [c for c in HTML if c in "‐‑‒–—―−"]:
    sys.exit("dash-family characters in output")

(OUT / "rate.html").write_text(HTML, encoding="utf-8")
print("wrote", OUT / "rate.html", len(HTML), "bytes,", len(items), "items,",
      len(CODES), "codes, core", NCORE, "ext", NEXT)
