import { useEffect, useState } from 'react'
import { api, Link, PROVIDER_NAME } from './api'
import Home from './pages/Home'
import Roadmap from './pages/Roadmap'
import Run from './pages/Run'
import Catalog from './pages/Catalog'
import Learn from './pages/Learn'
import Race from './pages/Race'
import Demo, { AdminLogin } from './pages/Demo'

function usePath() {
  const [path, setPath] = useState(location.pathname)
  useEffect(() => {
    const on = () => setPath(location.pathname)
    window.addEventListener('popstate', on)
    return () => window.removeEventListener('popstate', on)
  }, [])
  return path
}

export default function App() {
  const path = usePath()
  const [health, setHealth] = useState<any>(null)
  const [planMode, setPlanMode] = useState<{ provider: string, model?: string } | null>(null)
  useEffect(() => { api('/api/health').then(setHealth).catch(() => setHealth({ error: true })) }, [])
  const liveBand = path.startsWith('/roadmaps/') && !!planMode && planMode.provider !== 'mock'
  if (!health) return <main><p role="status">연결 확인 중…</p></main>
  if (health.hosted && (!health.admin || path === '/demo')) return <>
    <header className="nav"><Link to="/" className="brand">데이터 활용 로드맵</Link><Link to="/admin">관리자</Link></header>
    <main>{path === '/admin' && !health.admin ? <AdminLogin /> : <Demo />}</main>
  </>
  let page: React.ReactNode
  let m: RegExpMatchArray | null
  if ((m = path.match(/^\/roadmaps\/([\w-]+)/))) page = <Roadmap planId={m[1]} key={m[1]} onMode={setPlanMode} />
  else if ((m = path.match(/^\/race\/([\w-]+)/))) page = <Race planId={m[1]} key={m[1]} />
  else if ((m = path.match(/^\/runs\/([\w-]+)/))) page = <Run runId={m[1]} />
  else if (path.startsWith('/catalog')) page = <Catalog />
  else if (path.startsWith('/learn')) page = <Learn />
  else page = <Home />
  const on = (p: string) => (p === '/' ? path === '/' : path.startsWith(p)) ? 'on' : ''
  return (
    <>
      <div className={'band' + (liveBand ? ' band-live' : '')} role="status">
        {path.startsWith('/race/')
          ? <span>비교 실험 — Opus 5.5 · Jev 실제 호출(외부 전송) · 결과는 계획에 쓰지 않음</span>
          : liveBand
          ? <span>{planMode?.provider === 'codex' ? `Codex 실제 판단 · ${planMode?.model || health?.codex_model} — 1은 선택, 0은 대안이며 성공확률이 아닙니다` : `LIVE 판단(${PROVIDER_NAME[planMode?.provider || ''] || planMode?.provider} · ${planMode?.model || '모델 미상'}) — 외부 판단 응답`}</span>
          : health.codex_ready && (path === '/' || path === '/admin')
          ? <span>판단 대기 — 전송 내용을 확인하고 동의하면 Codex로 경로를 만듭니다.</span>
          : <span>모의 판단(MOCK) — 명시한 로컬 규칙이며 실제 Jev 판단이 아닙니다</span>}
        <span className="live">
          {health?.codex_ready ? `Codex 연결 준비 · ${health.codex_model}` : health?.openai_key_present ? `OpenAI 연결 준비 · ${health.openai_model}` : health?.live_key_present ? `키 있음 · 모델 ${health.jev_model_default}` : '키 없음 — 꺼짐'}
        </span>
      </div>
      <header className="nav">
        <span className="brand">데이터 활용 로드맵</span>
        <Link to="/" className={on('/')}>시작</Link>
        <Link to="/catalog" className={on('/catalog')}>카탈로그</Link>
        <Link to="/learn" className={on('/learn')}>배우기</Link>
        <a href="/devplan">개발계획</a>
        {health.hosted && <><Link to="/demo">공개 예제</Link><button onClick={async () => { await api('/api/auth/logout', { body: {} }); location.href = '/' }}>로그아웃</button></>}
        {health?.error && <span className="err small">서버에 연결하지 못했습니다</span>}
      </header>
      <main>{page}</main>
    </>
  )
}
