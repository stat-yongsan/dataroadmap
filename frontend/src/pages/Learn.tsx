import { useEffect, useState } from 'react'
import { api, CONTROL_KO, fmtP, Link } from '../api'

// ---- 통계 실습: 브라우저에서 계산. 정답은 강의 원고에 손으로 적힌 값(6·7·49·6.51·4.55·1/49·0.16·0.1961·20·2)으로 대조한다 ----
const r = (x: number, d = 4) => (Number.isFinite(x) ? Number(x.toFixed(d)) : NaN)
function moments(out: [number, number][]) {
  const mean = out.reduce((s, [x, p]) => s + x * p, 0)
  return { mean, variance: out.reduce((s, [x, p]) => s + p * (x - mean) ** 2, 0) }
}
const entropy = (ps: number[]) => -ps.filter((p) => p > 0).reduce((s, p) => s + p * Math.log2(p), 0)
const brier = (p: number, yes: number, n: number) => (yes * (p - 1) ** 2 + (n - yes) * p ** 2) / n

function Num({ label, value, set, step = 1, min, max, w = '5rem' }: { label: string; value: number; set: (v: number) => void; step?: number; min?: number; max?: number; w?: string }) {
  return <label className="small">{label} <input type="number" value={value} step={step} min={min} max={max} style={{ width: w }} onChange={(e) => set(Number(e.target.value))} /></label>
}

function Stats() {
  const [a, setA] = useState(6)
  const [b1, setB1] = useState(0)
  const [b2, setB2] = useState(14)
  const [pb, setPb] = useState(0.5)
  const [beta, setBeta] = useState(0.05)
  const [sp, setSp] = useState([0.1, 0.7, 0.2])
  const [bp, setBp] = useState(0.8)
  const [yes, setYes] = useState(8)
  const [n, setN] = useState(10)
  const [pc, setPc] = useState(0.8)
  const [errCost, setErrCost] = useState(100)
  const [revCost, setRevCost] = useState(5)
  const A = moments([[a, 1]])
  const B = moments([[b1, pb], [b2, 1 - pb]])
  const U = (m: { mean: number; variance: number }, bt: number) => m.mean - bt * m.variance
  const betaStar = B.variance !== A.variance ? (B.mean - A.mean) / (B.variance - A.variance) : NaN
  const S = moments(sp.map((p, i) => [i, p] as [number, number]))
  const sSum = sp.reduce((s, p) => s + p, 0)
  const loss = (p: number) => (1 - p) * errCost
  return (
    <>
      <section className="card">
        <h3 style={{ marginTop: 0 }}>① 기댓값 · 분산 · 위험 조정(β) — 강의 6 · 12절</h3>
        <div className="row"><Num label="안정형 A 값(확률 1)" value={a} set={setA} /><Num label="변동형 B 결과1" value={b1} set={setB1} /><Num label="결과1 확률" value={pb} set={setPb} step={0.05} min={0} max={1} /><Num label="결과2" value={b2} set={setB2} /></div>
        <p className="small">A: 평균 <b>{r(A.mean)}</b> · 분산 <b>{r(A.variance)}</b> — B: 평균 <b data-testid="mean-b">{r(B.mean)}</b> · 분산 <b data-testid="var-b">{r(B.variance)}</b> · 표준편차 {r(Math.sqrt(B.variance))}</p>
        <table><thead><tr><th>β</th><th>A 효용 E−βVar</th><th>B 효용</th><th>선택</th></tr></thead><tbody>
          {[0, 0.01, 0.05].map((bt) => <tr key={bt}><td>{bt}</td><td>{r(U(A, bt))}</td><td data-testid={`u-b-${bt}`}>{r(U(B, bt))}</td><td>{U(B, bt) > U(A, bt) ? 'B' : U(B, bt) < U(A, bt) ? 'A' : '같음'}</td></tr>)}
          <tr><td><Num label="직접" value={beta} set={setBeta} step={0.005} min={0} w="5.5rem" /></td><td>{r(U(A, beta))}</td><td>{r(U(B, beta))}</td><td>{U(B, beta) > U(A, beta) ? 'B' : U(B, beta) < U(A, beta) ? 'A' : '같음'}</td></tr>
        </tbody></table>
        <p className="small">두 선택이 같아지는 β = <b data-testid="beta-star">{r(betaStar, 5)}</b>{Math.abs(betaStar - 1 / 49) < 1e-9 ? ' (= 1/49)' : ''} · 결과 단위를 100배로 바꾸면 같은 순위를 위해 β 도 1/100 로 바꿔야 한다.</p>
        <p className="dim small">이 계산은 확률을 학습하지 않는다. 우리가 정한 확률에서 통계량을 계산할 뿐이며, E[R]−βVar(R) 는 Jev 의 공식 학습 손실이 아니다.</p>
      </section>
      <section className="card">
        <h3 style={{ marginTop: 0 }}>② Score = 수준 번호의 확률 가중평균 — 강의 8절</h3>
        <div className="row">{sp.map((p, i) => <Num key={i} label={`수준 ${i} 확률`} value={p} step={0.05} min={0} max={1} set={(v) => setSp(sp.map((x, j) => (j === i ? v : x)))} />)}
          <button onClick={() => setSp([0.1, 0.7, 0.2])}>강의 예(0.1·0.7·0.2)</button><button onClick={() => setSp([0, 1, 0])}>중간에 집중</button><button onClick={() => setSp([0.5, 0, 0.5])}>낮음·높음 사이</button></div>
        {Math.abs(sSum - 1) > 1e-9 && <p className="err small">확률 합이 {r(sSum)} — 1 이어야 합니다</p>}
        <p className="small">Score <b data-testid="score-value">{r(S.mean, 2)}</b> · 수준 번호의 분산 {r(S.variance, 2)} · 엔트로피 {r(entropy(sp), 2)} bit</p>
        <p className="dim small">1.10 은 정답률 110% 도, 55% 준비됐다는 측정값도 아니다. 엔트로피는 여기서 계산한 통계량이며 Jev confidence 의 공식이 아니다.</p>
      </section>
      <section className="card">
        <h3 style={{ marginTop: 0 }}>③ 보정과 Brier 점수 — 강의 9절</h3>
        <div className="row"><Num label="실제 예 건수" value={yes} set={setYes} min={0} /><Num label="전체 건수" value={n} set={setN} min={1} /><Num label="모두에 준 확률" value={bp} set={setBp} step={0.01} min={0} max={1} /></div>
        <table><thead><tr><th>확률</th><th>Brier(작을수록 좋음)</th></tr></thead><tbody>
          <tr><td>0.8</td><td data-testid="brier-0.8">{r(brier(0.8, yes, n))}</td></tr><tr><td>0.99</td><td data-testid="brier-0.99">{r(brier(0.99, yes, n))}</td></tr>
          <tr><td>{bp}</td><td>{r(brier(bp, yes, n))}</td></tr></tbody></table>
        <p className="dim small">10건은 개념 설명용이다. 실제 보정 성능을 입증하는 표본이 아니고, confidence 0.9 가 곧 90% 정답률이라는 뜻도 아니다.</p>
      </section>
      <section className="card">
        <h3 style={{ marginTop: 0 }}>④ 오류 비용에 따른 자동처리 · 검토 — 강의 13 · 19절</h3>
        <div className="row"><Num label="틀렸을 때 손실" value={errCost} set={setErrCost} /><Num label="검토 비용" value={revCost} set={setRevCost} /><Num label="p_correct" value={pc} set={setPc} step={0.01} min={0} max={1} /></div>
        <table><thead><tr><th>p_correct</th><th>자동처리 기대손실</th><th>선택</th></tr></thead><tbody>
          {[0.8, 0.98, pc].map((p, i) => <tr key={i}><td>{p}</td><td data-testid={i < 2 ? `loss-${p}` : undefined}>{r(loss(p), 2)}</td><td>{loss(p) < revCost ? '자동처리 후보' : '검토'}</td></tr>)}</tbody></table>
        <p className="dim small">p_correct 는 그 업무에서 검증된 정답확률이라는 가정이다. 실제 실행에는 허용된 작업 · 사전조건 · 데이터 검증도 필요하다.</p>
      </section>
    </>
  )
}

// ---- 2단계 판단 실습: 앱 엔진을 그대로 부른다(따로 흉내 내지 않음) ----
function TwoStep() {
  const [log, setLog] = useState<any[]>([])
  const [plan, setPlan] = useState<any>(null)
  const [agg, setAgg] = useState<any>(null)
  const [expected, setExpected] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  async function show(pid: string, note: string) {
    const p = await api(`/api/plans/${pid}`)
    setPlan(p)
    const probs = p.root_decision?.probabilities || {}
    const top = Object.entries(probs).sort((x: any, y: any) => y[1] - x[1])[0]
    setLog((l) => [...l, { note, pid, top, probs, numeric: p.root_state.columns?.['금액']?.numeric, kind: p.root_state.columns?.['금액']?.kind }])
    const a = p.root_state.artifacts.find((x: any) => x.kind === 'agg_sum')
    if (a) setAgg(await api(`/api/versions/${a.version_id}`))
  }
  async function go(fn: () => Promise<void>) { setErr(''); setBusy(true); try { await fn() } catch (e: any) { setErr(e.message) } finally { setBusy(false) } }
  const start = () => go(async () => {
    setLog([]); setAgg(null)
    const exs = await api('/api/examples')
    setExpected(exs.find((x: any) => x.key === 'A').expected)
    const ex = await api('/api/examples/A', { method: 'POST' })
    const g = await api(`/api/datasets/${ex.dataset_id}/goals`, { body: ex.suggested })
    await show(g.plan_id, '예제 A 를 올리고 첫 판단')
  })
  const top = log.length ? log[log.length - 1].top : null
  const readyTop = plan?.nodes.find((n: any) => n.depth === 1 && n.project_id && top && n.project_id === top[0] && n.status === 'ready')
  const next = () => go(async () => {
    const r2 = await api(`/api/plans/${plan.plan.plan_id}/nodes/${readyTop.node_id}/run`, { method: 'POST', body: {} })
    await show(r2.plan_id, `${readyTop.project_id} 실행 → 결과 검증 → 새 상태에서 다시 판단`)
  })
  const total = agg ? agg.rows.reduce((s: number, row: any[]) => s + row[3], 0) : null
  return (
    <section className="card">
      <h3 style={{ marginTop: 0 }}>상태 → 판단 → 파이썬 실행 → 새 상태 → 다시 판단 (예제 A, jev_easy_demo.py 와 같은 흐름)</h3>
      <p className="small dim">모의 판단(MOCK)입니다. MOCK 은 confidence 를 만들지 않습니다 — 강의 7절의 confidence 는 실제 Jev 응답에 있는 값입니다.</p>
      <div className="row"><button className="primary" disabled={busy} onClick={start}>1. 예제 A 불러와 판단</button>
        <button disabled={busy || !readyTop} onClick={next}>{readyTop ? `2. 1순위 작업 ${readyTop.project_id} 실행` : '실행할 1순위 작업 없음'}</button>
        {plan && <Link to={`/roadmaps/${plan.plan.plan_id}`}>이 계획의 그래프 보기</Link>}</div>
      {err && <p className="err">{err}</p>}
      {log.map((l, i) => (
        <div key={i} className="card small">
          <b>{i + 1}단계 · {l.note}</b>
          <div>금액 열: {l.kind}{l.numeric === true ? ' (숫자)' : ' (아직 문자)'} · Choice 1순위 <b>{CONTROL_KO[l.top?.[0]] || l.top?.[0]}</b> ({fmtP(l.top?.[1])})</div>
          <div className="dim">분포: {Object.entries(l.probs).sort((x: any, y: any) => y[1] - x[1]).map(([k, p]: any) => `${k} ${p.toFixed(2)}`).join(' · ')}</div>
        </div>))}
      {agg && (
        <div className="card small">
          <b>파이썬 합산 결과</b> {agg.rows.map((row: any[]) => `${row[0]} ${row[3].toLocaleString()}원`).join(' · ')} · 총 {total?.toLocaleString()}원
          {expected && <div className={total === expected.total && agg.rows.every((row: any[]) => expected.sum[row[0]] === row[3]) ? 'ok' : 'err'}>
            정답(실행 전에 고정한 값) 대조: 교과 {expected.sum['교과']} · 비교과 {expected.sum['비교과']} · 총 {expected.total} → {total === expected.total ? '일치' : '불일치'}</div>}
        </div>
      )}
    </section>
  )
}

export default function Learn() {
  const [outline, setOutline] = useState<any>(null)
  useEffect(() => { api('/api/learn/outline').then(setOutline) }, [])
  return (
    <>
      <h1>배우기 — Jev: 확률로 다음 작업을 고르는 AI</h1>
      <p className="small dim">60분 강의 원고(docs/source/Jev_60min_Lecture_KO.md)의 목차와 실습입니다.</p>
      <p><a href="/lecture/" target="_blank" rel="noopener">발표용 슬라이드 열기 — 60분판(38장 · 퀴즈 8개)</a> · <a href="/lecture/15min.html" target="_blank" rel="noopener">15분 핵심판(9장 · 실습 1개)</a> <span className="small dim">— 앱 없이도 data-roadmap\lecture\ 의 index.html · 15min.html 을 더블클릭하면 열립니다. ← → · Space 로 넘깁니다.</span></p>
      <section className="card">
        <h2 style={{ marginTop: 0 }}>강의 20단위</h2>
        {outline ? <ol className="small">{outline.units.map((u: any) => <li key={u.no}><b>{u.title}</b> <span className="dim">{u.time}</span>{u.screen && <div className="dim">{u.screen}</div>}</li>)}</ol> : <p className="dim">불러오는 중…</p>}
      </section>
      <h2>통계 실습 — 값을 바꿔 보기</h2>
      <Stats />
      <h2>2단계 판단 실습</h2>
      <TwoStep />
    </>
  )
}
