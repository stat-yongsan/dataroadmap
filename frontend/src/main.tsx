import React, { useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './style.css'

type Profile = { columns: string[]; row_count: number; numeric_columns: string[]; preview: string[][] }
type Plan = { goal: string; group_col: string; value_col: string | null; row_count: number; steps: string[]; status: string }
type Result = { plan: Plan; rows: { group: string; value: string }[]; total: string; verified: boolean; check: string }
type Catalogue = { areas: Record<string, number>; area_names: Record<string, string>; projects: { project_id: string; area_id: string; title: string }[] }
type RaceInfo = { codex_installed: boolean; jev_key_present: boolean; codex_model: string; jev_model: string }
type RaceLane = { status: string; elapsed_ms: number; choice?: string; model?: string; error?: string }
type RaceResult = { gpt: RaceLane; jev: RaceLane }

async function post<T>(path: string, file: File, fields: Record<string, string> = {}): Promise<T> {
  const form = new FormData()
  form.append('file', file)
  Object.entries(fields).forEach(([key, value]) => form.append(key, value))
  const response = await fetch(path, { method: 'POST', body: form, ...(path === '/api/race' ? {headers: {'X-Data-Roadmap': '1'}} : {}) })
  if (!response.ok) { const body = await response.json(); throw new Error(body.detail || '요청에 실패했습니다.') }
  return response.json()
}

function App() {
  const [catalogue, setCatalogue] = useState<Catalogue | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [data, setData] = useState<Profile | null>(null)
  const [goal, setGoal] = useState('sum')
  const [group, setGroup] = useState('')
  const [value, setValue] = useState('')
  const [plan, setPlan] = useState<Plan | null>(null)
  const [result, setResult] = useState<Result | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [area, setArea] = useState('A')
  const [raceInfo, setRaceInfo] = useState<RaceInfo | null>(null)
  const [raceOpen, setRaceOpen] = useState(false)
  const [raceConsent, setRaceConsent] = useState(false)
  const [raceResult, setRaceResult] = useState<RaceResult | null>(null)

  useEffect(() => { fetch('/api/catalog').then(r => r.json()).then(setCatalogue).catch(() => setError('카탈로그를 불러오지 못했습니다.')); fetch('/api/race/availability').then(r => r.json()).then(setRaceInfo).catch(() => setRaceInfo(null)) }, [])
  function clearPlan() { setPlan(null); setResult(null); setRaceResult(null); setRaceConsent(false); setRaceOpen(false); setError('') }
  async function loadFile(next: File) {
    setBusy(true); setError(''); setData(null); setFile(null); clearPlan()
    try {
      const p = await post<Profile>('/api/profile', next)
      setFile(next); setData(p)
      setGroup(p.columns.includes('부서') ? '부서' : p.columns[0] || '')
      setValue(p.numeric_columns.includes('금액') ? '금액' : p.numeric_columns.find(c => c !== p.columns[0]) || '')
    } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }
  async function loadSample() {
    setBusy(true); setError('')
    try { const r = await fetch('/api/sample'); if (!r.ok) throw new Error('예제를 불러오지 못했습니다.'); await loadFile(new File([await r.blob()], 'sample.csv', {type:'text/csv'})) }
    catch (e) { setError((e as Error).message); setBusy(false) }
  }
  async function makePlan() {
    if (!file) return
    setBusy(true); setError(''); setResult(null)
    try { setPlan(await post<Plan>('/api/plan', file, {goal, group_col: group, value_col: value})) }
    catch (e) { setPlan(null); setError((e as Error).message) } finally { setBusy(false) }
  }
  async function runPlan() {
    if (!file || !plan) return
    setBusy(true); setError('')
    try { setResult(await post<Result>('/api/run', file, {goal, group_col: group, value_col: value})) }
    catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }
  async function runRace() {
    if (!file || !plan || !raceConsent) return
    setBusy(true); setError(''); setRaceResult(null)
    try { setRaceResult(await post<RaceResult>('/api/race', file, {goal, group_col: group, value_col: value, consent: 'true'})) }
    catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }
  const n = (x: string) => Number.isSafeInteger(Number(x)) ? Number(x).toLocaleString('ko-KR') : x

  return <div className="shell">
    <header className="top"><a className="brand" href="#top"><span className="brand-mark">↗</span> DATA ROADMAP</a><span className="top-note">CODEX PROTOTYPE <i /> 01</span><a className="top-link" href="#catalogue">작업 카탈로그 ↓</a></header>
    <main id="top">
      <section className="hero"><div><p className="eyebrow"><span /> DATA → DECISION → RESULT</p><h1>데이터에서<br/><em>가능성을 발견하세요.</em></h1><p className="intro">흩어진 표를 이해하고, 목적에 맞는 분석 경로를 만들고, 결과를 직접 검증합니다.</p><div className="hero-actions"><button className="primary" onClick={loadSample} disabled={busy}>가상 예제 시작하기 <span>↗</span></button><a href="#workspace">직접 파일 선택 ↓</a></div></div><div className="hero-aside"><div><b>17</b><span>작업 영역</span></div><div><b>153</b><span>작업 카드</span></div><div><b>02</b><span>실행 가능한 목표</span></div><p>Astra로 정리한 작업 카탈로그를 바탕으로 Codex가 새로 만든 프로토타입입니다.</p></div></section>
      <div className="context-bar"><span><b>01</b> 자료 확인</span><span><b>02</b> 목표 설정</span><span><b>03</b> 경로 검토</span><span><b>04</b> 결과 검증</span></div>
      <section id="workspace" className="workspace"><div className="section-head"><div><p className="eyebrow">YOUR WORKSPACE</p><h2>분석을 시작해 볼까요?</h2><p>가상 CSV 파일을 선택하고 결과를 확인하세요.</p></div><span className="badge">CSV는 앱에서 처리 · 모델 비교는 별도 동의</span></div>
        <div className="grid"><div className="panel"><div className="panel-title"><span className="step">01</span><div><h3>데이터 선택</h3><p>UTF-8 CSV · 최대 2MB</p></div></div><label className="upload"><strong>파일을 선택하세요</strong><span>가상 CSV 파일만 사용해 주세요.</span><input type="file" accept=".csv,text/csv" onChange={e => e.target.files?.[0] && loadFile(e.target.files[0])}/></label>{data && <div className="file-meta"><span className="dot"/> {file?.name} <b>{data.row_count.toLocaleString()}행 · {data.columns.length}열</b></div>}{data && <div className="preview"><div className="overline">데이터 미리보기 · 처음 5행</div><div className="scroll"><table><thead><tr>{data.columns.map(c => <th key={c}>{c}</th>)}</tr></thead><tbody>{data.preview.map((row, i) => <tr key={i}>{row.map((cell, j) => <td key={j}>{cell}</td>)}</tr>)}</tbody></table></div></div>}</div>
        <div className="panel"><div className="panel-title"><span className="step">02</span><div><h3>무엇을 알고 싶나요?</h3><p>목표와 데이터 열을 선택합니다.</p></div></div><div className="goal-options"><button className={goal === 'sum' ? 'goal active' : 'goal'} onClick={() => { setGoal('sum'); clearPlan() }}><b>그룹별 합계</b><small>부서별 지출 합계처럼</small></button><button className={goal === 'count' ? 'goal active' : 'goal'} onClick={() => { setGoal('count'); clearPlan() }}><b>그룹별 건수</b><small>유형별 신청 건수처럼</small></button></div><div className="fields"><label>그룹 열<select value={group} disabled={!data} onChange={e => {setGroup(e.target.value);clearPlan()}}><option value="">선택하세요</option>{data?.columns.map(c => <option key={c}>{c}</option>)}</select></label>{goal === 'sum' && <label>금액 열<select value={value} disabled={!data} onChange={e => {setValue(e.target.value);clearPlan()}}><option value="">선택하세요</option>{data?.numeric_columns.map(c => <option key={c}>{c}</option>)}</select></label>}</div><button className="outline" disabled={!data || busy || !group || (goal === 'sum' && !value)} onClick={makePlan}>분석 경로 만들기 <span>→</span></button><p className="helper">계획을 먼저 확인합니다. 이 버튼은 계산을 실행하지 않습니다.</p></div></div>
        {error && <p className="error" role="alert">{error}</p>}
        {plan && <section className="plan panel"><div className="panel-title"><span className="step">03</span><div><h3>제안된 분석 경로</h3><p>아직 실행하지 않은 계획입니다.</p></div></div><div className="path">{plan.steps.map((s, i) => <React.Fragment key={s}><div className="path-step"><span>{String(i+1).padStart(2,'0')}</span><b>{s}</b></div>{i < plan.steps.length-1 && <span className="path-arrow">→</span>}</React.Fragment>)}</div><div className="plan-bottom"><p>{plan.row_count.toLocaleString()}행 · {plan.group_col} 기준{plan.value_col ? ` · ${plan.value_col} 계산` : ''}</p><button className="primary" disabled={busy} onClick={runPlan}>경로 실행하고 검증하기 ↗</button></div><div className="race-links"><button onClick={() => setRaceOpen(!raceOpen)}>GPT-6.1 Sol vs Jev 결정 속도 비교 →</button><a href="#workspace">← 데이터 · 목적 바꾸기</a></div></section>}
        {plan && data && raceOpen && <section className="panel race"><div className="result-head"><div><p className="eyebrow">DECISION COMPARISON</p><h3>GPT-6.1 Sol vs Jev</h3></div><span className="badge">1회 비교</span></div><p className="helper race-explainer">두 모델에 같은 질문을 보내 다음 작업 선택과 응답 시간을 비교합니다. 정답률 비교가 아닙니다. Codex CLI 시작 시간도 GPT 측 시간에 포함됩니다. 모델 선택은 계산에 사용되지 않습니다.</p><div className="race-preview"><b>보낼 필드</b><p>목표: {goal === 'sum' ? '그룹별 합계' : '그룹별 건수'} · 행 수: {data.row_count.toLocaleString()} · 그룹 열: {group}{goal === 'sum' ? ` · 금액 열: ${value}` : ''}</p><p>전체 열 이름: {data.columns.join(', ')} · 숫자 열: {data.numeric_columns.join(', ') || '없음'}</p><p>선택지: C03 금액 해석 · I01 그룹별 집계 · needs_info 정보 확인. 셀 값과 원본 파일은 전송하지 않습니다.</p></div>{!raceInfo?.codex_installed && <p className="error">Codex CLI 설치가 필요합니다. 실행 전 요청하신 계정의 로그인을 확인해 주세요.</p>}{raceInfo && !raceInfo.jev_key_present && <p className="error">Jev 키가 없습니다. .env의 TYPESAFE_API_KEY 설정 후 앱을 다시 켜 주세요.</p>}<label className="race-consent"><input type="checkbox" checked={raceConsent} onChange={e => setRaceConsent(e.target.checked)} /> 위 요약과 질문을 OpenAI Codex와 TypeSafe Jev에 보내는 데 동의합니다.</label><button className="primary" disabled={busy || !raceConsent || !raceInfo?.codex_installed || !raceInfo?.jev_key_present} onClick={runRace}>{busy ? '비교 중…' : '1회 비교 시작 →'}</button>{raceResult && <div className="race-result">{([['GPT-6.1 Sol', raceResult.gpt], ['Jev', raceResult.jev]] as [string, RaceLane][]).map(([title, lane]) => <div className="race-lane" key={title}><small>{title}</small>{lane.status === 'ok' ? <><strong>{lane.elapsed_ms.toLocaleString()} ms</strong><p>다음 작업 선택: {lane.choice} · 모델: {lane.model}</p></> : <p className="error">{lane.error}</p>}</div>)}</div>}</section>}
        {result && <section className="result panel"><div className="result-head"><div><p className="eyebrow">OBSERVED RESULT</p><h3>실행 결과</h3></div><span className={result.verified ? 'verified' : 'error'}>{result.verified ? '✓ 검증 통과' : '검증 실패'}</span></div><div className="result-summary"><span>{result.check}</span><strong>{n(result.total)}{goal === 'count' ? '건' : ''}</strong></div><div className="scroll"><table><thead><tr><th>{group}</th><th>{goal === 'sum' ? '합계' : '건수'}</th></tr></thead><tbody>{result.rows.map(r => <tr key={r.group}><td>{r.group}</td><td>{n(r.value)}</td></tr>)}</tbody></table></div><p className="helper">선택한 파일의 실제 처리 결과입니다. 입력 파일은 변경하지 않습니다.</p></section>}
      </section>
      <section id="catalogue" className="catalogue"><div className="section-head"><div><p className="eyebrow">THE BIGGER PICTURE</p><h2>하나의 표, 다양한 가능성</h2><p>Astra로 정리한 17개 작업 영역과 153개 작업을 살펴보세요. 이 프로토타입은 그룹별 합계와 건수를 실행합니다.</p></div></div><div className="catalogue-box"><div className="area-list" aria-label="작업 영역">{catalogue && Object.entries(catalogue.areas).map(([id,count]) => <button key={id} title={catalogue.area_names[id]} aria-label={`${id} ${catalogue.area_names[id]} ${count}개`} onClick={() => setArea(id)} className={area === id ? 'active' : ''}>{id} <small>{count}</small></button>)}</div><div className="cards"><div className="overline">{area} · {catalogue?.area_names[area]} · 작업 카드</div>{catalogue?.projects.filter(p => p.area_id === area).map(p => <div className="card-row" key={p.project_id}><span>{p.project_id}</span><b>{p.title}</b></div>)}</div></div></section>
    </main><footer><span>DATA ROADMAP <b>↗</b></span><span>A Codex-built prototype · synthetic data only</span></footer>
  </div>
}

createRoot(document.getElementById('root')!).render(<App />)
