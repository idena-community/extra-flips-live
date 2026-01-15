<script setup>
const timestamp = useState('scanner-ts', () => Date.now())

const { data, pending, error, refresh } = await useFetch('/api/scan', {
  lazy: true,
  query: { t: timestamp },
  headers: { 'Cache-Control': 'no-cache' }
})

const refreshData = async () => {
  timestamp.value = Date.now()
  await refresh()
}

const formatDate = (dateString) => {
  if (!dateString) return ''
  return new Date().toLocaleTimeString()
}
</script>

<template>
  <div class="scanner-wrapper">
    <div class="scanner-container">
      
      <header class="header">
        <h1>🔍 Extra Flips Live</h1>
        <p class="subtitle">Idena Blockchain Monitor</p>
      </header>

      <div v-if="pending" class="state-box loading">
        <div class="spinner"></div>
        <p>Scanning blockchain data...</p>
      </div>

      <div v-else-if="error" class="state-box error">
        <h3>Network Error</h3>
        <p>{{ error.message }}</p>
        <button @click="refreshData" class="btn btn-retry">Retry</button>
      </div>

      <div v-else-if="data && !data.success" class="state-box error">
        <h3>Script Error</h3>
        <p>{{ data.error }}</p>
        <button @click="refreshData" class="btn btn-retry">Retry</button>
      </div>

      <div v-else-if="data && data.success" class="dashboard">
        
        <div class="main-card">
          <div class="epoch-badge">Epoch {{ data.data.epoch }}</div>
          
          <div class="grid-stats">
            <div class="stat-box warning">
              <span class="stat-label">Authors > Threshold ({{ data.data.threshold }})</span>
              <span class="stat-value">{{ data.data.counts.authorsOverThreshold }}</span>
            </div>

            <div class="stat-box danger">
              <span class="stat-label">Total Extra Flips</span>
              <span class="stat-value">{{ data.data.counts.totalExtraFlips }}</span>
            </div>

            <div class="stat-box info">
              <span class="stat-label">Flips Scanned</span>
              <span class="stat-value">{{ data.data.counts.flipsSeen }}</span>
            </div>
          </div>

          <div class="footer-info">
            <p>{{ data.data.note }}</p>
            <p class="timestamp">Last updated: {{ formatDate(data.data.timestamp) }}</p>
          </div>
        </div>

        <button @click="refreshData" class="btn btn-refresh">
          🔄 Refresh Data
        </button>

      </div>
    </div>
  </div>
</template>

<style>
body { margin: 0; padding: 0; background-color: #f8fafc; }
</style>

<style scoped>
.scanner-wrapper {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  padding: 40px 20px;
  min-height: 100vh;
  color: #334155;
}
.scanner-container { max-width: 800px; margin: 0 auto; }
.header { text-align: center; margin-bottom: 30px; }
.header h1 { font-size: 2.5rem; margin-bottom: 5px; color: #1e293b; }
.subtitle { color: #64748b; font-size: 1.1rem; }
.main-card { background: white; border-radius: 16px; padding: 30px; box-shadow: 0 10px 25px -5px rgba(0,0,0,0.1); position: relative; overflow: hidden; }
.epoch-badge { position: absolute; top: 0; right: 0; background: #3b82f6; color: white; padding: 8px 16px; border-bottom-left-radius: 16px; font-weight: bold; }
.grid-stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-top: 20px; }
.stat-box { padding: 20px; border-radius: 12px; display: flex; flex-direction: column; align-items: center; text-align: center; }
.stat-box.warning { background-color: #fff7ed; border: 1px solid #ffedd5; color: #9a3412; }
.stat-box.danger { background-color: #fef2f2; border: 1px solid #fee2e2; color: #991b1b; }
.stat-box.info { background-color: #eff6ff; border: 1px solid #dbeafe; color: #1e40af; }
.stat-label { font-size: 0.85rem; text-transform: uppercase; margin-bottom: 8px; opacity: 0.8; }
.stat-value { font-size: 2.5rem; font-weight: 800; line-height: 1; }
.footer-info { margin-top: 30px; padding-top: 20px; border-top: 1px solid #e2e8f0; text-align: center; font-size: 0.9rem; color: #94a3b8; }
.btn { display: block; width: 100%; padding: 15px; margin-top: 20px; border: none; border-radius: 12px; font-size: 1rem; font-weight: 600; cursor: pointer; }
.btn-refresh { background-color: #0f172a; color: white; }
.btn-retry { background-color: #ef4444; color: white; }
.spinner { width: 40px; height: 40px; border: 4px solid #e2e8f0; border-top-color: #3b82f6; border-radius: 50%; animation: spin 1s linear infinite; margin: 0 auto 15px; }
.state-box { text-align: center; padding: 40px; }
.error h3 { color: #991b1b; margin-bottom: 5px; }
.error p { color: #7f1d1d; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>