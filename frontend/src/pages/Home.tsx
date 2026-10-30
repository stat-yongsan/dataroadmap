import { useEffect, useMemo, useState } from 'react'
import { api, navigate, PROVIDER_NAME } from '../api'

const KEYWORDS: [RegExp, string][] = [[/비율|률|퍼센트/, 'rate_by_group'], [/사람|인원|명수|고유/, 'distinct_entities'], [/월별|추이|변화/, 'monthly_trend'], [/합계|금액|총액/, 'sum_by_group'], [/건수|개수|몇 건/, 'count_by_group']]
const PARAM_KO: Record<string, string> = { group_col: '그룹 열', value_col: '값(금액) 열', entity_col: '대상(사람) 열', status_col: '상태 열', date_col: '날짜 열', success_values: '성공으로 셀 상태 값' }

export default function Home() {
  const [examples, setExamples] = useState<any[]>([])
  const [goals, setGoals] = useState<Record<string, any>>({})
  const [health, setHealth] = useState<any>(null)
  const [ds, setDs] = useState<string | null>(new URLSearchParams(location.search).get('ds'))
  const [data, setData] = useState<any>(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [goalKey, setGoalKey] = useState('')
  const [params, setParams] = useState<Record<string, any>>({})
  const [rules, setRules] = useState<Record<string, any>>({})
  const [desc, setDesc] = useState('')
  const [ingestOpt, setIngestOpt] = useState<Record<string, string>>({})
  const [provider, setProvider] = useState<'mock' | 'live' | 'codex' | 'openai'>('mock')
  const [liveOk, setLiveOk] = useState(false)
  const [livePrev, setLivePrev] = useState<{ goal_id: string, live_payload: any } | null>(null)
  // 목표 · 규칙을 바꾸면 미리 본 필드가 낡는다 → 다시 보고 다시 동의
  useEffect(() => { setLivePrev(null); setLiveOk(false) }, [ds, goalKey, params, rules, desc, provider])

  useEffect(() => {
    api('/api/examples').then(setExamples)
    api('/api/goals').then(setGoals)
    api('/api/health').then(h => { setHealth(h); if (h.codex_ready) setProvider('codex') })
  }, [])

  async function loadDataset(id: string, suggested?: any) {
    const d = await api(`/api/datasets/${id}`)
    setData(d)
    setDs(id)
    history.replaceState(null, '', `/?ds=${id}`)
    const sg = suggested || (d.suggested_goals[0] ? { goal_key: d.suggested_goals[0].goal_key, params: d.suggested_goals[0].params, rules: {} } : null)
    if (sg) {
      setGoalKey(sg.goal_key)
      setParams(sg.params || {})
      setRules(sg.rules || {})
    }
    const t = d.inspect?.table
    if (t?.sheet) setIngestOpt((o) => ({ sheet: t.sheet, ...o }))
  }
  useEffect(() => { if (ds && !data) loadDataset(ds).catch((e) => setErr(String(e.message))) }, []) // eslint-disable-line

  async function run(fn: () => Promise<void>) {
    setErr(''); setBusy(true)
    try { await fn() } catch (e: any) { setErr(e.message || String(e)) } finally { setBusy(false) }
  }

  const cols: string[] = data?.preview?.columns || []
  const required: string[] = goals[goalKey]?.required || []
  const table = data?.inspect?.table
  const enc = data?.inspect?.encoding

  function onDesc(v: string) {
    setDesc(v)
    const hit = KEYWORDS.find(([re]) => re.test(v))
    if (hit) setGoalKey(hit[1])
  }

  const ready = useMemo(() => goalKey && required.every((k) => params[k] && String(params[k]).length), [goalKey, required, params])

  return (
    <>
      <h1>데이터 활용 로드맵</h1>
      <p className="dim">코드가 파일의 구조와 품질을 확인하고, Codex 또는 OpenAI Decisions API가 허용된 다음 작업을 고릅니다. Python이 실행·검증한 뒤 실제로 바뀐 상태에서 다시 판단합니다. 모의 판단도 선택할 수 있습니다.</p>
      {err && <p className="err">{err}</p>}
      <div className="grid2">
        <section className="card">
          <h2 style={{ marginTop: 0 }}>1. 샘플 데이터 고르기</h2>
          {examples.map((ex) => (
            <div key={ex.key} className="row" style={{ justifyContent: 'space-between', borderTop: '1px solid var(--line)', padding: '.45rem 0' }}>
              <div style={{ flex: '1 1 240px' }}><b>{ex.title}</b><div className="dim small">{ex.desc}</div></div>
              <button disabled={busy} onClick={() => run(async () => { const r = await api(`/api/examples/${ex.key}`, { method: 'POST' }); await loadDataset(r.dataset_id, r.suggested) })}>불러오기</button>
            </div>
          ))}
        </section>
        <section className="card">
          <h2 style={{ marginTop: 0 }}>또는 CSV · XLSX 올리기</h2>
          <form onSubmit={(e) => { e.preventDefault(); const f = new FormData(e.currentTarget); run(async () => { const r = await api('/api/datasets', { form: f }); await loadDataset(r.dataset_id) }) }}>
            <div className="row">
              <input type="file" name="file" accept=".csv,.tsv,.txt,.xlsx" required />
              <label className="small">인코딩 <select name="encoding" defaultValue=""><option value="">자동 판별</option><option>utf-8</option><option>utf-8-sig</option><option>cp949</option><option>euc-kr</option></select></label>
              <button className="primary" disabled={busy}>올리기</button>
            </div>
            <p className="dim small">한도: 파일 20 MiB · 10만 행. 넘으면 잘라 읽지 않고 거절합니다. {health?.hosted ? '업로드 파일은 이 서비스의 서버에서 처리합니다.' : '파일은 이 PC에서 처리합니다.'} 실제 판단을 고르면 외부에는 측정 요약과 후보만 전송합니다. 실제 업무 파일 대신 가상자료를 사용하세요.</p>
          </form>
        </section>
      </div>

      {data && (
        <section className="card">
          <h2 style={{ marginTop: 0 }}>2. 파일 살펴보기 — {data.dataset.display_name}</h2>
          <p className="small dim">{data.dataset.kind.toUpperCase()} · {data.dataset.size.toLocaleString()} 바이트 · sha256 {data.dataset.sha256.slice(0, 12)}… · 데이터셋 {data.dataset.dataset_id}</p>
          <p>표 범위: {table?.status === 'confirmed' ? <span className="ok">확정 — {table.reason}</span> : <span className="err">미확정 — {table?.reason}</span>}</p>
          {table?.reasons?.length > 0 && <ul className="small">{table.reasons.map((r: string) => <li key={r}>{r}</li>)}</ul>}
          {enc && (
            <p className="small">인코딩: <b>{enc.encoding || '모름'}</b> ({enc.status === 'confirmed' ? '확정' : enc.status === 'estimated' ? '추정' : '모름'} — {enc.reason})
              {enc.status !== 'confirmed' && (
                <span className="row" style={{ marginTop: '.3rem' }}>
                  <select value={ingestOpt.encoding || ''} onChange={(e) => setIngestOpt({ ...ingestOpt, encoding: e.target.value })}>
                    <option value="">인코딩 고르기</option>{[enc.encoding, ...enc.choices].filter(Boolean).map((c: string) => <option key={c}>{c}</option>)}
                  </select>
                  <button disabled={busy || !ingestOpt.encoding} onClick={() => run(async () => { await api(`/api/datasets/${ds}/ingest`, { body: { encoding: ingestOpt.encoding } }); await loadDataset(ds!) })}>이 인코딩으로 다시 읽기</button>
                </span>
              )}
            </p>
          )}
          {data.dataset.kind === 'xlsx' && (
            <details open={table?.status !== 'confirmed'}>
              <summary>시트 · 머리글 후보 · 병합 · 수식 (머리글 후보는 위에서부터 30행만 본 표본 기반)</summary>
              <div className="scroll"><table><thead><tr><th>시트</th><th>상태</th><th>범위</th><th>병합</th><th>제목행</th><th>머리글 후보(행)</th><th>수식</th><th>숨김 행/열</th></tr></thead><tbody>
                {data.inspect.sheets.map((s: any) => (
                  <tr key={s.name}><td>{s.name}</td><td>{s.state}</td><td>{s.dimension}</td><td>{s.merged.join(', ') || '없음'}</td><td>{s.title_rows.join(', ') || '없음'}</td>
                    <td>{s.header_candidates.map((c: any) => `${c.row}행(${c.values.join('·')})`).join(' / ') || '없음'}{s.duplicate_header_rows.length > 0 && <div className="err small">같은 후보 {s.duplicate_header_rows.join(', ')}행 — 임의로 고르지 않음</div>}</td>
                    <td>{s.formulas}</td><td>{s.hidden_rows}/{s.hidden_columns}</td></tr>))}
              </tbody></table></div>
              <div className="row" style={{ marginTop: '.5rem' }}>
                <label className="small">시트 <input value={ingestOpt.sheet || ''} onChange={(e) => setIngestOpt({ ...ingestOpt, sheet: e.target.value })} size={8} /></label>
                <label className="small">머리글 행 <input type="number" min={1} value={ingestOpt.header_row || ''} onChange={(e) => setIngestOpt({ ...ingestOpt, header_row: e.target.value })} style={{ width: '5rem' }} /></label>
                <label className="small">또는 범위 <input placeholder="B3:D6" value={ingestOpt.range || ''} onChange={(e) => setIngestOpt({ ...ingestOpt, range: e.target.value })} size={8} /></label>
                <button disabled={busy || !(ingestOpt.header_row || ingestOpt.range)} onClick={() => run(async () => { await api(`/api/datasets/${ds}/ingest`, { body: ingestOpt }); await loadDataset(ds!) })}>이 범위로 읽기(A02)</button>
              </div>
              <p className="dim small">범위를 사람이 정하기 전에는 합계를 내지 않습니다. 머리글 자동 탐지(B01)는 실행기가 없습니다.</p>
            </details>
          )}
          {data.profile ? (
            <>
              <h3>열 측정값 — {data.profile.scope} · 읽은 행 {data.profile.rows_read.toLocaleString()} · 열 {data.profile.columns_read} <span className="badge">measured</span></h3>
              <div className="scroll"><table><thead><tr><th>열</th><th>자료형 후보</th><th>식별자</th><th>빈칸</th><th>null</th><th>0</th><th>고유값</th><th>메모</th></tr></thead><tbody>
                {data.profile.columns.map((c: any) => (
                  <tr key={c.name}><td><b>{c.name}</b></td><td>{c.kind}</td><td>{c.identifier ? '예' : ''}</td><td>{c.empty}</td><td>{c.null}</td><td>{c.zero}</td><td>{c.distinct}{c.all_unique ? ' (모두 다름)' : ''}</td>
                    <td className="small">{[c.identifier_reason?.join(' · '), c.needs_parse ? '문자 숫자 — 계산 전에 변환 필요' : '', c.identifier_damage_reason, c.formula_uncached ? `수식 ${c.formula_uncached}칸 · 재계산 안 됨` : ''].filter(Boolean).join(' / ')}</td></tr>))}
              </tbody></table></div>
              <details><summary>{data.preview.note}</summary>
                <div className="scroll"><table><thead><tr>{data.preview.columns.map((c: string) => <th key={c}>{c}</th>)}</tr></thead><tbody>
                  {data.preview.rows.map((r: any[], i: number) => <tr key={i}>{r.map((v, j) => <td key={j}>{v === null ? <i className="dim">null</i> : String(v)}</td>)}</tr>)}
                </tbody></table></div>
              </details>
            </>
          ) : <p className="dim">표를 아직 읽지 못해 열 측정값이 없습니다.</p>}
        </section>
      )}

      {data && (
        <section className="card">
          <h2 style={{ marginTop: 0 }}>3. 목적과 업무 규칙</h2>
          <div className="row small">
            제안된 목적: {data.suggested_goals.map((g: any) => (
              <button key={g.goal_key} onClick={() => { setGoalKey(g.goal_key); setParams({ ...g.params }) }}>{goals[g.goal_key]?.label || g.goal_key}</button>
            ))}
            {data.suggested_goals.length === 0 && <span className="dim">(표를 읽은 뒤 제안)</span>}
          </div>
          <p className="dim small">데이터가 받쳐 주는 활용 목적 몇 개일 뿐, 유일한 정답이 아닙니다. 목적이 다르면 계획도 따로 만듭니다.</p>
          <div className="row" style={{ marginTop: '.4rem' }}>
            <label>목표를 직접 적기 <input value={desc} onChange={(e) => onDesc(e.target.value)} placeholder="예: 부서별 신청 건수" size={28} /></label>
            <label>목적 <select value={goalKey} onChange={(e) => setGoalKey(e.target.value)}><option value="">고르기</option>
              {Object.entries(goals).map(([k, g]: any) => <option key={k} value={k}>{g.label}</option>)}</select></label>
          </div>
          <div className="row" style={{ marginTop: '.5rem' }}>
            {required.map((k) => (
              <label key={k}>{PARAM_KO[k] || k}{' '}
                {k === 'success_values'
                  ? <input value={(params[k] || []).join(',')} onChange={(e) => setParams({ ...params, [k]: e.target.value.split(',').map((x) => x.trim()).filter(Boolean) })} placeholder="인증" size={10} />
                  : cols.length ? <select value={params[k] || ''} onChange={(e) => setParams({ ...params, [k]: e.target.value })}><option value="">열 고르기</option>{cols.map((c) => <option key={c}>{c}</option>)}</select>
                    : <input value={params[k] || ''} onChange={(e) => setParams({ ...params, [k]: e.target.value })} size={10} />}
              </label>
            ))}
          </div>
          <h3>업무 규칙</h3>
          <div className="row">
            <label>한 행의 의미(grain) <input value={rules.grain || ''} onChange={(e) => setRules({ ...rules, grain: e.target.value })} placeholder="예: 신청 1건" size={12} /></label>
            <label>값 단위 <input value={rules.value_unit || ''} onChange={(e) => setRules({ ...rules, value_unit: e.target.value })} placeholder="원" size={4} /></label>
          </div>
          {cols.length > 0 && (
            <div className="row small" style={{ marginTop: '.4rem' }}>업무 키:
              {cols.map((c) => (
                <label key={c}><input type="checkbox" checked={(rules.key || []).includes(c)} onChange={(e) => setRules({ ...rules, key: e.target.checked ? [...(rules.key || []), c] : (rules.key || []).filter((x: string) => x !== c) })} />{c}</label>
              ))}
            </div>
          )}
          {params.group_col && (
            <div className="row small" style={{ marginTop: '.4rem' }}>
              <label>선언된 그룹 목록(선택 · 쉼표) <input value={(rules.declared_groups?.[params.group_col] || []).join(',')}
                onChange={(e) => setRules({ ...rules, declared_groups: { [params.group_col]: e.target.value.split(',').map((x) => x.trim()).filter(Boolean) } })} placeholder="교과,비교과,지원" /></label>
              <span className="dim">행이 없는 그룹도 표에 남기고, 관측 0 과 구분합니다.</span>
            </div>
          )}
          <p className="small dim">값 해석 규칙: {rules.amount_syntax?.desc || '기본 — 쉼표 · 괄호 음수 · % · 원 접미사'} · 한 행의 의미가 비어 있으면 「정보 필요」 후보가 표시될 수 있습니다.</p>
          <div className="row" style={{ marginTop: '.6rem' }}>
            <label className="small">판단 <select value={provider} onChange={(e) => setProvider(e.target.value as 'mock' | 'live' | 'codex' | 'openai')}>
              <option value="codex" disabled={!health?.codex_ready}>Codex 실제 판단 · {health?.codex_model || '기본 모델'}{health?.codex_ready ? '' : ' · 연결 꺼짐'}</option>
              <option value="mock">모의 판단(MOCK · policy.v1)</option>
              <option value="openai" disabled={!health?.openai_key_present}>OpenAI Decisions API · {health?.openai_model || 'gpt-6-luna'}{health?.openai_key_present ? '' : ' · 키 없음'}</option>
              <option value="live" disabled={!health?.live_key_present}>LIVE — TypeSafe Jev({health?.jev_model_default || 'jev-latest'}){health?.live_key_present ? '' : ' · 키 없음'}</option></select></label>
            <button className="primary" disabled={busy || !ready || (provider !== 'mock' && !(liveOk && livePrev))} onClick={() => run(async () => {
              const r = await api(`/api/datasets/${ds}/goals`, { body: { goal_key: goalKey, params, rules, description: desc, provider, goal_id: provider !== 'mock' ? livePrev?.goal_id : undefined, req_id: crypto.randomUUID() } })
              navigate(`/roadmaps/${r.plan_id}`)
            })}>{busy ? (provider === 'mock' ? '처리 중…' : `${PROVIDER_NAME[provider]}에 묻는 중…`) : '활용 로드맵 만들기'}</button>
            {!ready && goalKey && <span className="dim small">목적 인자를 채우세요</span>}
            {ready && provider !== 'mock' && !(liveOk && livePrev) && <span className="dim small">{livePrev ? '아래 동의에 체크하면 켜집니다' : '아래 「보낼 필드 먼저 보기」를 눌러야 켜집니다'}</span>}
          </div>
          {provider !== 'mock' && (
            <div className="card small" style={{ marginTop: '.5rem' }}>
              <p style={{ marginTop: 0 }}>이 표의 <b>측정 요약</b>(열 이름 · 자료형 · 건수 · 빈칸/중복 수 · 업무 규칙)과 <b>후보 작업 목록</b>을 {PROVIDER_NAME[provider]}로 보냅니다. 예시 행은 보내지 않습니다(셀 값은 직접 적은 그룹 목록 · 성공 값만 갑니다).
                계획 하나에 최대 {provider === 'codex' ? 1 : health?.search?.max_live_calls_per_plan ?? 10}회 호출 · 사용량(토큰)은 계획 화면과 실행 기록에 남습니다. 실패하면 실패로 남고 모의 판단으로 바꾸지 않습니다.</p>
              {!livePrev
                ? <button disabled={busy || !ready} onClick={() => run(async () => {
                    setLivePrev(await api(`/api/datasets/${ds}/goals`, { body: { goal_key: goalKey, params, rules, description: desc, preview_only: true } }))
                  })}>보낼 필드 먼저 보기(호출 안 함)</button>
                : <>
                    <details open><summary>첫 호출에 보낼 필드(현재 상태) — 다음 단계 호출도 같은 형태입니다</summary><pre>{JSON.stringify(livePrev.live_payload, null, 1)}</pre></details>
                    <label><input type="checkbox" checked={liveOk} onChange={(e) => setLiveOk(e.target.checked)} /> 위 필드를 외부({PROVIDER_NAME[provider]})로 보내는 데 동의합니다</label>
                  </>}
            </div>
          )}
        </section>
      )}
    </>
  )
}
