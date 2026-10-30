import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// 개발 중에만 vite dev 서버를 쓰고 API 는 FastAPI(127.0.0.1:8765)로 넘긴다. 배포(실행)는 빌드 결과를 FastAPI 가 내보낸다.
const api = 'http://127.0.0.1:8765'
export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': api, '/devplan': api, '/requirements-source.md': api } },
})
