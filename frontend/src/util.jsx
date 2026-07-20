import React from 'react'
import dayjs from 'dayjs'
import { Tag } from 'antd'
import { useLang } from './i18n'

export const GREEN = '#49aa19'
export const RED = '#dc4446'
export const BLUE = '#1668dc'
export const ORANGE = '#b98217'
export const CHART_THEME = 'classicDark'

export const STRATEGY_KEYS = ['pre_trend', 'fair_value', 'tick_momo', 'open_burst',
  'prev_reverse', 'mystic_east']

export async function apiGet(path) {
  const r = await fetch(path)
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`)
  return r.json()
}

export async function apiPost(path, body) {
  const r = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const data = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(data.error || `${r.status}`)
  return data
}

export const fmtTs = (ts, f = 'MM-DD HH:mm:ss') => (ts ? dayjs.unix(ts).format(f) : '—')

export const money = (v, digits = 2) =>
  v == null ? '—' : `${v > 0 ? '+' : ''}${Number(v).toFixed(digits)}`

export const STATE_KEYS = ['pending', 'ordered', 'holding', 'tp_set', 'settled', 'skipped']
const STATE_COLOR = {
  pending: 'default', ordered: 'processing', holding: 'processing',
  tp_set: 'gold', settled: 'success', skipped: 'default',
}
export const KIND_KEYS = ['buy_limit', 'sell_tp', 'cancel', 'cancel_all', 'fill', 'redeem', 'withdraw', 'deposit']
const KIND_COLOR = {
  buy_limit: 'blue', sell_tp: 'gold', cancel: 'default', cancel_all: 'default',
  fill: 'green', entry: 'blue', tp: 'gold', redeem: 'purple', withdraw: 'magenta', deposit: 'cyan',
}

export function StateTag({ s }) {
  const { t } = useLang()
  if (!s) return <span style={{ color: '#555' }}>—</span>
  return <Tag color={STATE_COLOR[s] || 'default'}>{t(`st.${s}`)}</Tag>
}

export function SideTag({ s }) {
  const { t } = useLang()
  if (!s) return <span style={{ color: '#555' }}>—</span>
  return <Tag color={s === 'up' ? 'green' : 'red'}>{s === 'up' ? t('c.up') : t('c.down')}</Tag>
}

export function ResultTag({ r }) {
  const { t } = useLang()
  if (!r) return <span style={{ color: '#555' }}>—</span>
  if (r === 'unknown') return <Tag>{t('c.unknown')}</Tag>
  return <Tag color={r === 'up' ? 'green' : 'red'}>{r === 'up' ? t('c.rise') : t('c.fall')}</Tag>
}

export function ModeTag({ m }) {
  const { t } = useLang()
  if (!m) return <span style={{ color: '#555' }}>—</span>
  return <Tag color={m === 'live' ? 'volcano' : 'blue'}>{m === 'live' ? t('c.live') : t('c.paper')}</Tag>
}

export function KindTag({ k }) {
  const { t } = useLang()
  if (!k) return <span style={{ color: '#555' }}>—</span>
  return <Tag color={KIND_COLOR[k] || 'default'}>{t(`k.${k}`) === `k.${k}` ? k : t(`k.${k}`)}</Tag>
}

export function Pnl({ v, bold, digits = 2 }) {
  if (v == null) return <span style={{ color: '#555' }}>—</span>
  const color = v > 0 ? GREEN : v < 0 ? RED : '#8c8c8c'
  return (
    <span style={{ color, fontWeight: bold ? 600 : 500, fontVariantNumeric: 'tabular-nums' }}>
      {money(v, digits)}
    </span>
  )
}

export const num = (v, digits = 2) =>
  v == null ? '—' : Number(v).toFixed(digits)

export const pmUrl = (slug) => `https://polymarket.com/event/${slug}`

export const mmss = (sec) => {
  const s = Math.max(0, Math.round(sec))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}
