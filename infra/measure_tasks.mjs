/** Real local HTTP -> second browser WebSocket measurements, without provider calls.
 * Start the app, then node infra/measure_tasks.mjs [http://localhost:3000].
 * Seeds a separate synthetic workspace through the backend seed command.
 */
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { execFileSync } from 'node:child_process';
import { randomUUID, randomBytes } from 'node:crypto';
import { performance } from 'node:perf_hooks';
const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(resolve(root, 'frontend/package.json'));
const { chromium } = require('playwright');
const origin = process.argv[2] ?? 'http://localhost:3000';
const browser = await chromium.launch({executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE, headless: true});
const a = await browser.newContext({baseURL: origin, viewport:{width:1440,height:900}}), b = await browser.newContext({baseURL:origin});
async function write(context, path, data, method='POST') {
  const csrf=await context.request.get('/api/auth/csrf');
  const response=await context.request.fetch('/api'+path,{method,data,headers:{'X-CSRF-Token':(await csrf.json()).csrf_token}});
  if(!response.ok()) throw new Error(`Measurement request failed: ${method} ${response.status()}`);
  return response.status()===204?null:response.json();
}
async function account(context,name) {
  const email=`task-measure-${randomUUID()}@example.com`;
  await write(context,'/auth/register',{name,email,password:randomBytes(24).toString('base64url')});
  return email;
}
const percentile=(values,p)=>Math.round([...values].sort((a,b)=>a-b)[Math.max(0,Math.ceil(values.length*p)-1)]*100)/100;
try {
  const email=await account(a,'Performance A'), viewerEmail=await account(b,'Performance B');
  const python=resolve(root,'backend/.venv',process.platform==='win32'?'Scripts/python.exe':'bin/python');
  const seeded=JSON.parse(execFileSync(python,['-m','app.tasks.seed','--owner-email',email],{cwd:resolve(root,'backend'),encoding:'utf8',timeout:120000}));
  const base=`/workspaces/${seeded.workspace_id}`;
  const invite=await write(a,base+'/invitations',{email:viewerEmail,role:'viewer'});
  await write(b,`/invitations/${new URL(invite.invite_url).searchParams.get('token')}/accept`,{});
  const loads=[];
  for(let n=0;n<20;n++) {const started=performance.now();const response=await a.request.get(`/api${base}/tasks?project_id=${seeded.project_id}&limit=1000`);if(!response.ok()||(await response.json()).tasks.length!==1000)throw new Error('Incomplete board snapshot');loads.push(performance.now()-started);}
  const page=await a.newPage(); const started=performance.now();
  await page.goto(`/tasks?project=${seeded.project_id}`);
  await page.waitForFunction(()=>document.querySelectorAll('.task-card').length===120);
  await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
  const paint=performance.now()-started;
  const snapshot=await (await a.request.get(`/api${base}/tasks?project_id=${seeded.project_id}&limit=1000`)).json();
  const task=snapshot.tasks[0];
  const receiver=await b.newPage();
  const arrivals=[];
  await receiver.exposeFunction('taskMeasurementEvent',(event)=>{if(event.type==='task.updated'&&event.data.task.id===task.id)arrivals.push({version:event.data.task.version,at:performance.now()});});
  await receiver.goto('/');
  await receiver.evaluate(({wid,seq})=>new Promise((resolve,reject)=>{
    const socket=new WebSocket(`${location.protocol==='https:'?'wss':'ws'}://${location.host}/api/ws`);
    window.taskMeasurementSocket=socket;
    socket.onopen=()=>{socket.send(JSON.stringify({type:'subscribe',workspace_id:wid,workspace_seq:seq}));resolve();};
    socket.onmessage=e=>window.taskMeasurementEvent(JSON.parse(e.data)); socket.onerror=reject;
  }),{wid:seeded.workspace_id,seq:snapshot.last_seq});
  const deliveries=[];let current=task;
  for(let n=0;n<30;n++) {
    const before=performance.now();current=await write(a,base+`/tasks/${task.id}`,{version:current.version,title:`Synthetic delivery ${n}`},'PATCH');
    const deadline=performance.now()+10000;
    while(!arrivals.some(item=>item.version===current.version)) {if(performance.now()>deadline)throw new Error('Event delivery timed out');await new Promise(resolve=>setTimeout(resolve,5));}
    deliveries.push(arrivals.find(item=>item.version===current.version).at-before);
  }
  console.log(JSON.stringify({origin,task_count:1000,rendered_cards:120,http_samples:loads.length,http_p50_ms:percentile(loads,.5),http_p95_ms:percentile(loads,.95),cold_board_navigation_to_paint_ms:Math.round(paint*100)/100,board_target_met:paint<1000,delivery_samples:deliveries.length,delivery_p50_ms:percentile(deliveries,.5),delivery_p95_ms:percentile(deliveries,.95),delivery_max_ms:Math.round(Math.max(...deliveries)*100)/100,workspace_id:seeded.workspace_id,project_id:seeded.project_id},null,2));
} finally { for(const context of [a,b]) {try{await write(context,'/auth/logout',{});}catch{}await context.close();}await browser.close(); }
