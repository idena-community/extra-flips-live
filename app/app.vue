<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

type IdentityRow = {
  rank: number
  address: string
  totalGradeScore: number
  flipCount: number
  avgGradeScore: number
  maxFlipGradeScore: number
  scanUrl: string
}

type FlipRow = {
  rank: number
  cid: string
  author: string
  authorRank?: number | null
  gradeScore: number
  status: string
  word1?: string
  word2?: string
  scanUrl: string
  authorScanUrl: string
}

type GradeLeaderboard = {
  epoch?: number
  topLimit?: number
  topFlipsLimit?: number
  excludedWrongWordsAuthorsCount?: number
  filters?: {
    status?: string[]
  }
  topIdentities?: IdentityRow[]
  identityLookup?: IdentityRow[]
  topFlips?: FlipRow[]
}

type ProgressPoint = {
  timestamp: string
  flipsSeen: number
  uniqueAuthors: number
}

type ProgressEpochSeries = {
  epoch: number
  points: ProgressPoint[]
}

type ProgressPayload = {
  cacheUsed?: boolean
  minRefreshSeconds?: number
  secondsUntilNextRefresh?: number
  nextRefreshAt?: string | null
  series?: {
    currentEpoch?: ProgressEpochSeries
    previousEpochs?: ProgressEpochSeries[]
  }
}

type ChartLine = {
  epoch: number
  path: string
  opacity: number
}

type ChartPoint = {
  elapsedSeconds: number
  value: number
}

const timestamp = useState<number>('scanner-ts', () => Date.now())

const { data, pending, error, refresh } = await useFetch('/api/scan', {
  lazy: true,
  query: computed(() => ({ t: timestamp.value })),
  headers: { 'Cache-Control': 'no-cache' }
})

const payload = computed<any>(() => data.value?.data ?? null)
const gradeLeaderboard = computed<GradeLeaderboard | null>(() => {
  const value = payload.value?.gradeLeaderboard
  return value && typeof value === 'object' ? (value as GradeLeaderboard) : null
})

const topIdentities = computed<IdentityRow[]>(() => {
  const value = gradeLeaderboard.value?.topIdentities
  return Array.isArray(value) ? value : []
})

const identityLookup = computed<IdentityRow[]>(() => {
  const value = gradeLeaderboard.value?.identityLookup
  if (Array.isArray(value) && value.length > 0) {
    return value
  }
  return topIdentities.value
})

const topFlips = computed<FlipRow[]>(() => {
  const value = gradeLeaderboard.value?.topFlips
  return Array.isArray(value) ? value : []
})

const progressPayload = computed<ProgressPayload | null>(() => {
  const value = payload.value?.progress
  return value && typeof value === 'object' ? (value as ProgressPayload) : null
})

const progressCurrentSeries = computed<ProgressEpochSeries | null>(() => {
  const value = progressPayload.value?.series?.currentEpoch
  if (!value || typeof value !== 'object') return null
  const epoch = typeof value.epoch === 'number' ? value.epoch : 0
  const points = Array.isArray(value.points)
    ? value.points
        .map((point: any) => {
          if (!point || typeof point !== 'object') return null
          const ts = point.timestamp
          if (typeof ts !== 'string') return null
          const flipsSeen = Number(point.flipsSeen ?? 0)
          const uniqueAuthors = Number(point.uniqueAuthors ?? 0)
          return {
            timestamp: ts,
            flipsSeen: Number.isFinite(flipsSeen) ? flipsSeen : 0,
            uniqueAuthors: Number.isFinite(uniqueAuthors) ? uniqueAuthors : 0
          } as ProgressPoint
        })
        .filter((point): point is ProgressPoint => Boolean(point))
    : []
  return { epoch, points }
})

const progressPreviousSeries = computed<ProgressEpochSeries[]>(() => {
  const rows = progressPayload.value?.series?.previousEpochs
  if (!Array.isArray(rows)) return []
  return rows
    .map((series: any) => {
      if (!series || typeof series !== 'object') return null
      const epoch = Number(series.epoch ?? 0)
      if (!Number.isFinite(epoch) || epoch <= 0) return null
      const points = Array.isArray(series.points)
        ? series.points
            .map((point: any) => {
              if (!point || typeof point !== 'object') return null
              const ts = point.timestamp
              if (typeof ts !== 'string') return null
              const flipsSeen = Number(point.flipsSeen ?? 0)
              const uniqueAuthors = Number(point.uniqueAuthors ?? 0)
              return {
                timestamp: ts,
                flipsSeen: Number.isFinite(flipsSeen) ? flipsSeen : 0,
                uniqueAuthors: Number.isFinite(uniqueAuthors) ? uniqueAuthors : 0
              } as ProgressPoint
            })
            .filter((point): point is ProgressPoint => Boolean(point))
        : []
      return { epoch, points } as ProgressEpochSeries
    })
    .filter((series): series is ProgressEpochSeries => Boolean(series))
    .slice(0, 2)
})

const progressMinRefresh = computed(() => {
  const value = progressPayload.value?.minRefreshSeconds
  return typeof value === 'number' && Number.isFinite(value) ? value : 30
})

const progressNextRefreshAt = computed(() => {
  const value = progressPayload.value?.nextRefreshAt
  return typeof value === 'string' ? value : null
})

const nextSessionTime = computed(() => {
  const value = payload.value?.session?.nextValidationTime
  return typeof value === 'string' ? value : null
})

const nowMs = ref(Date.now())
let countdownTimer: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  countdownTimer = setInterval(() => {
    nowMs.value = Date.now()
  }, 1000)
})

onBeforeUnmount(() => {
  if (countdownTimer) {
    clearInterval(countdownTimer)
    countdownTimer = null
  }
})

const gradeStatusLabel = computed(() => {
  const statusList = gradeLeaderboard.value?.filters?.status
  return Array.isArray(statusList) && statusList.length > 0 ? statusList.join(', ') : 'All'
})

const searchAddress = ref('')
const normalizedSearchAddress = computed(() => searchAddress.value.trim().toLowerCase())
const hasSearchValue = computed(() => normalizedSearchAddress.value.length > 0)

const addressPattern = /^0x[a-f0-9]{40}$/
const isSearchAddressValid = computed(() => {
  if (!hasSearchValue.value) return true
  return addressPattern.test(normalizedSearchAddress.value)
})

const foundIdentity = computed<IdentityRow | null>(() => {
  if (!hasSearchValue.value || !isSearchAddressValid.value) return null
  const address = normalizedSearchAddress.value
  return identityLookup.value.find((row) => row.address === address) ?? null
})

const showSearchNotFound = computed(() => {
  return hasSearchValue.value && isSearchAddressValid.value && !foundIdentity.value
})

const refreshData = async () => {
  timestamp.value = Date.now()
  await refresh()
}

const formatTimestamp = (value?: string) => {
  if (!value) return '-'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return '-'
  return parsed.toLocaleString()
}

const formatInt = (value?: number) => {
  if (typeof value !== 'number' || Number.isNaN(value)) return '0'
  return Math.round(value).toLocaleString()
}

const formatDuration = (totalSeconds: number) => {
  const safe = Math.max(0, Math.floor(totalSeconds))
  const days = Math.floor(safe / 86400)
  const hours = Math.floor((safe % 86400) / 3600)
  const minutes = Math.floor((safe % 3600) / 60)
  const seconds = safe % 60
  return `${days}d ${String(hours).padStart(2, '0')}h ${String(minutes).padStart(2, '0')}m ${String(seconds).padStart(2, '0')}s`
}

const formatScore = (value?: number) => {
  if (typeof value !== 'number' || Number.isNaN(value)) return '-'
  return value.toLocaleString(undefined, {
    minimumFractionDigits: 4,
    maximumFractionDigits: 4
  })
}

const shortAddress = (address?: string) => {
  if (!address) return '-'
  if (address.length < 18) return address
  return `${address.slice(0, 10)}...${address.slice(-6)}`
}

const shortHash = (value?: string) => {
  if (!value) return '-'
  if (value.length < 24) return value
  return `${value.slice(0, 12)}...${value.slice(-8)}`
}

const formatWords = (word1?: string, word2?: string) => {
  const words = [word1, word2].filter((value) => Boolean(value && value.trim()))
  return words.length > 0 ? words.join(' / ') : '-'
}

const secondsUntilNextSession = computed(() => {
  const iso = nextSessionTime.value
  if (!iso) return null
  const ms = Date.parse(iso)
  if (!Number.isFinite(ms)) return null
  return Math.floor((ms - nowMs.value) / 1000)
})

const nextSessionCountdownLabel = computed(() => {
  const seconds = secondsUntilNextSession.value
  if (seconds === null) return 'Unavailable'
  if (seconds <= 0) return 'Session started'
  return formatDuration(seconds)
})

const CHART_WIDTH = 720
const CHART_HEIGHT = 220

const toChartPoints = (
  points: ProgressPoint[],
  selector: (point: ProgressPoint) => number
): ChartPoint[] => {
  if (!points.length) return []
  const baseTime = Date.parse(points[0].timestamp)
  if (!Number.isFinite(baseTime)) return []

  return points
    .map((point) => {
      const ts = Date.parse(point.timestamp)
      if (!Number.isFinite(ts)) return null
      const value = selector(point)
      return {
        elapsedSeconds: Math.max(0, (ts - baseTime) / 1000),
        value
      } as ChartPoint
    })
    .filter((point): point is ChartPoint => Boolean(point))
}

const buildLinePath = (
  points: ChartPoint[],
  maxElapsedSeconds: number,
  maxValue: number
) => {
  if (!points.length) return ''
  const safeMaxElapsed = maxElapsedSeconds > 0 ? maxElapsedSeconds : 1
  const safeMax = maxValue > 0 ? maxValue : 1
  if (points.length === 1) {
    const y = CHART_HEIGHT - (points[0].value / safeMax) * CHART_HEIGHT
    return `M0 ${y.toFixed(2)} L${CHART_WIDTH} ${y.toFixed(2)}`
  }
  return points
    .map((point, index) => {
      const x = (point.elapsedSeconds / safeMaxElapsed) * CHART_WIDTH
      const y = CHART_HEIGHT - (point.value / safeMax) * CHART_HEIGHT
      return `${index === 0 ? 'M' : 'L'}${x.toFixed(2)} ${y.toFixed(2)}`
    })
    .join(' ')
}

const buildMetricChart = (selector: (point: ProgressPoint) => number) => {
  const currentSeries = progressCurrentSeries.value
  const currentPoints = toChartPoints(currentSeries?.points ?? [], selector)
  const trailingSeries = progressPreviousSeries.value.map((series) => ({
    epoch: series.epoch,
    points: toChartPoints(series.points, selector)
  }))
  const allSeries = [currentPoints, ...trailingSeries.map((series) => series.points)]
  const maxElapsedSeconds = Math.max(
    1,
    ...allSeries.flatMap((series) => series.map((point) => point.elapsedSeconds))
  )
  const maxValue = Math.max(
    1,
    ...allSeries.flatMap((series) => series.map((point) => point.value))
  )

  const trailingPaths: ChartLine[] = trailingSeries.map((series, index) => ({
    epoch: series.epoch,
    path: buildLinePath(series.points, maxElapsedSeconds, maxValue),
    opacity: index === 0 ? 0.45 : 0.24
  }))

  const currentPath = buildLinePath(currentPoints, maxElapsedSeconds, maxValue)
  const latestValue = currentPoints.length ? currentPoints[currentPoints.length - 1].value : 0

  return {
    currentPath,
    trailingPaths,
    maxValue,
    maxElapsedSeconds,
    latestValue
  }
}

const flipsChart = computed(() => buildMetricChart((point) => point.flipsSeen))
const authorsChart = computed(() => buildMetricChart((point) => point.uniqueAuthors))
const chartElapsedLabel = computed(() => formatDuration(flipsChart.value.maxElapsedSeconds))
</script>

<template>
  <div class="scanner-page">
    <div class="orb orb-orange"></div>
    <div class="orb orb-blue"></div>

    <main class="scanner-shell">
      <header class="hero">
        <div>
          <p class="eyebrow">Idena Community Monitor</p>
          <h1>Extra Flips and GradeScore Leaderboards</h1>
          <p class="subtitle">
            Live extra flips, Top 10 identities, address rank lookup, and Top 10 flips from last epoch.
          </p>
        </div>
        <button class="refresh-btn" @click="refreshData">Refresh Data</button>
      </header>

      <div v-if="pending" class="state-box loading">
        <div class="spinner"></div>
        <p>Scanning blockchain data...</p>
      </div>

      <div v-else-if="error" class="state-box error">
        <h3>Network Error</h3>
        <p>{{ error.message }}</p>
        <button class="retry-btn" @click="refreshData">Retry</button>
      </div>

      <div v-else-if="data && !data.success" class="state-box error">
        <h3>Script Error</h3>
        <p>{{ data.error }}</p>
        <button class="retry-btn" @click="refreshData">Retry</button>
      </div>

      <section v-else-if="payload" class="dashboard">
        <article class="panel extra-panel">
          <div class="panel-head">
            <h2>Live Extra Flips</h2>
            <span class="badge">Epoch {{ payload.epoch }}</span>
          </div>

          <div class="countdown-box">
            <p class="countdown-label">Next validation session</p>
            <p class="countdown mono">{{ nextSessionCountdownLabel }}</p>
            <p class="countdown-time">{{ formatTimestamp(nextSessionTime || undefined) }}</p>
          </div>

          <div class="stats-grid">
            <div class="stat warning">
              <p class="label">Authors over threshold ({{ payload.threshold }})</p>
              <p class="value">{{ formatInt(payload.counts?.authorsOverThreshold) }}</p>
            </div>

            <div class="stat danger">
              <p class="label">Total extra flips</p>
              <p class="value">{{ formatInt(payload.counts?.totalExtraFlips) }}</p>
            </div>

            <div class="stat info">
              <p class="label">Flips scanned</p>
              <p class="value">{{ formatInt(payload.counts?.flipsSeen) }}</p>
            </div>

            <div class="stat success">
              <p class="label">Authors submitted flips</p>
              <p class="value">{{ formatInt(payload.counts?.uniqueAuthors) }}</p>
            </div>
          </div>

          <div class="footnote">
            <p>{{ payload.note }}</p>
            <p>Last updated: {{ formatTimestamp(payload.timestamp) }}</p>
          </div>
        </article>

        <article class="panel lookup-panel">
          <div class="panel-head">
            <h2>Find Your Rank</h2>
            <span class="badge badge-alt">By Address</span>
          </div>

          <p class="leaderboard-meta">Paste your Idena address to check full-rank position in last epoch leaderboard.</p>

          <div class="search-wrap">
            <input
              v-model="searchAddress"
              class="search-input mono"
              type="text"
              placeholder="0x..."
              autocomplete="off"
              spellcheck="false"
            />
          </div>

          <div v-if="!hasSearchValue" class="empty-state compact">
            <p>Enter an address to see rank, total gradeScore, and flip stats.</p>
          </div>

          <div v-else-if="!isSearchAddressValid" class="inline-error">
            <p>Address format looks invalid. Expected `0x` + 40 hex characters.</p>
          </div>

          <div v-else-if="foundIdentity" class="result-card">
            <p class="result-title">Found: Rank #{{ foundIdentity.rank }}</p>
            <p class="result-line">
              <span>Total gradeScore</span>
              <strong class="mono">{{ formatScore(foundIdentity.totalGradeScore) }}</strong>
            </p>
            <p class="result-line">
              <span>Flips</span>
              <strong class="mono">{{ formatInt(foundIdentity.flipCount) }}</strong>
            </p>
            <p class="result-line">
              <span>Average gradeScore</span>
              <strong class="mono">{{ formatScore(foundIdentity.avgGradeScore) }}</strong>
            </p>
            <p class="result-line">
              <span>Best flip gradeScore</span>
              <strong class="mono">{{ formatScore(foundIdentity.maxFlipGradeScore) }}</strong>
            </p>
            <p class="result-link">
              <a :href="foundIdentity.scanUrl" target="_blank" rel="noopener noreferrer">
                Open identity on scan.idena.io
              </a>
            </p>
          </div>

          <div v-else-if="showSearchNotFound" class="empty-state compact">
            <p>Address not found in the filtered last-epoch leaderboard.</p>
          </div>
        </article>

        <article class="panel leaderboard-panel">
          <div class="panel-head">
            <h2>Top {{ gradeLeaderboard?.topLimit ?? 10 }} Identities by Grade Score</h2>
            <span v-if="gradeLeaderboard?.epoch" class="badge badge-alt">Epoch {{ gradeLeaderboard.epoch }}</span>
          </div>

          <p class="leaderboard-meta">
            Excluding wrongWords bad authors: {{ formatInt(gradeLeaderboard?.excludedWrongWordsAuthorsCount) }}
          </p>
          <p class="leaderboard-meta">
            Status filter: {{ gradeStatusLabel }}
          </p>

          <div v-if="topIdentities.length" class="table-wrap">
            <table class="ranking-table ranking-table-identities">
              <colgroup>
                <col class="col-rank">
                <col class="col-address">
                <col class="col-score">
                <col class="col-count">
                <col class="col-score-sm">
                <col class="col-score-sm">
              </colgroup>
              <thead>
                <tr>
                  <th>Rank</th>
                  <th>Address</th>
                  <th>Total gradeScore</th>
                  <th>Flips</th>
                  <th>Avg</th>
                  <th>Max</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in topIdentities" :key="`${row.rank}-${row.address}`">
                  <td class="mono num">#{{ row.rank }}</td>
                  <td>
                    <a :href="row.scanUrl" target="_blank" rel="noopener noreferrer" :title="row.address">
                      <span class="clip">{{ shortAddress(row.address) }}</span>
                    </a>
                  </td>
                  <td class="mono num">{{ formatScore(row.totalGradeScore) }}</td>
                  <td class="mono num">{{ formatInt(row.flipCount) }}</td>
                  <td class="mono num">{{ formatScore(row.avgGradeScore) }}</td>
                  <td class="mono num">{{ formatScore(row.maxFlipGradeScore) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-else class="empty-state">
            <p>No identity leaderboard rows available for the selected epoch and filters.</p>
          </div>
        </article>

        <article class="panel flips-panel">
          <div class="panel-head">
            <h2>Top {{ gradeLeaderboard?.topFlipsLimit ?? 10 }} Best Flips (Last Epoch)</h2>
            <span v-if="gradeLeaderboard?.epoch" class="badge badge-alt">Epoch {{ gradeLeaderboard.epoch }}</span>
          </div>

          <div v-if="topFlips.length" class="table-wrap">
            <table class="ranking-table ranking-table-flips">
              <colgroup>
                <col class="col-rank">
                <col class="col-flip">
                <col class="col-score-sm">
                <col class="col-status">
                <col class="col-author">
                <col class="col-rank-sm">
                <col class="col-words">
              </colgroup>
              <thead>
                <tr>
                  <th>Rank</th>
                  <th>Flip</th>
                  <th>gradeScore</th>
                  <th>Status</th>
                  <th>Author</th>
                  <th>Author Rank</th>
                  <th>Words</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in topFlips" :key="`${row.rank}-${row.cid}`">
                  <td class="mono num">#{{ row.rank }}</td>
                  <td>
                    <a :href="row.scanUrl" target="_blank" rel="noopener noreferrer" :title="row.cid">
                      <span class="clip">{{ shortHash(row.cid) }}</span>
                    </a>
                  </td>
                  <td class="mono num">{{ formatScore(row.gradeScore) }}</td>
                  <td><span class="clip">{{ row.status || '-' }}</span></td>
                  <td>
                    <a :href="row.authorScanUrl" target="_blank" rel="noopener noreferrer" :title="row.author">
                      <span class="clip">{{ shortAddress(row.author) }}</span>
                    </a>
                  </td>
                  <td class="mono num">{{ row.authorRank ? `#${row.authorRank}` : '-' }}</td>
                  <td><span class="clip">{{ formatWords(row.word1, row.word2) }}</span></td>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-else class="empty-state">
            <p>No flip leaderboard rows available for the selected epoch and filters.</p>
          </div>
        </article>

        <article class="panel chart-panel">
          <div class="panel-head">
            <h2>Submission Progress Since Epoch Start</h2>
            <span class="badge badge-alt">Live Timeline</span>
          </div>

          <p class="leaderboard-meta">
            Fresh API refresh is limited to once every {{ formatInt(progressMinRefresh) }} seconds.
          </p>
          <p class="leaderboard-meta">
            Next refresh window: {{ formatTimestamp(progressNextRefreshAt || undefined) }}
          </p>

          <div class="chart-grid">
            <section class="chart-card">
              <div class="chart-card-head">
                <h3>Total flips submitted</h3>
                <p class="mono chart-value">{{ formatInt(flipsChart.latestValue) }}</p>
              </div>
              <svg class="line-chart" viewBox="0 0 720 220" preserveAspectRatio="none">
                <line x1="0" y1="220" x2="720" y2="220" class="grid-line"></line>
                <line x1="0" y1="165" x2="720" y2="165" class="grid-line"></line>
                <line x1="0" y1="110" x2="720" y2="110" class="grid-line"></line>
                <line x1="0" y1="55" x2="720" y2="55" class="grid-line"></line>
                <path
                  v-for="trail in flipsChart.trailingPaths"
                  :key="`flips-trail-${trail.epoch}`"
                  :d="trail.path"
                  class="line trail"
                  :style="{ opacity: trail.opacity }"
                />
                <path :d="flipsChart.currentPath" class="line current" />
              </svg>
              <p class="chart-caption">
                Green: current epoch {{ payload.epoch }} | Gray: previous two epochs | Window: {{ chartElapsedLabel }}
              </p>
            </section>

            <section class="chart-card">
              <div class="chart-card-head">
                <h3>Total authors submitted</h3>
                <p class="mono chart-value">{{ formatInt(authorsChart.latestValue) }}</p>
              </div>
              <svg class="line-chart" viewBox="0 0 720 220" preserveAspectRatio="none">
                <line x1="0" y1="220" x2="720" y2="220" class="grid-line"></line>
                <line x1="0" y1="165" x2="720" y2="165" class="grid-line"></line>
                <line x1="0" y1="110" x2="720" y2="110" class="grid-line"></line>
                <line x1="0" y1="55" x2="720" y2="55" class="grid-line"></line>
                <path
                  v-for="trail in authorsChart.trailingPaths"
                  :key="`authors-trail-${trail.epoch}`"
                  :d="trail.path"
                  class="line trail"
                  :style="{ opacity: trail.opacity }"
                />
                <path :d="authorsChart.currentPath" class="line current" />
              </svg>
              <p class="chart-caption">
                Green: current epoch {{ payload.epoch }} | Gray: previous two epochs | Window: {{ chartElapsedLabel }}
              </p>
            </section>
          </div>
        </article>
      </section>
    </main>
  </div>
</template>

<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&family=JetBrains+Mono:wght@500&display=swap');

:root {
  --ink: #132025;
  --muted: #4b5d66;
  --panel: #fefefe;
  --border: #d4e0e6;
  --orange: #e86c2b;
  --blue: #1570b6;
  --accent-soft: #fff2e8;
}

html,
body {
  margin: 0;
  min-height: 100%;
  background: linear-gradient(160deg, #f0f4f7 0%, #eef6f3 50%, #f8eee3 100%);
  color: var(--ink);
}
</style>

<style scoped>
.scanner-page {
  position: relative;
  overflow: hidden;
  min-height: 100vh;
  padding: 34px 18px 42px;
  font-family: "Space Grotesk", "Avenir Next", "Segoe UI", sans-serif;
}

.orb {
  position: absolute;
  border-radius: 999px;
  pointer-events: none;
  filter: blur(8px);
}

.orb-orange {
  top: -70px;
  right: -80px;
  width: 280px;
  height: 280px;
  background: radial-gradient(circle at 30% 30%, rgba(232, 108, 43, 0.35), rgba(232, 108, 43, 0));
}

.orb-blue {
  bottom: -140px;
  left: -120px;
  width: 340px;
  height: 340px;
  background: radial-gradient(circle at 70% 70%, rgba(21, 112, 182, 0.25), rgba(21, 112, 182, 0));
}

.scanner-shell {
  position: relative;
  z-index: 1;
  max-width: 1160px;
  margin: 0 auto;
}

.hero {
  display: flex;
  gap: 16px;
  justify-content: space-between;
  align-items: flex-end;
  margin-bottom: 24px;
}

.eyebrow {
  margin: 0;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  font-size: 0.74rem;
  color: var(--blue);
  font-weight: 700;
}

h1 {
  margin: 6px 0 8px;
  font-size: clamp(1.7rem, 4vw, 2.7rem);
  line-height: 1.06;
}

.subtitle {
  margin: 0;
  color: var(--muted);
  font-size: 1rem;
}

.refresh-btn,
.retry-btn {
  border: none;
  border-radius: 999px;
  padding: 12px 18px;
  font-weight: 700;
  font-family: inherit;
  cursor: pointer;
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}

.refresh-btn {
  color: #fff;
  background: linear-gradient(130deg, var(--orange), #d04f10);
  box-shadow: 0 12px 24px -18px rgba(208, 79, 16, 0.9);
}

.retry-btn {
  color: #fff;
  background: #ae2f24;
}

.refresh-btn:hover,
.retry-btn:hover {
  transform: translateY(-1px);
}

.dashboard {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
}

.panel {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 18px;
  box-shadow: 0 16px 36px -30px rgba(19, 32, 37, 0.55);
  padding: 18px;
}

.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 14px;
}

.panel-head h2 {
  margin: 0;
  font-size: 1.2rem;
}

.badge {
  background: var(--accent-soft);
  border: 1px solid #f4c8aa;
  color: #8f3608;
  font-size: 0.78rem;
  font-weight: 700;
  border-radius: 999px;
  padding: 5px 10px;
  white-space: nowrap;
}

.badge-alt {
  background: #e8f3fc;
  border-color: #bedcf3;
  color: #0a507f;
}

.stats-grid {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.countdown-box {
  margin-bottom: 12px;
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid #d2e6f5;
  background: #f1f8fe;
}

.countdown-label {
  margin: 0;
  color: #3f5f71;
  font-size: 0.78rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.countdown {
  margin: 6px 0 2px;
  font-size: 1.18rem;
  color: #0f567f;
}

.countdown-time {
  margin: 0;
  color: #5e7887;
  font-size: 0.82rem;
}

.stat {
  border-radius: 14px;
  padding: 12px;
  border: 1px solid transparent;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  min-height: 116px;
}

.warning {
  background: #fff4ea;
  border-color: #f4cfb2;
}

.danger {
  background: #ffeceb;
  border-color: #f2c5c2;
}

.info {
  background: #eaf4fe;
  border-color: #c6ddf2;
}

.success {
  background: #ecf9f0;
  border-color: #c6ebd2;
}

.label {
  margin: 0 0 8px;
  color: #5b6970;
  font-size: 0.77rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  min-height: 2.2em;
}

.value {
  margin: auto 0 0;
  font-size: 2rem;
  font-weight: 700;
}

.footnote {
  margin-top: 12px;
  border-top: 1px dashed #d7e2e8;
  padding-top: 10px;
  color: #5f6f76;
  font-size: 0.84rem;
}

.footnote p {
  margin: 6px 0;
}

.leaderboard-meta {
  margin: 4px 0;
  color: #5f6f76;
  font-size: 0.88rem;
}

.chart-panel {
  grid-column: 1 / -1;
}

.chart-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-top: 12px;
}

.chart-card {
  border: 1px solid #d8e4ea;
  border-radius: 12px;
  padding: 10px;
  background: #fcfeff;
}

.chart-card-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
}

.chart-card-head h3 {
  margin: 0;
  font-size: 0.96rem;
}

.chart-value {
  margin: 0;
  font-size: 1rem;
}

.line-chart {
  width: 100%;
  height: 180px;
  display: block;
  margin-top: 6px;
}

.grid-line {
  stroke: #dce8ef;
  stroke-width: 1;
}

.line {
  fill: none;
  stroke-width: 2.5;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.line.current {
  stroke: #16a34a;
}

.line.trail {
  stroke: #6b7280;
}

.chart-caption {
  margin: 6px 0 0;
  color: #5f6f76;
  font-size: 0.8rem;
}

.search-wrap {
  margin-top: 10px;
}

.search-input {
  width: 100%;
  border-radius: 10px;
  border: 1px solid #c8d9e2;
  padding: 11px 12px;
  font-size: 0.95rem;
  box-sizing: border-box;
  background: #fafdff;
}

.search-input:focus {
  outline: none;
  border-color: #5ea3d5;
  box-shadow: 0 0 0 3px rgba(21, 112, 182, 0.12);
}

.result-card {
  margin-top: 12px;
  border: 1px solid #cde1ef;
  background: #f5fbff;
  border-radius: 12px;
  padding: 12px;
}

.result-title {
  margin: 0 0 8px;
  font-weight: 700;
}

.result-line {
  margin: 6px 0;
  display: flex;
  justify-content: space-between;
  gap: 12px;
  color: #435760;
  font-size: 0.9rem;
}

.result-link {
  margin: 10px 0 0;
}

.inline-error {
  margin-top: 12px;
  border: 1px solid #efc4c0;
  background: #fff2f1;
  color: #7b221b;
  border-radius: 12px;
  padding: 12px;
}

.table-wrap {
  overflow: auto;
  border: 1px solid #d8e4ea;
  border-radius: 12px;
  margin-top: 12px;
  max-height: 462px;
}

table {
  width: 100%;
  border-collapse: collapse;
  min-width: 640px;
}

th,
td {
  text-align: left;
  padding: 11px 12px;
  border-bottom: 1px solid #e7eff3;
  font-size: 0.9rem;
}

th {
  font-size: 0.76rem;
  text-transform: uppercase;
  letter-spacing: 0.07em;
  color: #56717d;
  background: #f3f8fb;
}

.ranking-table {
  table-layout: fixed;
}

.ranking-table-identities .col-rank {
  width: 12%;
}

.ranking-table-identities .col-address {
  width: 32%;
}

.ranking-table-identities .col-score {
  width: 20%;
}

.ranking-table-identities .col-count {
  width: 12%;
}

.ranking-table-identities .col-score-sm {
  width: 12%;
}

.ranking-table-flips .col-rank {
  width: 8%;
}

.ranking-table-flips .col-flip {
  width: 24%;
}

.ranking-table-flips .col-score-sm {
  width: 14%;
}

.ranking-table-flips .col-status {
  width: 12%;
}

.ranking-table-flips .col-author {
  width: 18%;
}

.ranking-table-flips .col-rank-sm {
  width: 10%;
}

.ranking-table-flips .col-words {
  width: 14%;
}

.ranking-table td,
.ranking-table th {
  white-space: nowrap;
}

.num {
  text-align: right;
}

.clip {
  display: inline-block;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  vertical-align: bottom;
}

tbody tr:nth-child(even) {
  background: #fcfdff;
}

tbody tr:hover {
  background: #f4f9ff;
}

.mono {
  font-family: "JetBrains Mono", "Menlo", monospace;
  font-variant-numeric: tabular-nums;
  font-feature-settings: "tnum" 1;
}

.value,
.countdown,
.chart-value {
  font-variant-numeric: tabular-nums;
  font-feature-settings: "tnum" 1;
}

a {
  color: #0f5f96;
  text-decoration: none;
  font-weight: 600;
}

a:hover {
  text-decoration: underline;
}

.state-box {
  background: rgba(255, 255, 255, 0.88);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 28px;
  text-align: center;
}

.spinner {
  width: 38px;
  height: 38px;
  border: 4px solid #d9e4ea;
  border-top-color: var(--blue);
  border-radius: 999px;
  margin: 0 auto 12px;
  animation: spin 0.9s linear infinite;
}

.empty-state {
  margin-top: 12px;
  border: 1px dashed #d6e2e8;
  border-radius: 12px;
  padding: 20px;
  color: #5f6f76;
  background: #f9fcfe;
}

.empty-state.compact {
  padding: 12px;
}

.leaderboard-panel,
.flips-panel {
  display: flex;
  flex-direction: column;
}

.leaderboard-panel,
.flips-panel {
  min-height: 320px;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

@media (max-width: 1080px) {
  .dashboard {
    grid-template-columns: 1fr;
  }

  .hero {
    flex-direction: column;
    align-items: flex-start;
  }
}

@media (max-width: 720px) {
  .scanner-page {
    padding: 22px 12px 28px;
  }

  .panel {
    padding: 14px;
  }

  .stats-grid {
    grid-template-columns: 1fr;
  }

  .chart-grid {
    grid-template-columns: 1fr;
  }

  th,
  td {
    padding: 9px 10px;
  }
}
</style>
