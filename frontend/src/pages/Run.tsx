import { useEffect, useState } from 'react'
import { api, Badge } from '../api'

function TableView({ vid }: { vid: string }) {
  const [t, setT] = useState<any>(null)
  useEffect(() => { api(`/api/versions/${vid}`).then(setT) }, [vid])
  if (!t) return <p className="dim small">불러오는 중…</p>
  return (
    <div className="scroll">
      <p className="small dim">grain: {t.schema?.grain || '—'} · {t.shown}/{t.total_rows}행 표시</p>
      <table><thead><tr>{t.columns.map((c: string) => <th key={c}>{c}</th>)}</tr></thead><tbody>
        {t.rows.map((r: any[], i: number) => <tr key={i}>{r.map((v, j) => <td key={j}>{v === null ? <i className="dim">null</i> : String(v)}</td>)}</tr>)}
      </tbody></table>
    </div>
  )
}

export default function Run({ runId }: { runId: string }) {
  const [m, setM] = useState<any>(null)
  const [open, setOpen] = useState<string | null>(null)
  const [err, setErr] = useState('')
  useEffect(() => { api(`/api/runs/${runId}`).then(setM).catch((e) => setErr(e.message)) }, [runId])
  if (err) return <p className="err">{err}</p>
  if (!m) return <p className="dim">불러오는 중…</p>
  const arts = (sid: string) => m.artifacts.filter((a: any) => a.step_run_id === sid)
  return (
    <>
      <h1>실행 기록 <span className="dim small">{runId}</span></h1>
      <p className="small">데이터: <b>{m.dataset.display_name}</b> · sha256 {m.dataset.sha256.slice(0, 12)}… · {m.mode}
        {' '}· <a href={`/api/runs/${runId}/manifest`}>run_manifest.json 내려받기</a></p>
      <section className="card">
        <h2 style={{ marginTop: 0 }}>단계 실행</h2>
        <div className="scroll"><table className="wide"><thead><tr><th>#</th><th>작업</th><th>상태</th><th>방식</th><th>검증(check)</th><th>문제</th><th>결과 파일</th></tr></thead><tbody>
          {m.step_runs.map((s: any, i: number) => (
            <tr key={s.step_run_id}>
              <td>{i + 1}</td><td><b>{s.project_id}</b> {s.title}<div className="dim small">{s.handler_version} · 설정 {s.config_hash}</div></td>
              <td><Badge s={s.status} /></td><td className="small">{s.execution_mode}</td>
              <td className="small">{(s.checks || []).map((c: any, j: number) => <div key={j}>{c.status === 'passed' ? '✔' : '✘'} {c.name}</div>)}
                {(s.checks || []).length > 0 && <details><summary>세부</summary><pre>{JSON.stringify(s.checks, null, 1)}</pre></details>}</td>
              <td className="small err">{(s.issues || []).join(' / ')}</td>
              <td className="small">{arts(s.step_run_id).map((a: any) => (
                <div key={a.artifact_id}><a href={`/api/artifacts/${a.artifact_id}`} target="_blank" rel="noreferrer">{a.name}</a>
                  {' '}<a href={`/api/artifacts/${a.artifact_id}?download=1`} title="내려받기">⭳</a>{a.kind === 'chart' && <div><img src={`/api/artifacts/${a.artifact_id}`} alt={`${s.project_id} 차트`} style={{ maxWidth: 260, marginTop: 4 }} /></div>}</div>))}</td>
            </tr>))}
        </tbody></table></div>
      </section>
      <section className="card">
        <h2 style={{ marginTop: 0 }}>데이터 버전 <span className="dim small">— 원본은 그대로 두고 실행마다 새 버전</span></h2>
        <div className="scroll"><table><thead><tr><th>버전</th><th>역할</th><th>grain</th><th>부모</th><th>만든 단계</th><th></th></tr></thead><tbody>
          {m.versions.map((v: any) => (
            <tr key={v.version_id}><td><code>{v.version_id}</code></td><td>{v.role === 'detail' ? '상세 표' : `결과 표(${v.agg_kind})`}</td><td>{v.grain || '—'}</td>
              <td><code>{v.parent_version_id || '원본'}</code></td><td className="small">{m.step_runs.find((s: any) => s.step_run_id === v.created_by_step_run)?.project_id}</td>
              <td><button onClick={() => setOpen(open === v.version_id ? null : v.version_id)}>{open === v.version_id ? '닫기' : '표 보기'}</button></td></tr>))}
        </tbody></table></div>
        {open && <TableView vid={open} />}
      </section>
      <section className="card small">
        <h2 style={{ marginTop: 0 }}>판단 사용량</h2>
        <p>계획 {m.decisions.plans.length}개 · LIVE 호출 {m.decisions.live_calls}회 · 토큰 입력 {m.decisions.tokens.input_tokens} / 출력 {m.decisions.tokens.output_tokens} · {m.decisions.cost}</p>
        <p className="dim">CSV 내보내기 규칙: {m.csv_escape_policy}</p>
      </section>
    </>
  )
}
