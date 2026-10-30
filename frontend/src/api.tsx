// API 호출 한 곳. 경로는 같은 출처(/api) — 배포 때는 FastAPI 가, 개발 때는 vite 프록시가 받는다.
export async function api<T = any>(path: string, opts: { method?: string; body?: unknown; form?: FormData } = {}): Promise<T> {
  const init: RequestInit = { method: opts.method || (opts.body || opts.form ? 'POST' : 'GET') }
  if (opts.form) init.body = opts.form
  else if (opts.body !== undefined) {
    init.body = JSON.stringify(opts.body)
    init.headers = { 'Content-Type': 'application/json' }
  }
  const r = await fetch(path, init)
  const text = await r.text()
  let data: any = text
  try { data = JSON.parse(text) } catch { /* 텍스트 응답 */ }
  if (!r.ok) throw new Error(typeof data === 'object' && data?.detail ? String(data.detail) : `HTTP ${r.status}`)
  return data as T
}

export const STATUS_KO: Record<string, string> = {
  observed: '현재 상태(측정)', ready: '실행 가능', running: '실행 중', succeeded: '검증 완료', needs_info: '정보 필요',
  needs_review: '검토 필요', unsupported: '현재 환경에서 지원 안 됨', blocked: '현재 환경에서 지원 안 됨', failed: '실패',
  projected: '아직 실행하지 않은 계획', done: '목표 도달(계획)', skipped: '건너뜀',
}
export const CONTROL_KO: Record<string, string> = { needs_info: '정보 필요', unsupported: '지원 안 됨', done: '완료(목표 도달)' }
export const GATE_KO: Record<string, string> = {
  input_contract_matches: '입력 계약 일치', required_parameters_resolved: '필요한 인자 있음', preconditions_pass: '사전조건 통과',
  handler_implemented: '실행기 구현됨', runtime_capabilities_available: '실행 환경 지원', requested_operation_allowed: '허용된 작업',
}
// 판단 공급자 표시명 한 곳. 요청 값 live 는 typesafe 로 저장되므로 둘 다 둔다(codex · openai 는 요청 = 저장).
export const PROVIDER_NAME: Record<string, string> = { codex: 'OpenAI Codex', openai: 'OpenAI Decisions API', live: 'TypeSafe Jev', typesafe: 'TypeSafe Jev' }
export const IMPL_KO: Record<string, string> = { implemented: '실행기 있음', planned: '계획 카드(실행기 없음)', spec_only: '명세 있음 · 실행기 미구현' }

export function Badge({ s }: { s: string }) {
  return <span className={`badge st-${s}`}>{STATUS_KO[s] || s}</span>
}

export function fmtP(p: number | null | undefined) {
  return p === null || p === undefined ? '—' : p.toFixed(3)
}

export function navigate(to: string) {
  history.pushState(null, '', to)
  window.dispatchEvent(new PopStateEvent('popstate'))
}

export function Link({ to, children, className }: { to: string; children: React.ReactNode; className?: string }) {
  return <a href={to} className={className} onClick={(e) => { if (e.ctrlKey || e.metaKey) return; e.preventDefault(); navigate(to) }}>{children}</a>
}
