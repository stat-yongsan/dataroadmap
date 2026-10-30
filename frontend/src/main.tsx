import React, { useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './style.css'

type Profile = { columns: string[]; row_count: number; numeric_columns: string[]; preview: string[][] }
type Assessment = { score: number; basis: string }
type Plan = { goal: string; group_col: string; value_col: string | null; row_count: number; steps: string[]; status: string; executable: boolean; assessments: Record<string, Assessment> }
type Result = { plan: Plan; rows: { group: string; value: string }[]; total: string; verified: boolean; check: string }
type Catalogue = { areas: Record<string, number>; area_names: Record<string, string>; projects: { project_id: string; area_id: string; title: string }[] }
type RaceInfo = { codex_installed: boolean; jev_key_present: boolean; codex_model: string; jev_model: string; review_required: boolean }
type RaceLane = { status: string; elapsed_ms: number; choice?: string; reason?: string; probabilities?: Record<string, number>; model?: string; error?: string }
type RaceResult = { gpt: RaceLane; jev: RaceLane }

function ResultChart({rows}: {rows: Result['rows']}) {
  const values = rows.map(r => Number(r.value))
  if (values.some(v => !Number.isFinite(v))) return <p className="helper">값이 너무 커 차트로 표시할 수 없습니다. 아래 표에서 정확한 값을 확인하세요.</p>
  const scale = values.reduce((max, v) => Math.max(max, Math.abs(v)), 0)
  return <div className="result-chart" aria-label="실제 집계 결과 막대그래프">{rows.map((r, i) => <div className="result-bar" key={r.group}>
    <span>{r.group}</span><div className="bar-track"><i className={values[i] < 0 ? 'negative' : ''} style={{width: `${scale ? Math.abs(values[i]) / scale * 100 : 0}%`}} /></div><b>{r.value}</b>
  </div>)}<p className="helper">막대 길이 = 각 값의 절댓값 ÷ 가장 큰 절댓값. 붉은 막대는 음수입니다.</p></div>
}

async function post<T>(path: string, file: File, fields: Record<string, string> = {}, reviewPassword = ''): Promise<T> {
  const form = new FormData()
  form.append('file', file)
  Object.entries(fields).forEach(([key, value]) => form.append(key, value))
  const response = await fetch(path, { method: 'POST', body: form, ...(path === '/api/race' ? {headers: {'X-Data-Roadmap': '1', 'X-Review-Password': reviewPassword}} : {}) })
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
  const [reviewPassword, setReviewPassword] = useState('')
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
    try { setRaceResult(await post<RaceResult>('/api/race', file, {goal, group_col: group, value_col: value, consent: 'true'}, reviewPassword)) }
    catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }
  const n = (x: string) => Number.isSafeInteger(Number(x)) ? Number(x).toLocaleString('ko-KR') : x

  return <div className="shell">
    <header className="top"><a className="brand" href="#top"><span className="brand-mark">↗</span> DATA ROADMAP</a><span className="top-note">CODEX PROTOTYPE <i /> 01</span><a className="top-link" href="#catalogue">작업 카탈로그 ↓</a></header>
    <main id="top">
      <section className="hero"><div><p className="eyebrow"><span /> DATA → DECISION → RESULT</p><h1>데이터에서<br/><em>가능성을 발견하세요.</em></h1><p className="intro">흩어진 표를 이해하고, 목적에 맞는 분석 경로를 만들고, 결과를 직접 검증합니다.</p><div className="hero-actions"><button className="primary" onClick={loadSample} disabled={busy}>가상 예제 시작하기 <span>↗</span></button><a href="#workspace">직접 파일 선택 ↓</a></div></div><div className="hero-aside"><div><b>17</b><span>작업 영역</span></div><div><b>153</b><span>작업 카드</span></div><div><b>02</b><span>실행 가능한 목표</span></div><p>Astra로 정리한 작업 카탈로그를 바탕으로 Codex가 새로 만든 프로토타입입니다.</p></div></section>
      <div className="context-bar"><span><b>01</b> 자료 확인</span><span><b>02</b> 목표 설정</span><span><b>03</b> 경로 검토</span><span><b>04</b> 결과 검증</span></div>
      <section id="workspace" className="workspace"><div className="section-head"><div><p className="eyebrow">YOUR WORKSPACE</p><h2>분석을 시작해 볼까요?</h2><p>가상 CSV 또는 Excel 파일을 선택하고 결과를 확인하세요.</p></div><span className="badge">파일은 앱에서 처리 · 모델 비교는 별도 동의</span></div>
        <div className="grid"><div className="panel"><div className="panel-title"><span className="step">01</span><div><h3>데이터 선택</h3><p>UTF-8 CSV / XLSX 첫 시트 · 최대 2MB</p></div></div><label className="upload"><strong>파일을 선택하세요</strong><span>가상 파일만 사용해 주세요. XLSX 수식은 값으로 저장해야 합니다.</span><input type="file" accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" onChange={e => e.target.files?.[0] && loadFile(e.target.files[0])}/></label>{data && <div className="file-meta"><span className="dot"/> {file?.name} <b>{data.row_count.toLocaleString()}행 · {data.columns.length}열</b></div>}{data && <div className="preview"><div className="overline">데이터 미리보기 · 처음 5행</div><div className="scroll"><table><thead><tr>{data.columns.map(c => <th key={c}>{c}</th>)}</tr></thead><tbody>{data.preview.map((row, i) => <tr key={i}>{row.map((cell, j) => <td key={j}>{cell}</td>)}</tr>)}</tbody></table></div></div>}</div>
        <div className="panel"><div className="panel-title"><span className="step">02</span><div><h3>무엇을 알고 싶나요?</h3><p>목표와 데이터 열을 선택합니다.</p></div></div><div className="goal-options"><button className={goal === 'sum' ? 'goal active' : 'goal'} onClick={() => { setGoal('sum'); clearPlan() }}><b>그룹별 합계</b><small>부서별 지출 합계처럼</small></button><button className={goal === 'count' ? 'goal active' : 'goal'} onClick={() => { setGoal('count'); clearPlan() }}><b>그룹별 건수</b><small>유형별 신청 건수처럼</small></button></div><div className="fields"><label>그룹 열<select value={group} disabled={!data} onChange={e => {setGroup(e.target.value);clearPlan()}}><option value="">선택하세요</option>{data?.columns.map(c => <option key={c}>{c}</option>)}</select></label>{goal === 'sum' && <label>금액 열<select value={value} disabled={!data} onChange={e => {setValue(e.target.value);clearPlan()}}><option value="">선택하세요</option>{data?.columns.filter(c => c !== group).map(c => <option key={c}>{c}</option>)}</select></label>}</div><button className="outline" disabled={!data || busy || !group || (goal === 'sum' && !value)} onClick={makePlan}>분석 경로 만들기 <span>→</span></button><p className="helper">계획을 먼저 확인합니다. 이 버튼은 계산을 실행하지 않습니다.</p></div></div>
        {error && <p className="error" role="alert">{error}</p>}
        {plan && <section className="plan panel"><div className="panel-title"><span className="step">03</span><div><h3>분석 절차 · 화면 3단계</h3><p>선택한 목표에 따른 고정 절차입니다. 순위 비교나 AI 추천이 아닙니다.</p></div></div><div className="path">{plan.steps.map((s, i) => <React.Fragment key={s}><div className="path-step"><span>{String(i+1).padStart(2,'0')}</span><b>{s}</b></div>{i < plan.steps.length-1 && <span className="path-arrow">→</span>}</React.Fragment>)}</div><div className="assessment-summary"><strong>데이터 확인 근거</strong><p>점수는 실제 데이터에서 통과한 확인 항목 또는 비어 있지 않은 값의 비율입니다. 성공 확률이나 AI 평가가 아닙니다.</p>{Object.entries(plan.assessments).map(([id, a]) => <div className="assessment-line" key={id}><b>{id} · {a.score}%</b><span>{a.basis}</span><div className="score-track"><i style={{width:`${a.score}%`}} /></div></div>)}{!plan.executable && <p className="error">필수 확인 항목이 충족되지 않아 실행할 수 없습니다. 원본을 확인하고 다시 선택하세요.</p>}</div><div className="plan-bottom"><p>{plan.row_count.toLocaleString()}행 · {plan.group_col} 기준{plan.value_col ? ` · ${plan.value_col} 계산` : ''}</p><button className="primary" disabled={busy || !plan.executable} onClick={runPlan}>경로 실행하고 검증하기 ↗</button></div><div className="race-links"><button onClick={() => setRaceOpen(!raceOpen)}>GPT-6.1 Sol vs Jev 결정 속도 비교 →</button><a href="#workspace">← 데이터 · 목적 바꾸기</a></div></section>}
        {plan && data && raceOpen && <section className="panel race"><div className="result-head"><div><p className="eyebrow">DECISION COMPARISON</p><h3>GPT-6.1 Sol vs Jev</h3></div><span className="badge">1회 비교</span></div><p className="helper race-explainer">두 모델에 같은 데이터 측정값과 질문을 보내 다음 영역과 응답 시간을 비교합니다. 정답률 비교가 아닙니다. Codex CLI 시작 시간도 GPT 측 시간에 포함됩니다. 모델 선택은 계산에 사용되지 않습니다.</p><div className="race-preview"><b>보낼 필드</b><p>목표: {goal === 'sum' ? '그룹별 합계' : '그룹별 건수'} · 행 수: {data.row_count.toLocaleString()} · 그룹 열: {group}{goal === 'sum' ? ` · 금액 열: ${value}` : ''}</p><p>전체 열 이름: {data.columns.join(', ')} · 숫자 열: {data.numeric_columns.join(', ') || '없음'}</p><p>측정한 확인 결과: {Object.entries(plan.assessments).map(([id,a]) => `${id} ${a.basis}`).join(" · ")}</p><p>선택지: A~Q 17개 작업 영역과 정보 필요. 측정한 입력 조건을 함께 보내며 셀 값과 원본 파일은 전송하지 않습니다.</p></div>{!raceInfo?.codex_installed && <p className="error">Codex CLI 설치가 필요합니다. 실행 전 요청하신 계정의 로그인을 확인해 주세요.</p>}{raceInfo && !raceInfo.jev_key_present && <p className="error">Jev 키가 없습니다. .env의 TYPESAFE_API_KEY 설정 후 앱을 다시 켜 주세요.</p>}<>{raceInfo?.review_required && <label className="review-password">심사위원 접근 암호<input type="password" autoComplete="off" value={reviewPassword} onChange={e => setReviewPassword(e.target.value)} /></label>}</><label className="race-consent"><input type="checkbox" checked={raceConsent} onChange={e => setRaceConsent(e.target.checked)} /> 위 요약과 질문을 OpenAI Codex와 TypeSafe Jev에 보내는 데 동의합니다.</label><button className="primary" disabled={busy || !raceConsent || !raceInfo?.codex_installed || !raceInfo?.jev_key_present || (!!raceInfo?.review_required && !reviewPassword)} onClick={runRace}>{busy ? '비교 중…' : '1회 비교 시작 →'}</button>{raceResult && <div className="race-result">{([['GPT-6.1 Sol', raceResult.gpt], ['Jev', raceResult.jev]] as [string, RaceLane][]).map(([title, lane]) => <div className="race-lane" key={title}><small>{title}</small>{lane.status === 'ok' ? <><strong>{lane.elapsed_ms.toLocaleString()} ms</strong><p>다음 영역: {lane.choice === "needs_info" ? "정보 필요" : `${lane.choice} · ${catalogue?.area_names[lane.choice || ""] || ""}`} · 모델: {lane.model}</p>{lane.reason && <p>모델이 제시한 이유: {lane.reason}</p>}</> : <p className="error">{lane.error}</p>}</div>)}</div>}{raceResult?.jev.status === "ok" && raceResult.jev.probabilities && <div className="probability-list"><h4>Jev가 반환한 영역별 선택 확률</h4><p className="helper">같은 질문의 후보 분포입니다. 성공 확률이나 Codex의 점수가 아닙니다. 영역을 누르면 아래 카탈로그가 바뀝니다.</p>{Object.entries(raceResult.jev.probabilities).sort((a,b) => b[1]-a[1]).map(([id,p]) => <button key={id} disabled={id === "needs_info"} onClick={() => {setArea(id); document.getElementById("catalogue")?.scrollIntoView()}}><span>{id === "needs_info" ? "정보 필요" : `${id} · ${catalogue?.area_names[id] || ""}`}</span><div className="score-track"><i style={{width:`${p*100}%`}} /></div><b>{(p*100).toFixed(1)}%</b></button>)}</div>}</section>}
        {result && <section className="result panel"><div className="result-head"><div><p className="eyebrow">OBSERVED RESULT</p><h3>실행 결과</h3></div><span className={result.verified ? 'verified' : 'error'}>{result.verified ? '✓ 검증 통과' : '검증 실패'}</span></div><div className="result-summary"><span>{result.check}</span><strong>{n(result.total)}{goal === 'count' ? '건' : ''}</strong></div><ResultChart rows={result.rows} /><div className="scroll"><table><thead><tr><th>{group}</th><th>{goal === 'sum' ? '합계' : '건수'}</th></tr></thead><tbody>{result.rows.map(r => <tr key={r.group}><td>{r.group}</td><td>{n(r.value)}</td></tr>)}</tbody></table></div><p className="helper">선택한 파일의 실제 처리 결과입니다. 입력 파일은 변경하지 않습니다.</p></section>}
      </section>
      <section id="catalogue" className="catalogue"><div className="section-head"><div><p className="eyebrow">THE BIGGER PICTURE</p><h2>하나의 표, 다양한 가능성</h2><p>Astra로 정리한 17개 작업 영역과 153개 작업을 살펴보세요. 이 프로토타입은 그룹별 합계와 건수를 실행합니다.</p></div></div><div className="catalogue-box"><div className="area-list" aria-label="작업 영역">{catalogue && Object.entries(catalogue.areas).map(([id,count]) => <button key={id} title={catalogue.area_names[id]} aria-label={`${id} ${catalogue.area_names[id]} ${count}개`} onClick={() => setArea(id)} className={area === id ? 'active' : ''}>{id} <small>{count}</small></button>)}</div><div className="cards"><div className="overline">{area} · {catalogue?.area_names[area]} · 작업 카드</div>{raceResult?.jev.probabilities && raceResult.jev.probabilities[area] !== undefined && <p className="area-model-score">Jev의 이 영역 선택 확률 <b>{(raceResult.jev.probabilities[area] * 100).toFixed(1)}%</b> · 모델 출력, 성공률 아님</p>}<p className="helper area-note">{plan ? `이 영역에서 평가한 작업 ${catalogue?.projects.filter(p => p.area_id === area && plan.assessments[p.project_id]).length || 0} / ${catalogue?.areas[area] || 0}개` : "데이터와 목표로 분석 절차를 만들면 평가 가능한 작업의 실제 측정값이 표시됩니다."} · 평가 전은 0점이 아닙니다.</p><div className="score-track coverage"><i style={{width: `${plan && catalogue?.areas[area] ? 100 * catalogue.projects.filter(p => p.area_id === area && plan.assessments[p.project_id]).length / catalogue.areas[area] : 0}%`}} /></div>{catalogue?.projects.filter(p => p.area_id === area).map(p => { const a = plan?.assessments[p.project_id]; return <div className="card-row" key={p.project_id}><span>{p.project_id}</span><div className="card-detail"><b>{p.title}</b>{a ? <><strong>{a.score}% · 측정값</strong><div className="score-track"><i style={{width:`${a.score}%`}} /></div><small>{a.basis}</small></> : <small>평가 전 · 이 프로토타입의 측정 기준 없음</small>}</div></div> })}</div></div></section>
    </main><footer><span>DATA ROADMAP <b>↗</b></span><span>A Codex-built prototype · synthetic data only</span></footer>
  </div>
}

createRoot(document.getElementById('root')!).render(<App />)
