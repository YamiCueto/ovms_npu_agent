import { Component, OnDestroy, OnInit, signal, computed } from '@angular/core';
import { bootstrapApplication } from '@angular/platform-browser';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Bench, EventType, Mcp, Mode, RunEvent, Status, Trace } from './types';

const eventTypes: EventType[] = ['run_started','hop_started','hop_completed','tool_started','tool_completed','run_completed','run_failed'];

@Component({selector:'app-root', standalone:true, imports:[CommonModule,FormsModule], templateUrl:'./app.html'})
class App implements OnInit, OnDestroy {
  Math = Math;
  page = signal('Dashboard'); pages = ['Dashboard','Chat','Inspector','MCP','Benchmark'];
  status = signal<Status | null>(null); traces = signal<Trace[]>([]); events = signal<RunEvent[]>([]);
  selected = signal<Trace | null>(null); mcp = signal<Mcp>({servers:[],tools:[]});
  bench = signal<Bench | null>(null); error = signal(''); processing = signal(false); elapsed = signal(0);
  messages = signal<{role:string;content:string;error?:boolean}[]>([]);
  text = ''; mode: Mode = 'normal'; repetitions = 3; session = ''; activeRun = ''; started = 0;
  source?: EventSource; timer?: ReturnType<typeof setInterval>; polling = false;
  latest = computed(() => this.traces().at(-1)); successes = computed(() => this.traces().filter(t=>t.success).length);
  maxLatency = computed(() => Math.max(1,...this.traces().map(t=>t.total_latency_s)));
  busy = computed(() => this.processing() || !!this.status()?.busy || (!!this.bench() && !this.bench()!.done));
  async api<T>(path:string, method='GET', body?:unknown):Promise<T> {
    const response = await fetch('/api'+path,{method, headers: method === 'POST' ? {'Content-Type':'application/json'} : {},body: body === undefined ? undefined : JSON.stringify(body)});
    if(!response.ok){ const data=await response.json().catch(()=>({detail:response.statusText})); throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)); }
    return response.json();
  }
  async ngOnInit(){
    try {
      this.session = sessionStorage.getItem('npu-session') || '';
      if(this.session){
        try { const h=await this.api<{messages:{role:string;content:string}[]}>('/sessions/'+this.session); this.messages.set(h.messages.filter(m=>['user','assistant'].includes(m.role)).map(m=>({...m,content:m.content.replace(/^\/no_think\n/,'')}))); }
        catch { this.session=''; }
      }
      if(!this.session) await this.newSession();
      await this.refresh(); await this.refreshMcp();
      this.activeRun=sessionStorage.getItem('npu-run') || '';
      if(this.activeRun){
        try {const run=await this.api<{done:boolean;query:string;events:RunEvent[];trace:Trace}>('/runs/'+this.activeRun);
          this.events.set(run.events);
          if(run.done){this.selected.set(run.trace);sessionStorage.removeItem('npu-run');if(!run.trace.success)this.messages.update(m=>[...m,{role:'assistant',content:run.trace.final_answer||run.trace.error,error:true}]);}
          else {this.messages.update(m=>[...m,{role:'user',content:run.query}]);this.processing.set(true);this.started=Date.now()-(run.events.at(-1)?.elapsed_s||0)*1000;this.watch(this.activeRun);}
        }catch{sessionStorage.removeItem('npu-run');}
      }
      const jid=sessionStorage.getItem('npu-benchmark');if(jid){try{this.bench.set(await this.api<Bench>('/benchmarks/'+jid));}catch{sessionStorage.removeItem('npu-benchmark');}}
    }catch(e){this.fail(e);}
    this.timer=setInterval(()=>{if(this.processing())this.elapsed.set((Date.now()-this.started)/1000);void this.poll();},1000);
  }
  ngOnDestroy(){clearInterval(this.timer);this.source?.close();}
  fail(e:unknown){this.error.set(e instanceof Error?e.message:String(e));}
  async newSession(){this.session=(await this.api<{session_id:string}>('/sessions','POST',{})).session_id;sessionStorage.setItem('npu-session',this.session);}
  async refresh(){const [status,traces]=await Promise.all([this.api<Status>('/status'),this.api<Trace[]>('/runs')]);this.status.set(status);this.traces.set(traces);}
  async poll(){if(this.polling)return;this.polling=true;try{await this.refresh();const b=this.bench();if(b&&!b.done)this.bench.set(await this.api<Bench>('/benchmarks/'+b.id));}catch(e){this.status.set(null);this.fail(e);}finally{this.polling=false;}}
  onPromptKeydown(event: KeyboardEvent){
    if(event.key !== 'Enter' || event.shiftKey || event.ctrlKey || event.altKey || event.metaKey || event.isComposing)return;
    event.preventDefault();
    if(!event.repeat)void this.send();
  }
  async send(){if(!this.text.trim()||this.busy())return;this.error.set('');const text=this.text;this.processing.set(true);this.started=Date.now();this.elapsed.set(0);
    try{const run=await this.api<{run_id:string}>('/runs','POST',{session_id:this.session,text,mode:this.mode});this.text='';this.messages.update(m=>[...m,{role:'user',content:text}]);this.events.set([]);this.activeRun=run.run_id;sessionStorage.setItem('npu-run',run.run_id);this.watch(run.run_id);}
    catch(e){this.processing.set(false);this.fail(e);}
  }
  watch(id:string){this.source?.close();this.source=new EventSource('/api/runs/'+id+'/events');
    for(const type of eventTypes)this.source.addEventListener(type,(raw)=>{
      const event=JSON.parse((raw as MessageEvent).data) as RunEvent;
      if(!this.events().some(e=>e.run_id===event.run_id&&e.seq===event.seq))this.events.update(e=>[...e,event]);
      if(event.trace){this.selected.set(event.trace);this.processing.set(false);this.source?.close();sessionStorage.removeItem('npu-run');
        this.messages.update(m=>[...m,{role:'assistant',content:event.trace!.final_answer || event.trace!.error,error:!event.trace!.success}]);
        if(!event.trace.success)this.error.set(event.trace.error);void this.refresh();}
    });
    this.source.onerror=()=>{this.error.set('Conexion SSE interrumpida; intentando reconectar.');void this.recover(id);};
  }
  async recover(id:string){try{const run=await this.api<{done:boolean;trace:Trace;events:RunEvent[]}>('/runs/'+id);if(run.done){this.source?.close();this.events.set(run.events);this.selected.set(run.trace);this.processing.set(false);sessionStorage.removeItem('npu-run');this.messages.update(m=>[...m,{role:'assistant',content:run.trace.final_answer||run.trace.error,error:!run.trace.success}]);}}catch(e){this.source?.close();this.processing.set(false);sessionStorage.removeItem('npu-run');this.fail(e);}}
  async reset(){if(this.busy())return;try{await this.api('/sessions/'+this.session,'DELETE');await this.newSession();this.messages.set([]);this.events.set([]);this.selected.set(null);this.error.set('');}catch(e){this.fail(e);}}
  async inspect(trace:Trace){this.selected.set(trace);this.page.set('Inspector');try{const run=await this.api<{events:RunEvent[]}>('/runs/'+trace.run_id);this.events.set(run.events);}catch(e){this.fail(e);}}
  async refreshMcp(){this.mcp.set(await this.api<Mcp>('/mcp'));}
  async toggleMcp(id:string,connected:boolean){try{await this.api('/mcp/'+id+(connected?'':'/connect'),connected?'DELETE':'POST',connected?undefined:{});await this.refreshMcp();}catch(e){this.fail(e);}}
  async benchmark(){if(this.busy())return;try{this.error.set('');const j=await this.api<{id:string}>('/benchmarks','POST',{repetitions:this.repetitions});sessionStorage.setItem('npu-benchmark',j.id);this.bench.set(await this.api<Bench>('/benchmarks/'+j.id));}catch(e){this.fail(e);}}
  fmt(value:number|null|undefined,digits=2){return value == null?'—':value.toLocaleString('es',{maximumFractionDigits:digits});}
}
bootstrapApplication(App).catch(console.error);
