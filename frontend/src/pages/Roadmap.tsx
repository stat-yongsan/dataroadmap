import { useEffect, useMemo, useRef, useState } from 'react'
import { Background, Controls, Handle, Panel, Position, ReactFlow, type Edge, type Node, type NodeProps, type ReactFlowInstance } from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import dagre from '@dagrejs/dagre'
import { api, Badge, CONTROL_KO, fmtP, GATE_KO, IMPL_KO, Link, navigate, PROVIDER_NAME, STATUS_KO } from '../api'

const W = 210, H = 70

type StepData = { label: string; sub: string; status: string; suggested: boolean; history?: boolean; selected?: boolean; hl?: boolean }

function StepNode({ data }: NodeProps<Node<StepData>>) {
  const dashed = data.status === 'projected'
  return (
    <div style={{
      width: W, minHeight: H, padding: '6px 8px', borderRadius: 8, background: 'var(--panel)', color: 'var(--fg)', fontSize: 12,
      border: `${data.selected ? 3 : data.hl ? 2 : 1}px ${dashed ? 'dashed' : 'solid'} ${data.selected || data.hl ? 'var(--accent)' : data.history ? 'var(--ok)' : 'var(--line)'}`,
      opacity: data.status === 'unsupported' ? 0.8 : 1,
    }}>
      <Handle type="target" position={Position.Left} style={{ opacity: 0 }} />
      <div style={{ fontWeight: 700, lineHeight: 1.25 }}>{data.label}</div>
      <div style={{ color: 'var(--dim)', fontSize: 11, lineHeight: 1.2, margin: '2px 0' }}>{data.sub}</div>
      <span className={`badge st-${data.status}`}>{STATUS_KO[data.status] || data.status}</span>
      {data.suggested && <span className="sug"> ★ 추천됨</span>}
      <Handle type="source" position={Position.Right} style={{ opacity: 0 }} />
    </div>
  )
}
const nodeTypes = { step: StepNode }

function layout(nodes: Node[], edges: Edge[]) {
  const g = new dagre.graphlib.Graph()
  g.setGraph({ rankdir: 'LR', nodesep: 18, ranksep: 70 })
  g.setDefaultEdgeLabel(() => ({}))
  nodes.forEach((n) => g.setNode(n.id, { width: W, height: H + 8 }))
  edges.forEach((e) => g.setEdge(e.source, e.target))
  dagre.layout(g)
  return nodes.map((n) => { const p = g.node(n.id); return { ...n, position: { x: p.x - W / 2, y: p.y - H / 2 } } })
}

function Dist({ probs, chosen }: { probs: Record<string, number> | null; chosen?: string | null }) {
  if (!probs) return <span className="dim">판단 분포 없음</span>
  const rows = Object.entries(probs).sort((a, b) => b[1] - a[1])
  return (
    <table><tbody>{rows.map(([k, p]) => (
      <tr key={k} style={{ fontWeight: k === chosen ? 700 : 400 }}><td style={{ width: '38%' }}>{CONTROL_KO[k] || k}</td>
        <td><div className="bar" style={{ width: `${Math.max(1, p * 100)}%` }} /></td><td style={{ width: '4.5rem' }}>{fmtP(p)}</td></tr>))}
    </tbody></table>
  )
}

// ★ 설명(Q7): ★ 는 계획을 만들 때 경로 비교 1위 경로의 노드에 붙는다(planning.py). 「후보 더 보기」 뒤에는 순위가 다시 매겨지므로
// paths[0] 이 아니라 ★ 노드 목록과 같은 경로를 찾는다.
function StarNote({ d, sel }: { d: any; sel: string }) {
  const n = d.nodes.find((x: any) => x.node_id === sel)
  if (!n || n.depth === 0) return null
  const sug = new Set<string>(d.nodes.filter((x: any) => x.suggested).map((x: any) => x.node_id))
  const star = d.paths.find((p: any) => p.nodes.length === sug.size && p.nodes.every((id: string) => sug.has(id)))
  if (!star) return null
  if (d.plan.provider === 'codex') return <p className="small dim">★는 현재 측정 상태에서 Codex가 선택한 다음 작업입니다. Python 실행·검증 뒤 새 상태에서 다시 판단합니다. 선택 표시는 성공확률이 아닙니다.</p>
  const name = (p: any) => (p.steps.join(' → ') || '(바로 멈춤)') + (p.ends_with === 'done' ? ' → 끝' : '')
  const f = (x: number) => x.toFixed(3)
  const kind = star.complete ? '완료 경로' : '부분 경로(완료 경로 없음)'
  const tail = <p className="dim small" style={{ margin: 0 }}>한 단계의 선택지 확률 하나가 아니라, 경로에 있는 각 단계 선택지 확률의 기하평균(경로 추천 점수)으로 고릅니다. 경로 추천 점수는 성공확률이 아닙니다.</p>
  if (n.suggested) {
    const k = star.nodes.indexOf(sel)
    const others = d.paths.filter((p: any) => p !== star && p.complete === star.complete)
    const second = others[0]
    const alt = n.depth === 1 ? others.find((p: any) => p.nodes[1] !== sel) : null
    return (
      <div className="small" data-testid="star-note" style={{ borderLeft: '3px solid var(--accent)', padding: '.2rem .5rem', margin: '.3rem 0' }}>
        <div>★ = 계획을 만들 때 {kind} 1위의 {k === 1 ? '첫' : `${k}번째`} 단계 — <b>{name(star)}</b> · 경로 추천 점수 <b>{f(star.score)}</b></div>
        <div>{second ? <>2위 {name(second)} {f(second.score)} · 차이 {f(star.score - second.score)}</> : '비교할 2위 경로 없음'}</div>
        {alt && alt !== second && <div>다른 첫 단계로 가는 최고 경로 {name(alt)} {f(alt.score)} · 차이 {f(star.score - alt.score)}</div>}
        {tail}
      </div>
    )
  }
  if (n.depth !== 1) return null
  const mine = d.paths.find((p: any) => p.nodes[1] === sel && p.complete === star.complete)
  return (
    <div className="small" data-testid="star-note" style={{ borderLeft: '3px solid var(--line)', padding: '.2rem .5rem', margin: '.3rem 0' }}>
      {mine ? <div>이 노드로 시작하는 최고 경로 {name(mine)} · 경로 추천 점수 {f(mine.score)} — ★ 경로({name(star)} {f(star.score)})보다 {f(star.score - mine.score)} 낮음</div>
        : <div>이 노드로 시작해 {star.complete ? '목표까지 닿는' : '비교할'} 경로가 탐색 안에 없음 — ★ 경로 {name(star)} {f(star.score)}</div>}
      {tail}
    </div>
  )
}

export default function Roadmap({ planId, onMode }: { planId: string, onMode?: (m: { provider: string, model?: string } | null) => void }) {
  const [d, setD] = useState<any>(null)
  const [err, setErr] = useState('')
  const [sel, setSel] = useState<string | null>(null)
  const [detail, setDetail] = useState<any>(null)
  const [showAll, setShowAll] = useState(false)
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set())
  const [hlPath, setHlPath] = useState<number | null>(null)
  const [compare, setCompare] = useState<number[]>([])
  const [busy, setBusy] = useState(false)

  const load = () => api(`/api/plans/${planId}`).then(setD).catch((e) => setErr(e.message))
  useEffect(() => { load() }, [planId]) // eslint-disable-line
  useEffect(() => {
    onMode?.(d ? { provider: d.plan.provider, model: d.root_decision?.model_returned || d.plan.versions?.model_requested } : null)
    return () => onMode?.(null)
  }, [d]) // eslint-disable-line

  useEffect(() => {
    setDetail(null)
    if (!sel || !d) return
    if (sel.startsWith('h:')) { setDetail({ history: d.history.find((h: any) => 'h:' + h.step_run_id === sel) }); return }
    api(`/api/plans/${planId}/nodes/${sel}`).then(setDetail).catch((e) => setErr(e.message))
  }, [sel, d, planId])

  const graph = useMemo(() => {
    if (!d) return { nodes: [] as Node[], edges: [] as Edge[], focus: [] as { id: string }[] }
    const byId: Record<string, any> = Object.fromEntries(d.nodes.map((n: any) => [n.node_id, n]))
    const root = d.nodes.find((n: any) => n.depth === 0)
    const top = d.paths.slice(0, 3).flatMap((p: any) => p.nodes)
    const visible = new Set<string>(showAll ? d.nodes.map((n: any) => n.node_id) : [root.node_id, ...top, ...d.nodes.filter((n: any) => n.depth === 1).map((n: any) => n.node_id)])
    // 접은 가지의 자손은 숨긴다
    const kids: Record<string, string[]> = {}
    d.edges.forEach((e: any) => { (kids[e.from] ||= []).push(e.to) })
    const hide = new Set<string>()
    const walk = (id: string) => (kids[id] || []).forEach((k) => { if (!hide.has(k)) { hide.add(k); walk(k) } })
    collapsed.forEach((c) => walk(c))
    const hlNodes = new Set<string>(hlPath !== null && d.paths[hlPath] ? d.paths[hlPath].nodes : [])
    const nodes: Node[] = []
    const edges: Edge[] = []
    d.history.forEach((h: any, i: number) => {
      nodes.push({ id: 'h:' + h.step_run_id, type: 'step', position: { x: 0, y: 0 }, data: { label: `${h.project_id} · ${h.title || ''}`, sub: '실제 실행', status: h.status, suggested: false, history: true, selected: sel === 'h:' + h.step_run_id } })
      const next = i + 1 < d.history.length ? 'h:' + d.history[i + 1].step_run_id : root.node_id
      edges.push({ id: 'he' + i, source: 'h:' + h.step_run_id, target: next, label: '실행됨', style: { stroke: 'var(--ok)', strokeWidth: 2 } })
    })
    d.nodes.forEach((n: any) => {
      if (!visible.has(n.node_id) || hide.has(n.node_id)) return
      const label = n.depth === 0 ? '현재 상태(측정)' : n.control_action ? CONTROL_KO[n.control_action] : `${n.project_id} · ${n.title || ''}`
      const sub = n.depth === 0 ? `버전 ${d.plan.base_version_id}` : n.control_action ? (n.terminal_reason || '') : `${IMPL_KO[n.implementation_status] || ''}${collapsed.has(n.node_id) ? ' · 접힘' : ''}`
      nodes.push({ id: n.node_id, type: 'step', position: { x: 0, y: 0 }, data: { label, sub, status: n.status, suggested: n.suggested, selected: sel === n.node_id, hl: hlNodes.has(n.node_id) } })
    })
    const shown = new Set(nodes.map((n) => n.id))
    d.edges.forEach((e: any, i: number) => {
      if (!shown.has(e.from) || !shown.has(e.to)) return
      const target = byId[e.to]
      const hl = hlNodes.has(e.from) && hlNodes.has(e.to)
      edges.push({ id: 'e' + i, source: e.from, target: e.to, label: `${e.p.toFixed(2)}${e.kind === 'merge' ? ' · 합류' : e.kind === 'expand' ? ' · 더 보기' : ''}`,
        style: { strokeDasharray: target?.state_kind === 'projected' || target?.state_kind === 'control' ? '6 4' : undefined, strokeWidth: hl ? 3 : 1.3, stroke: hl ? 'var(--accent)' : 'var(--projected)' },
        labelStyle: { fontSize: 10 } })
    })
    // 첫 화면은 실행 이력 · 현재 상태 · 앞 두 단계에 맞춘다(전체는 「전체 보기」 버튼)
    const lastH = d.history.length ? 'h:' + d.history[d.history.length - 1].step_run_id : null
    const focus = nodes.filter((n) => n.id === lastH || (byId[n.id] && byId[n.id].depth <= 2)).map((n) => ({ id: n.id }))
    return { nodes: layout(nodes, edges), edges, focus }
  }, [d, showAll, collapsed, sel, hlPath])

  // G17~G19: 그래프만 모니터 전체 화면(브라우저 기본 기능 · Esc 로도 나옴). 들어가면 보이는 가지 전체, 나오면 첫 화면처럼 가까운 단계만.
  // 크기가 바뀐 뒤(React Flow 가 새 크기를 잰 뒤) 맞추려고 잠깐 기다린다
  const box = useRef<HTMLDivElement>(null)
  const [rf, setRf] = useState<ReactFlowInstance<Node, Edge> | null>(null)
  const [full, setFull] = useState(false)
  useEffect(() => {
    const on = () => {
      const f = document.fullscreenElement === box.current
      setFull(f)
      setTimeout(() => rf?.fitView(f ? { padding: 0.1 } : { nodes: graph.focus, maxZoom: 1.1, padding: 0.15 }), 100)
    }
    document.addEventListener('fullscreenchange', on)
    return () => document.removeEventListener('fullscreenchange', on)
  }, [rf, graph.focus])

  if (err && !d) return <p className="err">{err}</p>
  if (!d) return <p className="dim">계획을 불러오는 중…</p>
  const st = d.root_state
  const codex = d.plan.provider === 'codex'
  const providerName = PROVIDER_NAME[d.plan.provider] || d.plan.provider
  const selNode = d.nodes.find((n: any) => n.node_id === sel)
  const own = selNode?.decision_call_id ? d.decisions[selNode.decision_call_id] : null
  const childOpts = new Set(d.edges.filter((e: any) => e.from === sel).map((e: any) => e.option))

  async function act(fn: () => Promise<void>) {
    setErr(''); setBusy(true)
    try { await fn() } catch (e: any) { setErr(e.message) } finally { setBusy(false) }
  }

  return (
    <>
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <h1>{d.goal.label} <span className="dim small">— {Object.entries(d.goal.params).map(([k, v]) => `${k}=${Array.isArray(v) ? v.join(',') : v}`).join(' · ')}</span></h1>
        <span className="row">{!codex && <Link to={`/race/${planId}`}>Opus 5.5 vs Jev 결정 속도 비교 →</Link>}<Link to={`/?ds=${d.plan.dataset_id}`}>← 데이터 · 목적 바꾸기</Link></span>
      </div>
      {d.newer_plan && <p className="card">이 계획 뒤에 새 계획이 있습니다(실행 후 재계획). <Link to={`/roadmaps/${d.newer_plan}`}>최신 계획으로</Link></p>}
      {err && <p className="err">{err}</p>}
      <section className="card small">
        <div className="row">
          <span><b>현재 observed 상태</b> 버전 <code>{st.dataset_version_id}</code></span>
          <span>한 행의 의미: {st.grain?.value || <span className="err">미확인</span>}</span>
          <span>표 범위: {st.table_confirmed ? '확정' : <span className="err">미확정</span>}</span>
          {st.key_dup_groups !== null && st.key_dup_groups !== undefined && <span>업무 키 중복 그룹(측정): {st.key_dup_groups}</span>}
          <span>판단: <b>{d.plan.provider === 'mock' ? '모의 판단(MOCK)' : `LIVE(${providerName} · ${d.root_decision?.model_returned || d.plan.versions?.model_requested || '모델 미상'})`}</b>{d.plan.provider !== 'mock' && <> · 호출 {d.plan.calls_used ?? 0}/{d.config?.max_live_calls_per_plan ?? 10}회</>}</span>
          <span>계획 버전: {d.lineage.map((l: any, i: number) => <span key={l.plan_id}>{i > 0 && ' → '}{l.plan_id === planId ? <b>{i + 1}</b> : <Link to={`/roadmaps/${l.plan_id}`}>{i + 1}</Link>}</span>)}</span>
        </div>
        {st.unresolved_requirements?.length > 0 && <p className="err">부족한 정보: {st.unresolved_requirements.join(' · ')}</p>}
        <div className="row">실행한 작업: {st.completed_steps.length ? st.completed_steps.map((s: any) => <span key={s.step_run_id}>{s.project_id} <Badge s={s.status} /></span>) : <span className="dim">없음</span>}
          {st.artifacts.length > 0 && <span> · 결과: {st.artifacts.map((a: any) => a.kind).join(', ')}</span>}</div>
        {d.plan.stop_reasons?.length > 0 && <p className="dim">탐색이 멈춘 이유: {d.plan.stop_reasons.join(' · ')}</p>}
      </section>

      <div className="row small" style={{ margin: '.3rem 0' }}>
        <label><input type="checkbox" checked={showAll} onChange={(e) => setShowAll(e.target.checked)} /> 모든 가지 보기(기본은 상위 경로 3개 + 지금 할 수 있는 후보)</label>
        {hlPath !== null && <button onClick={() => setHlPath(null)}>경로 강조 끄기</button>}
        <span className="dim">실선 = 실제 실행 · 점선 = 아직 실행하지 않은 계획 · {codex ? '1=Codex 선택, 0=대안(확률 아님)' : '숫자 = 그 단계의 선택지 확률'}</span>
      </div>
      <div className="split">
        <div ref={box} className="card" style={{ height: '64vh', minHeight: 380, padding: 0 }}>
          <ReactFlow nodes={graph.nodes} edges={graph.edges} nodeTypes={nodeTypes} nodesDraggable={false} nodesConnectable={false}
            fitView fitViewOptions={{ nodes: graph.focus, maxZoom: 1.1, padding: 0.15 }} onInit={setRf}
            onNodeClick={(_, n) => setSel(n.id)} onPaneClick={() => setSel(null)} minZoom={0.2} proOptions={{ hideAttribution: true }}>
            <Background />
            <Controls showInteractive={false} />
            <Panel position="top-right">
              <button onClick={() => full ? document.exitFullscreen() : box.current?.requestFullscreen()}>{full ? '전체 화면 끝(Esc)' : '⛶ 전체 화면'}</button>
            </Panel>
          </ReactFlow>
        </div>
        <aside className="card" style={{ maxHeight: '64vh', overflowY: 'auto' }}>
          {!sel && (
            <>
              <h3 style={{ marginTop: 0 }}>현재 상태에서의 판단</h3>
              <p className="small dim">{codex ? 'Codex가 실제로 고른 다음 작업입니다. 1=선택, 0=대안이며 확률이 아닙니다.' : d.root_decision?.provider === 'mock' ? '모의 판단 — 명시한 로컬 규칙(policy.v1)의 분포입니다.' : `LIVE — ${providerName} 가 돌려준 분포입니다.`} 노드를 누르면 조건 · 근거 · 입출력이 보입니다.</p>
              {codex && <p>{d.root_decision?.answers?.answers?.next_step?.reason}</p>}
              <Dist probs={d.root_decision?.probabilities} chosen={d.root_decision && Object.entries(d.root_decision.probabilities || {}).sort((a: any, b: any) => b[1] - a[1])[0]?.[0]} />
              <p className="small">판단 확신 지표(confidence): {d.root_decision?.confidence ?? (d.root_decision?.provider === 'mock' ? '없음(모의 판단)' : '없음')} <span className="dim">— 정답률이 아닙니다</span></p>
              <details><summary>영역별 필요성(Noul) · 후보별 목표 기여도(Score)</summary>
                <table><tbody>{Object.entries(d.root_decision?.answers?.answers || {}).filter(([k]) => k !== 'next_step').map(([k, a]: any) => (
                  <tr key={k}><td>{k.replace('area_', '영역 ').replace('contrib_', '기여 ')}</td><td>{a.type === 'noul' ? codex ? (a.noul === 1 ? '필요' : '현재는 불필요') : `예일 확률 ${fmtP(a.noul)}` : `수준 ${a.score} — ${a.legend?.[a.score] ?? a.legend?.[String(a.score)] ?? ''}`}</td></tr>))}</tbody></table>
                <p className="dim small">Noul 은 각각 독립 질문이라 합이 1 일 필요가 없고, 경로 점수에는 넣지 않습니다.</p>
              </details>
            </>
          )}
          {sel && detail?.history && (
            <>
              <h3 style={{ marginTop: 0 }}>{detail.history.project_id} · {detail.history.title} <Badge s={detail.history.status} /></h3>
              <p className="small">실제로 실행한 단계입니다.</p>
              {detail.history.checks?.map((c: any, i: number) => <div key={i} className="small">{c.status === 'passed' ? '✔' : '✘'} {c.name} <code>{JSON.stringify(c.detail).slice(0, 180)}</code></div>)}
              {detail.history.issues?.length > 0 && <p className="err small">{detail.history.issues.join(' / ')}</p>}
              <p><Link to={`/runs/${d.plan.run_id}`}>실행 기록 전체 보기</Link></p>
            </>
          )}
          {sel && detail?.node && (
            <>
              <h3 style={{ marginTop: 0 }}>{detail.node.project_id ? `${detail.node.project_id} · ${detail.card?.title}` : detail.node.depth === 0 ? '현재 상태(측정)' : CONTROL_KO[detail.node.control_action]} <Badge s={detail.node.display_status} />{detail.node.suggested ? <span className="sug"> ★ 추천됨</span> : null}</h3>
              <StarNote d={d} sel={sel} />
              {detail.card && <p className="small dim">영역 {detail.card.area_id} · 환경 {detail.card.environment} — {detail.card.environment_label} · {IMPL_KO[detail.impl?.implementation_status]}</p>}
              {detail.control_text && <p className="small">{detail.control_text}</p>}
              {detail.node.terminal_reason && <p className="small dim">멈춘 이유: {detail.node.terminal_reason}</p>}
              {selNode?.status === 'ready' && (
                <button className="primary" disabled={busy} onClick={() => act(async () => { const r = await api(`/api/plans/${planId}/nodes/${sel}/run`, { method: 'POST', body: {} }); navigate(`/roadmaps/${r.plan_id}`) })}>
                  {busy ? '실행 중…' : `${detail.node.project_id} 실행 → 결과 검증 → 다시 판단`}</button>
              )}
              {selNode && selNode.depth > 1 && selNode.state_kind === 'projected' && <p className="small dim">아직 입력이 없는 계획 노드입니다. 앞 단계를 실행하면 새 상태에서 다시 판단합니다.</p>}
              {detail.gate && (
                <>
                  <h3>실행 조건(코드가 판정)</h3>
                  <table><tbody>{Object.entries(GATE_KO).map(([k, label]) => {
                    const v = detail.gate[k]
                    return <tr key={k}><td>{label}</td><td>{v === true ? '✔' : v === false ? <span className="err">✘</span> : <span className="dim">조건부</span>}</td></tr>
                  })}</tbody></table>
                  {detail.gate.reasons?.length > 0 && <ul className="small">{detail.gate.reasons.map((r: string) => <li key={r}>{r}</li>)}</ul>}
                </>
              )}
              {detail.selection?.probabilities && (
                <>
                  <h3>선택 근거</h3>
                  {detail.selection.rule && <p className="small">규칙 <code>{detail.selection.rule.rule_id}</code> — {detail.selection.rule.text}</p>}
                  <p className="small">{codex ? '선택 지시자(1=선택, 0=대안)' : '이 선택지의 확률'} {fmtP(detail.selection.probabilities[detail.node.project_id || detail.node.control_action])} · 판단 확신 지표 {detail.selection.confidence ?? (d.plan.provider === 'mock' ? '없음(모의 판단)' : '없음')} <span className="dim">(정답률 아님)</span></p>
                  {detail.selection.score && <p className="small">목표 기여도(Score) 수준 {detail.selection.score.score} — {detail.selection.score.legend?.[detail.selection.score.score]}</p>}
                  <details><summary>{codex ? '선택 여부(같은 상태의 모든 후보)' : '확률 세부(같은 상태의 모든 선택지)'}</summary><Dist probs={detail.selection.probabilities} chosen={detail.node.project_id || detail.node.control_action} /></details>
                </>
              )}
              {detail.impl && (
                <>
                  <h3>입력 · 출력 계약 <span className="dim small">(앱 설계 · implementation_design)</span></h3>
                  <p className="small"><b>입력</b> {detail.impl.input_contract || '—'}<br /><b>출력</b> {detail.impl.output_contract || '—'}</p>
                  {detail.impl.preconditions?.length > 0 && <p className="small">사전조건: {detail.impl.preconditions.join(' · ')}</p>}
                  {detail.impl.why_not && <p className="small err">{detail.impl.why_not}</p>}
                </>
              )}
              {detail.state?.conditions?.length > 0 && detail.node.state_kind === 'projected' && <p className="small">계약상 조건: {detail.state.conditions.join(' · ')} <span className="dim">(측정값 아님)</span></p>}
              {detail.card && (
                <details><summary>원문 카드({detail.card.source_start_line}~{detail.card.source_end_line}행)</summary>
                  <p className="small"><b>입력 예제</b> {detail.card.input_example}<br /><b>변환·출력 계약</b> {detail.card.transformation_output_contract}<br />
                    <b>성공 기준</b> {detail.card.success_criteria}<br /><b>실패·경계 실험</b> {detail.card.failure_boundary_experiment}</p>
                </details>
              )}
              {own?.probabilities && (
                <details open><summary>후보 더 보기 — 이 노드에서 받은 판단</summary>
                  <table><tbody>{Object.entries(own.probabilities as Record<string, number>).sort((a, b) => b[1] - a[1]).map(([k, p]) => (
                    <tr key={k}><td>{CONTROL_KO[k] || k}</td><td>{fmtP(p)}</td><td>{childOpts.has(k) ? <span className="dim">펼쳐짐</span> :
                      <button disabled={busy} onClick={() => act(async () => { await api(`/api/plans/${planId}/nodes/${sel}/expand`, { body: { option: k } }); setShowAll(true); await load() })}>가지 추가</button>}</td></tr>))}</tbody></table>
                </details>
              )}
              {selNode && selNode.depth > 0 && (
                <button className="small" style={{ marginTop: '.4rem' }} onClick={() => setCollapsed((c) => { const n = new Set(c); n.has(sel!) ? n.delete(sel!) : n.add(sel!); return n })}>{collapsed.has(sel!) ? '가지 펼치기' : '가지 접기'}</button>
              )}
            </>
          )}
        </aside>
      </div>

      <section className="card">
        <h2 style={{ marginTop: 0 }}>경로 비교 <span className="dim small">— 같은 목적 안에서만 비교합니다</span></h2>
        <p className="small dim">{d.notes[0]}</p>
        {(['완료 경로', '부분 경로'] as const).map((kind) => {
          const list = d.paths.map((p: any, i: number) => ({ ...p, i })).filter((p: any) => p.complete === (kind === '완료 경로'))
          if (!list.length) return null
          return (
            <div key={kind} className="scroll">
              <h3>{kind === '완료 경로' ? '목표까지 닿는 경로(계획)' : kind} <span className="dim small">{kind === '부분 경로' ? '(목표에 아직 닿지 않음 — 정보 부족 · 지원 안 됨 · 탐색 한도 등)' : '(아직 실행하지 않은 계획 — 「결과 미리보기」는 복사본에서 돌려 보고 아무것도 남기지 않음)'}</span></h3>
              <table className="wide"><thead><tr><th>비교</th><th>순위</th><th>작업 순서</th><th>경로 추천 점수</th><th>실행기</th><th>결과</th><th>필요한 조건</th><th>끝</th><th>실행 시간</th><th>결과 미리보기</th></tr></thead><tbody>
                {list.slice(0, 10).map((p: any) => (
                  <tr key={p.i} style={{ background: hlPath === p.i ? 'var(--head)' : undefined }}>
                    <td><input type="checkbox" aria-label="비교" checked={compare.includes(p.i)} onChange={(e) => setCompare((c) => e.target.checked ? [...c.slice(-1), p.i] : c.filter((x) => x !== p.i))} /></td>
                    <td>{p.rank}</td><td><a href="#" onClick={(e) => { e.preventDefault(); setHlPath(p.i); setShowAll(true) }}>{p.steps.join(' → ') || '(바로 멈춤)'}</a></td>
                    <td>{p.score.toFixed(3)}</td><td>{p.all_implemented ? '모두 있음' : '없는 카드 포함'}</td><td>{p.result_kinds.join(', ') || '—'}</td>
                    <td className="small">{p.conditions.join(' · ') || '—'}</td><td className="small">{CONTROL_KO[p.ends_with] || p.ends_with}</td><td className="small">{p.runtime}</td>
                    <td className="small"><a href={`/api/plans/${planId}/paths/${p.leaf}/preview`} target="_blank" rel="noreferrer" title="이 순서대로 복사본에서 돌려 본 결과(기록 안 됨)">미리보기 ↗</a></td></tr>))}
              </tbody></table>
            </div>
          )
        })}
        {compare.length === 2 && (
          <div className="grid2" style={{ marginTop: '.6rem' }}>
            {compare.map((i) => { const p = d.paths[i]; return (
              <div key={i} className="card"><b>경로 #{p.rank}</b>
                <ol className="small">{p.steps.map((s: string, j: number) => <li key={j}>{s} · {codex ? '선택(1)/대안(0)' : '선택지 확률'} {fmtP(p.raw_probs[j])}</li>)}</ol>
                <p className="small">경로 추천 점수 {p.score.toFixed(3)} · {p.complete ? '완료 경로' : '부분 경로'} · {p.all_implemented ? '실행기 모두 있음' : '실행기 없는 카드 포함'}<br />결과: {p.result_kinds.join(', ') || '—'}<br />조건: {p.conditions.join(' · ') || '—'}</p>
              </div>) })}
          </div>
        )}
      </section>

      <section className="card small">
        <h2 style={{ marginTop: 0 }}>내려받기</h2>
        <div className="row">
          <a className="btn" href={`/api/plans/${planId}/export/roadmap.json`}>roadmap.json</a>
          <a className="btn" href={`/api/plans/${planId}/export/roadmap.html?download=1`}>roadmap.html</a>
          <a className="btn" href={`/api/plans/${planId}/export/roadmap.html`} target="_blank" rel="noreferrer">roadmap.html 열어 보기</a>
          <a className="btn" href={`/api/runs/${d.plan.run_id}/manifest`}>run_manifest.json</a>
          <Link to={`/runs/${d.plan.run_id}`} className="btn">실행 기록 · 결과 파일</Link>
        </div>
        <details style={{ marginTop: '.6rem' }}><summary>{codex ? 'OpenAI Codex로 보낸 필드(현재 상태 기준 형태)' : d.plan.provider === 'mock' ? '실제 판단을 켜면 외부로 보낼 필드 — 이 계획은 모의 판단이라 보내지 않았습니다' : `외부(${providerName})로 보낸 필드(현재 상태 기준 형태)`}</summary>
          <p className="dim">예시 행은 보내지 않습니다(D12). 셀 값은 직접 적은 업무 규칙(그룹 목록 · 성공 값)에 든 것만 갑니다. 열 이름 · 자료형 · 건수 같은 측정 요약과 후보 목록만 보냅니다.</p>
          <pre>{JSON.stringify(d.live_preview, null, 1)}</pre>
        </details>
        <p className="dim">{d.notes.slice(1).join(' ')} 카탈로그 {d.plan.versions?.catalog} · 정책 {d.plan.versions?.policy} · 질문 {d.plan.versions?.question}</p>
      </section>
    </>
  )
}
