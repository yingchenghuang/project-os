// usage: node animrun.js <outdir> <parity: even|odd|all> [query]
const {chromium}=require('playwright'); const fs=require('fs');
const out=process.argv[2], par=process.argv[3]||'even', qs=process.argv[4]||'w=1280&h=720&aa=1';
const FPS=24, N=120*FPS;
(async()=>{
 const b=await chromium.launch({args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
 const p=await b.newPage({viewport:{width:1280,height:720}}); p.on('pageerror',e=>console.log('PAGEERR',e.message));
 await p.goto('http://localhost:8765/anim.html?'+qs); await p.waitForFunction(()=>window.__ready===true,null,{timeout:600000});
 const t0=Date.now(); let done=0;
 for(let i=0;i<N;i++){
   if(par==='even'&&i%2) continue; if(par==='odd'&&!(i%2)) continue;
   const f=`${out}/frame_${String(i).padStart(5,'0')}.jpg`; if(fs.existsSync(f)) continue;
   const d=await p.evaluate(t=>window.renderFrame(t), i/FPS);
   fs.writeFileSync(f+'.tmp',Buffer.from(d.split(',')[1],'base64')); fs.renameSync(f+'.tmp',f); done++;
   if(done%24===0) console.log(`frame ${i} t=${(i/FPS).toFixed(2)} done=${done} avg=${((Date.now()-t0)/1000/done).toFixed(2)}s`);
 }
 console.log('PASS COMPLETE', par); await b.close();})();
