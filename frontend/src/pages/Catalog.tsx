import { useEffect, useMemo, useState } from 'react'
import { api, IMPL_KO } from '../api'

export default function Catalog() {
  const [c, setC] = useState<any>(null)
  const [area, setArea] = useState('')
  const [status, setStatus] = useState('')
  const [q, setQ] = useState('')
  const [sel, setSel] = useState<string | null>(null)
  const [card, setCard] = useState<any>(null)
  useEffect(() => { api('/api/catalog').then(setC) }, [])
  useEffect(() => { setCard(null); if (sel) api(`/api/catalog/${sel}`).then(setCard) }, [sel])
  const list = useMemo(() => (c?.projects || []).filter((p: any) => (!area || p.area_id === area) && (!status || p.implementation_status === status)
    && (!q || `${p.project_id} ${p.title}`.toLowerCase().includes(q.toLowerCase()))), [c, area, status, q])
  if (!c) return <p className="dim">불러오는 중…</p>
  const count = (s: string) => c.projects.filter((p: any) => p.implementation_status === s).length
  return (
    <>
      <h1>작업 카탈로그</h1>
      <p className="small dim">원문 플레이북에서 기계적으로 뽑은 {c.areas.length}개 영역 · {c.projects.length}개 카드 · W01~W20. 카드 번호와 제목은 원문 그대로입니다.
        카탈로그 {c.catalog_version} · 원문 sha256 {c.source.sha256.slice(0, 12)}…{c.source.sha256 === c.source.spec_sha256 ? '(명세 기준 해시와 같음)' : '(명세와 다른 새 원본)'} · 점검 {c.verify.ok ? '통과' : '문제 있음'}</p>
      <p className="small">실행기 있음 <b>{count('implemented')}</b> · 계획 카드(실행기 없음) <b>{count('planned')}</b> · 명세만 <b>{count('spec_only')}</b> — 153개를 전부 구현했다는 뜻이 아닙니다.</p>
      <div className="row small">
        <button className={area === '' ? 'primary' : ''} onClick={() => setArea('')}>전체</button>
        {c.areas.map((a: any) => <button key={a.id} className={area === a.id ? 'primary' : ''} onClick={() => setArea(a.id)} title={a.question}>{a.id} {a.name} ({a.declared_count})</button>)}
      </div>
      <div className="row" style={{ margin: '.5rem 0' }}>
        <input placeholder="번호 · 제목 검색" value={q} onChange={(e) => setQ(e.target.value)} />
        <select value={status} onChange={(e) => setStatus(e.target.value)}><option value="">구현 상태 전체</option>{Object.entries(IMPL_KO).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
        <span className="dim small">{list.length}개</span>
      </div>
      <div className="split catalog">
        <div className="card scroll" style={{ maxHeight: '70vh', overflowY: 'auto' }}>
          <table><thead><tr><th>번호</th><th>최소 실습</th><th>환경</th><th>구현</th></tr></thead><tbody>
            {list.map((p: any) => (
              <tr key={p.project_id} onClick={() => setSel(p.project_id)} style={{ cursor: 'pointer', background: sel === p.project_id ? 'var(--head)' : undefined }}>
                <td><b>{p.project_id}</b></td><td>{p.title}</td><td>{p.environment}</td>
                <td><span className={`badge ${p.implementation_status === 'implemented' ? 'st-ready' : p.implementation_status === 'planned' ? 'st-projected' : ''}`}>{IMPL_KO[p.implementation_status]}</span></td></tr>))}
          </tbody></table>
        </div>
        <aside className="card" style={{ maxHeight: '70vh', overflowY: 'auto' }}>
          {!card && <p className="dim">카드를 고르면 원문 필드와 구현 메타가 보입니다.</p>}
          {card && (
            <>
              <h3 style={{ marginTop: 0 }}>{card.source.project_id || card.source.workflow_id} · {card.source.title}</h3>
              {card.source.project_id && <>
                <p className="small dim">환경 {card.source.environment} — {card.source.environment_label} · 원문 {card.source.source_start_line}~{card.source.source_end_line}행</p>
                <p className="small"><b>입력 예제</b> {card.source.input_example}<br /><b>변환·출력 계약</b> {card.source.transformation_output_contract}<br />
                  <b>성공 기준</b> {card.source.success_criteria}<br /><b>실패·경계 실험</b> {card.source.failure_boundary_experiment}</p>
                <h3>구현 메타 <span className="dim small">(원문과 분리 · {card.impl.metadata_origin})</span></h3>
                <p className="small">{IMPL_KO[card.impl.implementation_status]}{card.impl.handler_id ? ` · 실행기 ${card.impl.handler_id} (${card.impl.handler_version})` : ''}{card.impl.why_not ? ` — ${card.impl.why_not}` : ''}</p>
                {card.impl.input_contract && <p className="small"><b>입력</b> {card.impl.input_contract}<br /><b>출력</b> {card.impl.output_contract}</p>}
                {card.impl.preconditions?.length > 0 && <p className="small">사전조건: {card.impl.preconditions.join(' · ')}<br />효과: {card.impl.effects?.join(' · ')}<br />필요 인자: {card.impl.required_parameters?.join(' · ') || '없음'}</p>}
              </>}
              <details><summary>원문 그대로</summary><pre style={{ whiteSpace: 'pre-wrap' }}>{card.card_md}</pre></details>
            </>
          )}
        </aside>
      </div>
      <section className="card">
        <h2 style={{ marginTop: 0 }}>조합 프로젝트 W01~W20 <span className="dim small">— 목적과 작업 조합의 예시 템플릿. 화살표 전체가 파일 하나의 전달 체인이라는 뜻이 아닙니다</span></h2>
        <div className="scroll"><table><thead><tr><th>번호</th><th>제목</th><th>언급된 카드</th><th>정답</th></tr></thead><tbody>
          {c.workflows.map((w: any) => (
            <tr key={w.workflow_id} onClick={() => setSel(w.workflow_id)} style={{ cursor: 'pointer' }}><td><b>{w.workflow_id}</b></td><td>{w.title}</td>
              <td className="small">{w.mentioned_projects.join(' · ')}</td><td className="small">{w.expected}</td></tr>))}
        </tbody></table></div>
      </section>
    </>
  )
}
