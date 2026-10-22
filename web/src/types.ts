export type Mode = 'normal' | 'rapido' | 'automatico';
export type EventType = 'run_started' | 'hop_started' | 'hop_completed' | 'tool_started' | 'tool_completed' | 'run_completed' | 'run_failed';
export interface Tool { name: string; tool_call_id: string; arguments: string; result: unknown; latency_s: number; error: string | null; }
export interface Hop { hop: number; prompt_tokens: number | null; completion_tokens: number | null; inference_latency_s: number; finish_reason: string; tools: Tool[]; }
export interface Trace { run_id: string; user_query: string; mode: Mode; success: boolean; error: string; final_answer: string; total_latency_s: number; total_prompt_tokens: number | null; total_completion_tokens: number | null; tokens_per_second: number | null; total_hops: number; inference_latency_s: number; tool_latency_s: number; hops: Hop[]; }
export interface RunEvent { type: EventType; run_id: string; seq: number; elapsed_s: number; hop?: number; name?: string; arguments?: string; result?: unknown; error?: string; trace?: Trace; prompt_tokens?: number; completion_tokens?: number; inference_latency_s?: number; finish_reason?: string; latency_s?: number; tool_call_id?: string; }
export interface Status { connected: boolean; model_available: boolean; configured_device: string; model: string; busy: boolean; error: string | null; }
export interface Mcp { servers: {id: string; connected: boolean; tools: string[]}[]; tools: {function: {name: string; description: string}}[]; }
export interface BenchRow extends Trace { case: string; repeat: number; correct: boolean; }
export interface Bench { id: string; done: boolean; total: number; rows: BenchRow[]; active_run_id?: string; error?: string; summary: {case: string; mode: Mode; n: number; p50: number; p95: number; correct: number; warning: string | null}[]; }
