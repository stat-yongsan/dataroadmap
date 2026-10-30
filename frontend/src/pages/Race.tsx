// 결정 속도 비교(/race/:planId, D20) — 같은 판단 질문 한 벌을 Opus 5.5(왼쪽)와 Jev(오른쪽)에 동시에 보낸다.
// 기록되는 시간은 서버가 잰 값이다(요청 보내기 직전 → 첫 응답 → 결정 완료). 화면 스톱워치는 보여 주기용이다.
// 결과는 race_runs 에만 남고 계획 · 경로에는 쓰지 않는다.
import { useEffect, useRef, useState } from 'react'
import { api, Link, fmtP } from '../api'

type Lane = {
  state: 'idle' | 'running' | 'done'
  t0: number; tEnd?: number
  thinkingMs?: number | null; firstMs?: number | null; doneMs?: number | null
  text: string
  status?: string; error?: string | null; check?: string | null; checkError?: string | null
  model?: string | null; answer?: any; usage?: any
}
type Round = { i: number; opus: Lane; jev: Lane }

const idle = (): Lane => ({ state: 'idle', t0: 0, text: '' })
const median = (xs: number[]) => {
  const s = xs.filter((x) => Number.isFinite(x)).sort((a, b) => a - b)
  if (!s.length) return null
  const m = Math.floor(s.length / 2)
  return s.length % 2 ? s[m] : Math.round((s[m - 1] + s[m]) / 2)
}
const ms = (x?: number | null) => (x === null || x === undefined ? '—' : `${x.toLocaleString()} ms`)

function Decision({ lane }: { lane: Lane }) {
  const ns = lane.answer?.next_step
  if (!ns?.probabilities) return null
  const top = Object.entries(ns.probabilities as Record<string, number>).sort((a, b) => b[1] - a[1]).slice(0, 3)
  return (
    <div className="small">
      <div>다음 작업 선택: <b>{ns.choice}</b></div>
      <table style={{ marginTop: '.3rem' }}><tbody>{top.map(([o, p]) => (
        <tr key={o}><td>{o}</td><td style={{ width: '50%' }}><div className="bar" style={{ width: `${Math.max(p * 100, 1)}%` }} /></td><td>{fmtP(p)}</td></tr>
      ))}</tbody></table>
    </div>
  )
}

function LaneCard({ side, title, sub, lane, now, jev }: { side: string; title: string; sub: string; lane: Lane; now: number; jev?: boolean }) {
  const elapsed = lane.state === 'idle' ? 0 : ((lane.tEnd ?? now) - lane.t0) / 1000
  const preRef = useRef<HTMLPreElement>(null)
  useEffect(() => { if (preRef.current) preRef.current.scrollTop = preRef.current.scrollHeight }, [lane.text])
  return (
    <section className="card race-lane" aria-label={title}>
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <div><span className="dim small">{side}</span> <b style={{ fontSize: '1.1rem' }}>{title}</b><div className="dim small">{sub}</div></div>
        {lane.state === 'running' && <span className="badge st-running">결정 중</span>}
        {lane.state === 'done' && (lane.status === 'ok' ? <span className="badge st-succeeded">결정 완료</span> : <span className="badge st-failed">실패</span>)}
      </div>
      <div className="race-clock" aria-live="off">{elapsed.toFixed(3)}<span className="small dim"> 초</span></div>
      <table className="small"><tbody>
        {!jev && <tr><th>생각 시작</th><td>{ms(lane.thinkingMs)}</td></tr>}
        <tr><th>첫 응답</th><td>{jev ? (lane.doneMs != null ? `${ms(lane.doneMs)} (한 번에 옴 = 완료)` : '—') : ms(lane.firstMs)}</td></tr>
        <tr><th>결정 완료</th><td><b>{ms(lane.doneMs)}</b></td></tr>
        {lane.model && <tr><th>답한 모델</th><td>{lane.model}</td></tr>}
        {lane.check && <tr><th>형식 검사</th><td className={lane.check === '통과' ? 'ok' : 'err'}>{lane.check}{lane.checkError ? ` — ${lane.checkError}` : ''}</td></tr>}
      </tbody></table>
      {lane.error && <p className="err small">{lane.error}</p>}
      <Decision lane={lane} />
      {!jev && (lane.text || lane.state === 'running') && (
        <details open style={{ marginTop: '.4rem' }}><summary>Opus 가 쓰는 답(실시간)</summary>
          <pre ref={preRef} className="race-stream">{lane.text || (lane.thinkingMs != null ? '(생각 중 — 답 글자는 생각이 끝나야 나옵니다)' : '(연결 중)')}</pre>
        </details>
      )}
    </section>
  )
}

export default function Race({ planId }: { planId: string }) {
  const [info, setInfo] = useState<any>(null)
  const [err, setErr] = useState('')
  const [effort, setEffort] = useState('low')
  const [agree, setAgree] = useState(false)
  const [busy, setBusy] = useState(false)
  const [opus, setOpus] = useState<Lane>(idle())
  const [jev, setJev] = useState<Lane>(idle())
  const [rounds, setRounds] = useState<Round[]>([])
  const [now, setNow] = useState(performance.now())

  const load = () => api(`/api/race/${planId}`).then(setInfo).catch((e) => setErr(e.message))
  useEffect(() => { load() }, [planId]) // eslint-disable-line

  useEffect(() => { // 스톱워치 — 달리는 동안만 화면을 다시 그린다
    if (!busy) return
    let id = 0
    const tick = () => { setNow(performance.now()); id = requestAnimationFrame(tick) }
    id = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(id)
  }, [busy])

  async function runJev(batch: string, t0: number): Promise<Lane> {
    let lane: Lane = { ...idle(), state: 'running', t0 }
    setJev(lane)
    try {
      const r = await api(`/api/race/${planId}/jev`, { body: { batch_id: batch } })
      lane = { ...lane, state: 'done', tEnd: performance.now(), doneMs: r.done_ms, status: r.status, error: r.error, check: r.check_status, checkError: r.check_error, model: r.model_returned, answer: r.answer, usage: r.usage }
    } catch (e: any) {
      lane = { ...lane, state: 'done', tEnd: performance.now(), status: 'failed', error: e.message }
    }
    setJev(lane)
    return lane
  }

  async function runOpus(batch: string, t0: number): Promise<Lane> {
    let lane: Lane = { ...idle(), state: 'running', t0 }
    setOpus(lane)
    try {
      const r = await fetch(`/api/race/${planId}/opus`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ batch_id: batch, effort }) })
      if (!r.ok || !r.body) {
        const t = await r.text()
        let msg = `HTTP ${r.status}`
        try { msg = JSON.parse(t).detail || msg } catch { /* 텍스트 */ }
        throw new Error(msg)
      }
      const reader = r.body.getReader()
      const dec = new TextDecoder()
      let buf = ''
      for (;;) {
        const { value, done } = await reader.read()
        if (done) break
        buf += dec.decode(value, { stream: true })
        let nl
        while ((nl = buf.indexOf('\n')) >= 0) {
          const line = buf.slice(0, nl); buf = buf.slice(nl + 1)
          if (!line.trim()) continue
          const ev = JSON.parse(line)
          if (ev.t === 'thinking') lane = { ...lane, thinkingMs: ev.ms }
          else if (ev.t === 'first') lane = { ...lane, firstMs: ev.ms }
          else if (ev.t === 'delta') lane = { ...lane, text: lane.text + ev.text }
          else if (ev.t === 'done') lane = { ...lane, state: 'done', tEnd: performance.now(), doneMs: ev.ms, firstMs: ev.first_ms, thinkingMs: ev.thinking_ms, status: ev.status, error: ev.error, check: ev.check_status, checkError: ev.check_error, model: ev.model_returned, answer: ev.answer, usage: ev.usage }
          setOpus(lane)
        }
      }
      if (lane.state !== 'done') lane = { ...lane, state: 'done', tEnd: performance.now(), status: 'failed', error: '응답이 중간에 끊겼습니다' }
    } catch (e: any) {
      lane = { ...lane, state: 'done', tEnd: performance.now(), status: 'failed', error: e.message }
    }
    setOpus(lane)
    return lane
  }

  async function race(n: number) {
    setBusy(true); setErr(''); setRounds([])
    const batch = crypto.randomUUID()
    const done: Round[] = []
    try {
      for (let i = 1; i <= n; i++) {
        const t0 = performance.now()   // 두 쪽이 같은 순간에 출발
        const [o, j] = await Promise.all([runOpus(batch, t0), runJev(batch, t0)])
        done.push({ i, opus: o, jev: j })
        setRounds([...done])
      }
    } finally {
      setBusy(false)
      load()
    }
  }

  if (err && !info) return <p className="err">{err}</p>
  if (!info) return <p>불러오는 중…</p>
  const ready = info.keys.jev && info.keys.opus
  const last = rounds[rounds.length - 1]
  const lead = last && last.opus.status === 'ok' && last.jev.status === 'ok' && last.opus.doneMs != null && last.jev.doneMs != null
    ? (last.jev.doneMs <= last.opus.doneMs
      ? `Jev 가 ${(last.opus.doneMs - last.jev.doneMs).toLocaleString()} ms 먼저 결정 (Opus 의 ${(last.opus.doneMs / Math.max(last.jev.doneMs, 1)).toFixed(1)}배 빠름)`
      : `Opus 가 ${(last.jev.doneMs - last.opus.doneMs).toLocaleString()} ms 먼저 결정`)
    : null
  const med = (f: (r: Round) => number | null | undefined) => median(rounds.filter((r) => r.opus.status === 'ok' && r.jev.status === 'ok').map((r) => f(r) as number))
  const nq = Object.keys(info.questions).length

  return (
    <>
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <h1 style={{ marginBottom: 0 }}>결정 속도 비교 — Opus 5.5 vs Jev</h1>
        <Link to={`/roadmaps/${planId}`}>← 로드맵으로</Link>
      </div>
      <p className="dim small">이 계획을 만들 때의 상태(루트)에서 앱이 실제로 묻는 판단 질문 {nq}개(다음 작업 고르기 · 영역별 필요성 · 기여도 점수)를 두 모델에 똑같이 보냅니다. 정답을 가리는 비교가 아니라 <b>결정까지 걸리는 시간</b> 비교입니다. 결과는 계획 · 경로에 쓰지 않습니다.</p>

      <section className="card small">
        <div className="row">
          <label>Opus 생각 깊이(effort) <select value={effort} onChange={(e) => setEffort(e.target.value)} disabled={busy}>
            {info.efforts.map((x: string) => <option key={x} value={x}>{x}{x === 'low' ? ' (가장 빠름)' : x === 'medium' ? ' (Opus 5.5 기본값)' : ''}</option>)}
          </select></label>
          <span className="dim">Opus 5.5 는 생각(thinking)을 끌 수 없어 effort 로만 속도를 조절합니다 · fast 모드 끔</span>
        </div>
        {!info.keys.opus && <p className="err">ANTHROPIC_API_KEY 가 없습니다 — D:\devOps\.env 에 넣고 앱을 다시 켜세요(Opus 쪽 꺼짐)</p>}
        {!info.keys.jev && <p className="err">TYPESAFE_API_KEY 가 없습니다 — Jev 쪽 꺼짐</p>}
        <p style={{ margin: '.5rem 0' }}>누르면 이 표의 <b>측정 요약</b>(열 이름 · 자료형 · 건수 · 업무 규칙)과 <b>후보 작업 목록</b>을 <b>Anthropic(Opus)</b>과 <b>TypeSafe(Jev)</b> 두 곳으로 보냅니다. 예시 행은 보내지 않습니다(가상자료만 쓰기로 함 · D12). 1회 = 쪽마다 호출 1번, 5회 반복 = 쪽마다 5번(한 번에 최대 {info.max_per_batch}번).</p>
        <details><summary>보낼 필드(두 쪽 같음)</summary><pre>{JSON.stringify(info.payload, null, 1)}</pre></details>
        <div className="row" style={{ marginTop: '.5rem' }}>
          <label><input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)} /> 두 곳으로 보내는 데 동의합니다</label>
          <button className="primary" disabled={!agree || busy || !ready} onClick={() => race(1)}>{busy ? '결정 중…' : '1회 비교 시작'}</button>
          <button disabled={!agree || busy || !ready} onClick={() => race(info.max_per_batch)}>{info.max_per_batch}회 반복(중앙값)</button>
        </div>
      </section>

      {lead && <p className="race-lead">{lead}</p>}
      <div className="race-grid">
        <LaneCard side="왼쪽" title="Opus 5.5" sub={`${info.opus_model} · effort ${effort} · 일반 LLM(글로 답을 씀)`} lane={opus} now={now} />
        <LaneCard side="오른쪽" title="Jev" sub={`TypeSafe · ${info.jev_model} · 판단 전용 모델(분포를 바로 줌)`} lane={jev} now={now} jev />
      </div>

      {rounds.length > 0 && (
        <section className="card small">
          <h2 style={{ marginTop: 0 }}>이번 비교 {rounds.length > 1 ? `(${rounds.length}회)` : ''}</h2>
          <div style={{ overflowX: 'auto' }}><table>
            <thead><tr><th>회</th><th>Opus 첫 응답</th><th>Opus 결정 완료</th><th>Jev 결정 완료</th><th>차이(Opus − Jev)</th></tr></thead>
            <tbody>
              {rounds.map((r) => (
                <tr key={r.i}><td>{r.i}</td><td>{ms(r.opus.firstMs)}</td><td>{r.opus.status === 'ok' ? ms(r.opus.doneMs) : <span className="err">실패</span>}</td>
                  <td>{r.jev.status === 'ok' ? ms(r.jev.doneMs) : <span className="err">실패</span>}</td>
                  <td>{r.opus.status === 'ok' && r.jev.status === 'ok' ? ms((r.opus.doneMs ?? 0) - (r.jev.doneMs ?? 0)) : '—'}</td></tr>
              ))}
              {rounds.length > 1 && (
                <tr><th>중앙값</th><th>{ms(med((r) => r.opus.firstMs))}</th><th>{ms(med((r) => r.opus.doneMs))}</th><th>{ms(med((r) => r.jev.doneMs))}</th>
                  <th>{ms(med((r) => (r.opus.doneMs ?? 0) - (r.jev.doneMs ?? 0)))}</th></tr>
              )}
            </tbody>
          </table></div>
          <p className="dim">중앙값은 두 쪽 모두 성공한 회만 셉니다.</p>
        </section>
      )}

      <section className="card small">
        <h2 style={{ marginTop: 0 }}>읽는 법</h2>
        <ul>
          <li><b>시간</b> = 서버가 잰 값. 요청을 보내기 직전부터 잽니다. 화면 스톱워치는 보여 주기용이라 몇 ms 다를 수 있습니다.</li>
          <li><b>Opus 첫 응답</b> = 답 글자가 처음 나온 때. Opus 5.5 는 먼저 생각하고 나서 답을 쓰므로 「생각 시작」과 「첫 응답」 사이가 생각 시간입니다. <b>Jev</b> 는 답을 한 번에 돌려주므로 첫 응답 = 결정 완료입니다.</li>
          <li><b>확률</b>: Jev 의 확률은 모델이 내놓는 분포이고, Opus 의 확률은 모델이 글로 적은 값(보정 안 됨)입니다. 같은 뜻의 숫자가 아니어서 크기를 비교하지 않습니다. 두 쪽 답의 옳고 그름도 가리지 않습니다.</li>
          <li><b>형식 검사</b> = 앱이 쓰는 검사(질문 · 선택지 · 확률 합 · 점수와 분포)를 두 답에 똑같이 적용한 결과. Opus 에는 confidence 를 묻지 않으므로 그 칸만 검사하지 않습니다.</li>
        </ul>
      </section>

      <section className="card small">
        <h2 style={{ marginTop: 0 }}>기록(최근 100건)</h2>
        <p>이 계획의 비교 호출 {info.totals.calls}회 · 토큰 입력 {info.totals.input_tokens.toLocaleString()} / 출력 {info.totals.output_tokens.toLocaleString()} <span className="dim">(원화 비용은 표시하지 않습니다)</span></p>
        {info.runs.length > 0 && (
          <div style={{ overflowX: 'auto' }}><table>
            <thead><tr><th>시각(UTC)</th><th>쪽</th><th>모델</th><th>effort</th><th>첫 응답</th><th>결정 완료</th><th>상태</th><th>형식 검사</th></tr></thead>
            <tbody>{info.runs.map((r: any) => (
              <tr key={r.race_id}><td>{r.created_at?.replace('T', ' ').replace('+00:00', '')}</td><td>{r.who === 'opus' ? 'Opus' : 'Jev'}</td><td>{r.model_returned || r.model_requested}</td>
                <td>{r.effort || '—'}</td><td>{ms(r.first_ms)}</td><td>{ms(r.done_ms)}</td><td className={r.status === 'ok' ? '' : 'err'}>{r.status === 'ok' ? '성공' : `실패 — ${r.error}`}</td><td>{r.check_status || '—'}</td></tr>
            ))}</tbody>
          </table></div>
        )}
      </section>
    </>
  )
}
