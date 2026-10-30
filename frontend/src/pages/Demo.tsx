import { useEffect, useState } from 'react'
import { api, Link } from '../api'

const CHECKS: Record<string, string> = {
  text_table_parsed: 'CSV 행과 인코딩 확인', identifier_preserved: '거래번호의 앞자리 0 보존',
  identifiers_preserved: '거래번호의 앞자리 0 보존', schema_matches: '필수 열과 자료형 확인',
  schema: '필수 열과 자료형 확인', schema_check: '필수 열과 자료형 확인', duplicate_keys: '거래번호 중복 확인', key_duplicates: '거래번호 중복 확인',
  numeric_parse: '문자 금액을 숫자로 변환', parse_errors: '금액 변환 오류 확인',
  rows_preserved: '집계에 모든 거래 포함', sum_invariant: '집계 전후 합계 일치',
}
const COLUMNS: Record<string, string> = { count: '거래 건수', 'sum_금액': '지출 합계(원)' }

function Table({ table }: { table: any }) {
  if (!table) return <p className="dim">이 단계는 표를 바꾸지 않고 검사 결과를 남깁니다.</p>
  const columns = table.columns.map((name: string, index: number) => ({ name, index })).filter((c: any) => c.name !== 'observed')
  return <div style={{ overflowX: 'auto' }}><table><thead><tr>{columns.map((c: any) => <th key={c.name}>{COLUMNS[c.name] || c.name}</th>)}</tr></thead>
    <tbody>{table.rows.map((row: any[], i: number) => <tr key={i}>{columns.map((c: any) => { const v = row[c.index]; return <td key={c.index}>{typeof v === 'number' ? v.toLocaleString('ko-KR') : String(v ?? '—')}</td> })}</tr>)}</tbody></table></div>
}

export default function Demo() {
  const [data, setData] = useState<any>(null)
  const [selected, setSelected] = useState(0)
  const [error, setError] = useState('')
  useEffect(() => { api('/api/demo').then(setData).catch(e => setError(e.message)) }, [])
  if (error) return <p className="err">{error}</p>
  if (!data) return <p role="status">검증한 예제를 불러오는 중…</p>
  const stage = data.stages[selected]
  return <>
    <p className="small dim">공개 예제 · 가상자료 · {data.provider === 'codex' ? '실제 Codex 판단 기록' : '모의 판단 기록'}</p>
    <h1>원자료에서 검증 가능한 결과까지</h1>
    <p>Codex가 다음 작업을 고르고, Python이 실행하고 검증합니다. 검증한 새 데이터 상태에서 다음 작업을 다시 판단합니다.</p>
    <section className="card">
      <h2>{data.title}</h2>
      <div className="row" style={{ gap: '1.5rem' }}><b>거래 {data.source.rows.toLocaleString()}건</b><b>부서 {data.source.groups}개</b>
        <b data-testid="demo-total">합계 {data.total.toLocaleString()}원</b><span className="ok">{data.verified ? '독립 정답과 일치' : '검증 필요'}</span></div>
      <p className="dim small">‘98,300원’처럼 문자로 저장된 금액을 숫자로 바꾸고, 거래번호를 보존하며 부서별 합계를 구합니다. 고정 정답: {data.expected_total.toLocaleString()}원.</p>
    </section>
    <h2>단계를 눌러 처리 결과를 살펴보세요</h2>
    <div className="row" style={{ marginBottom: '1rem', alignItems: 'stretch' }}>{data.stages.map((s: any, i: number) =>
      <button key={i} aria-pressed={selected === i} className={selected === i ? 'primary' : ''} onClick={() => setSelected(i)}>
        {i + 1}. {s.id} · {s.title} ✓
      </button>)}</div>
    <section className="card" data-testid="demo-stage">
      <h3>{stage.id} · {stage.title}</h3>
      {stage.checks.map((c: any, i: number) => <details className="small" key={i}><summary><span className={c.status === 'passed' ? 'ok' : 'dim'}>{c.status === 'passed' ? '✓' : '·'}</span> {CHECKS[c.name] || c.name}</summary><pre>{JSON.stringify(c.detail, null, 2)}</pre></details>)}
      <Table table={stage.preview} />
      <p className="dim small">실제로 실행한 단계의 결과입니다. 상세 표는 앞 10행을 보여 줍니다.</p>
    </section>
    <div className="grid2">
      <section className="card"><h2>최종 집계표</h2><Table table={data.result} /></section>
      <section className="card"><h2>Codex 판단과 검증 기록</h2>
        <p className="small">판단: <b>{data.provider === 'codex' ? `OpenAI Codex · ${data.model}` : '로컬 모의 규칙'}</b></p>
        <ol>{data.decisions.map((d: any, i: number) => <li key={i}><b>{d.choice}</b> · {d.reason}<div className="small dim">응답 {(d.latency_ms / 1000).toFixed(1)}초</div></li>)}</ol>
        <p className="dim small">검증 기록: {new Date(data.generated_at).toLocaleString('ko-KR')} · 원본과 단계별 결과를 구분해 보존합니다.</p>
      </section>
    </div>
    <details className="card"><summary>만든 방법과 공개 예제의 범위</summary>
      <p>기존 로컬 프로토타입을 바탕으로 Codex가 실제 판단 연결, 실행 결과 재검증, 공개 예제와 관리자 접근 분리, 웹 배포를 구현했습니다.</p>
      <p>계산·사전조건·결과 검증은 등록된 Python 실행기가 담당합니다. Codex는 허용 후보에서 한 작업을 선택하며, 선택 표시는 성공확률이 아닙니다.</p>
      <p>{data.note}</p><p>자신의 가상 파일을 올려 새 경로를 만드는 기능은 관리자 로그인이 필요합니다.</p>
    </details>
    <p className="small"><Link to="/admin">관리자 로그인 →</Link></p>
  </>
}

export function AdminLogin() {
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  return <section className="card" style={{ maxWidth: 460, margin: '2rem auto' }}>
    <h1>관리자 로그인</h1><p>새 파일 업로드와 실제 Codex 판단은 관리자만 사용할 수 있습니다.</p>
    <form onSubmit={async e => { e.preventDefault(); setBusy(true); setError(''); try {
      await api('/api/auth/login', { body: { password } }); location.href = '/admin'
    } catch (e: any) { setError(e.message) } finally { setBusy(false) } }}>
      <label>관리자 비밀번호 <input type="password" autoComplete="current-password" required value={password} onChange={e => setPassword(e.target.value)} /></label>
      <p><button className="primary" disabled={busy}>{busy ? '확인 중…' : '로그인'}</button></p>
      {error && <p className="err">{error}</p>}
    </form><Link to="/">공개 예제로 돌아가기</Link>
  </section>
}
