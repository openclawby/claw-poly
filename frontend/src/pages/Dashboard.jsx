import React, { useContext, useEffect, useReducer, useState } from 'react'
import {
  Alert, Card, Col, Empty, Progress, Row, Space, Statistic, Table,
  Tag, Typography,
} from 'antd'
import { Area, Column, Pie } from '@ant-design/plots'
import dayjs from 'dayjs'
import { Ctx } from '../App'
import {
  apiGet, BLUE, CHART_THEME, fmtTs, GREEN, mmss, num, Pnl, pmUrl, RED,
  SideTag,
} from '../util'
import { useLang } from '../i18n'

function ActiveRoundCard({ r, posList, nowSec, leadSec, preview }) {
  const { t } = useLang()
  const total = r.end_ts - r.start_ts
  const elapsed = Math.min(Math.max(nowSec - r.start_ts, 0), total)
  const remain = Math.max(r.end_ts - nowSec, 0)
  const started = nowSec >= r.start_ts
  const toDecide = r.start_ts - (leadSec || 600) - nowSec
  const hint = preview?.side
    ? t('d.card.hint', { side: preview.side === 'up' ? t('c.up') : t('c.down') })
      + (preview.tier === 'trigger' ? '⚡' : '')
    : ''
  const openPositions = posList.filter((p) => ['ordered', 'holding', 'tp_set'].includes(p.state))
  const pendingLabel = openPositions.length === 0 && !started
    ? (preview && !preview.ready
      ? t('d.card.warm')
      : (toDecide > 0
        ? t('d.card.buyin', { t: mmss(toDecide) }) + hint
        : t('d.card.deciding') + hint))
    : null
  const mainSide = openPositions[0]?.side
  return (
    <Card size="small" style={{ width: 235 }} styles={{ body: { padding: 12 } }}>
      <Space direction="vertical" size={6} style={{ width: '100%' }}>
        <Space style={{ justifyContent: 'space-between', width: '100%' }}>
          <a href={pmUrl(r.slug)} target="_blank" rel="noreferrer" style={{ fontWeight: 600 }}>
            {fmtTs(r.start_ts, 'HH:mm')} ↗
          </a>
          {openPositions.length
            ? <Tag color="processing">{t('d.card.pos', { n: openPositions.length })}</Tag>
            : <Tag>{t('d.card.wait')}</Tag>}
        </Space>
        <Progress
          percent={started ? Math.round((elapsed / total) * 100) : 0}
          size="small"
          format={() => (started ? mmss(remain) : t('d.card.preopen'))}
          strokeColor={mainSide === 'up' ? GREEN : mainSide === 'down' ? RED : BLUE}
        />
        {openPositions.length > 0 && (
          <Space size={4} wrap>
            {openPositions.map((p) => (
              <Tag key={p.strategy} color={p.side === 'up' ? 'green' : 'red'} style={{ fontSize: 11 }}>
                {p.strategy} {p.side === 'up' ? '↑' : '↓'}@{num(p.entry_price)} ${num(p.usd, 0)}
              </Tag>
            ))}
          </Space>
        )}
        {pendingLabel && (
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>{pendingLabel}</Typography.Text>
        )}
        {openPositions[0]?.reason && (
          <Typography.Text type="secondary" style={{ fontSize: 12 }} ellipsis={{ tooltip: openPositions[0].reason }}>
            {openPositions[0].reason}
          </Typography.Text>
        )}
      </Space>
    </Card>
  )
}

export default function Dashboard() {
  const { t } = useLang()
  const { state } = useContext(Ctx)
  const [stats, setStats] = useState(null)
  const [, tick] = useReducer((x) => x + 1, 0)

  const st = state?.status
  const mode = 'paper'

  useEffect(() => {
    let stop = false
    const load = () => apiGet(`/api/stats?mode=${mode}`).then((d) => !stop && setStats(d)).catch(() => {})
    load()
    const iv = setInterval(load, 15000)
    return () => { stop = true; clearInterval(iv) }
  }, [mode])

  useEffect(() => {
    const iv = setInterval(tick, 1000)
    return () => clearInterval(iv)
  }, [])

  const nowSec = Math.floor(Date.now() / 1000)
  let leadSec = 600
  try {
    const en = JSON.parse(state?.settings?.enabled_strategies || '[]')
    const p = JSON.parse(state?.settings?.params || '{}')
    if (en.includes('pre_trend') && p.lead_sec) leadSec = Number(p.lead_sec)
  } catch { /* keep default */ }
  const positions = state?.positions || []
  const active = (state?.rounds || [])
    .filter((r) => r.end_ts > nowSec - 30)
    .sort((a, b) => a.start_ts - b.start_ts)
  const openUsd = positions
    .filter((p) => ['ordered', 'holding', 'tp_set'].includes(p.state))
    .reduce((s, p) => s + (p.usd || 0), 0)
  const maxOpen = Number(state?.settings?.max_open_usd || 0)

  const curve = (stats?.curve || []).map((p) => ({
    time: dayjs.unix(p.ts).format('MM-DD HH:mm'), pnl: p.cum,
  }))
  const daily = stats?.daily || []
  const stateDist = Object.entries(stats?.states || {}).map(([s, c]) => ({
    label: `${s} (${c})`, count: c,
  }))

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Row gutter={[16, 16]}>
        <Col xs={12} md={8} xl={4}>
          <Card><Statistic title={t('d.btc')} value={st?.btc} precision={2} prefix="$" /></Card>
        </Col>
        <Col xs={12} md={8} xl={4}>
          <Card>
            <Statistic
              title={t('d.today.paper')}
              value={st?.realized_today ?? 0} precision={2}
              valueStyle={{ color: (st?.realized_today ?? 0) >= 0 ? GREEN : RED }}
              prefix={(st?.realized_today ?? 0) >= 0 ? '+' : ''} suffix="$"
            />
          </Card>
        </Col>
        <Col xs={12} md={8} xl={4}>
          <Card>
            <Statistic
              title={t('d.cum.paper')}
              value={stats?.total_pnl ?? 0} precision={2}
              valueStyle={{ color: (stats?.total_pnl ?? 0) >= 0 ? GREEN : RED }}
              prefix={(stats?.total_pnl ?? 0) >= 0 ? '+' : ''} suffix="$"
            />
          </Card>
        </Col>
        <Col xs={12} md={8} xl={4}>
          <Card>
            <Statistic title={t('d.winrate')} value={stats?.win_rate ?? 0} suffix="%" />
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {t('d.wl', { w: stats?.wins ?? 0, l: stats?.losses ?? 0, t: stats?.tp_hits ?? 0 })}
            </Typography.Text>
          </Card>
        </Col>
        <Col xs={12} md={8} xl={4}>
          <Card>
            <Statistic title={t('d.settled')} value={stats?.trades ?? 0} />
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {t('d.best')} <Pnl v={stats?.best} digits={2} /> · {t('d.worst')} <Pnl v={stats?.worst} digits={2} />
            </Typography.Text>
          </Card>
        </Col>
        <Col xs={12} md={8} xl={4}>
          <Card>
            <Statistic
              title={t('d.exposure')} value={openUsd} precision={0} prefix="$"
              suffix={maxOpen ? ` / ${maxOpen}` : ''}
            />
            <Progress
              percent={maxOpen ? Math.round((openUsd / maxOpen) * 100) : 0}
              size="small" showInfo={false}
              strokeColor={openUsd / (maxOpen || 1) > 0.8 ? RED : BLUE}
            />
          </Card>
        </Col>
      </Row>

      <Card
        title={t('d.active', { n: state?.settings?.horizon || 6 })}
        styles={{ body: { overflowX: 'auto' } }}
      >
        {st?.preview && !st.preview.ready && (
          <Alert
            type="info" showIcon style={{ marginBottom: 12 }}
            message={t('d.buffer', { a: st.btc_buffer_min ?? 0, b: (st.preview.lookback_sec || 600) / 60 })}
          />
        )}
        {st?.preview?.ready && (
          <Alert
            type={st.preview.tier === 'trigger' ? 'warning' : 'success'} showIcon style={{ marginBottom: 12 }}
            message={t('d.signal', {
              lb: (st.preview.lookback_sec || 600) / 60,
              mv: `${st.preview.move_pct >= 0 ? '+' : ''}${st.preview.move_pct}`,
              side: st.preview.side === 'up' ? t('c.up') : t('c.down'),
              tier: st.preview.tier === 'trigger' ? t('d.tier.trigger') : t('d.tier.cover'),
              lead: (st.preview.lead_sec || 600) / 60,
            })}
          />
        )}
        {active.length === 0 ? (
          <Empty description={t('d.noactive')} />
        ) : (
          <Space size={12} style={{ paddingBottom: 4 }}>
            {active.map((r) => (
              <ActiveRoundCard
                key={r.slug} r={r} nowSec={nowSec} leadSec={leadSec} preview={st?.preview}
                posList={positions.filter((p) => p.slug === r.slug)}
              />
            ))}
          </Space>
        )}
      </Card>

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={14}>
          <Card title={t('d.equity')}>
            {curve.length === 0 ? <Empty description={t('d.nosettle')} /> : (
              <Area
                data={curve} xField="time" yField="pnl" height={280}
                theme={CHART_THEME} shapeField="smooth"
                style={{ fill: 'linear-gradient(-90deg, rgba(22,104,220,0.02) 0%, rgba(22,104,220,0.35) 100%)' }}
                line={{ style: { stroke: BLUE, lineWidth: 2 } }}
                axis={{ y: { labelFormatter: (v) => `$${v}` } }}
              />
            )}
          </Card>
        </Col>
        <Col xs={24} xl={10}>
          <Card title={t('d.daily')}>
            {daily.length === 0 ? <Empty description={t('d.nodata')} /> : (
              <Column
                data={daily} xField="date" yField="pnl" height={280}
                theme={CHART_THEME}
                style={{ fill: (d) => ((d.pnl ?? 0) >= 0 ? GREEN : RED), radiusTopLeft: 4, radiusTopRight: 4 }}
                axis={{ y: { labelFormatter: (v) => `$${v}` } }}
                tooltip={{
                  title: 'date',
                  items: [
                    { field: 'pnl', valueFormatter: (v) => `$${Number(v).toFixed(2)}` },
                    { field: 'trades', name: t('d.trades') },
                  ],
                }}
              />
            )}
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} md={12} xl={6}>
          <Card title={t('d.bystrat')} styles={{ body: { padding: 12 } }}>
            <Table
              size="small" pagination={false} rowKey="strategy"
              dataSource={stats?.by_strategy || []}
              locale={{ emptyText: t('d.nodata') }}
              columns={[
                { title: t('c.strategy'), dataIndex: 'strategy', render: (v) => <Tag color="geekblue">{v}</Tag> },
                { title: t('d.trades'), dataIndex: 'trades' },
                { title: t('d.winrate'), key: 'wr', render: (_, r) => (r.trades ? `${((r.wins / r.trades) * 100).toFixed(1)}%` : '—') },
                { title: t('c.pnl'), dataIndex: 'pnl', render: (v) => <Pnl v={v} /> },
              ]}
            />
          </Card>
        </Col>
        <Col xs={24} md={12} xl={6}>
          <Card title={t('d.states')}>
            {stateDist.length === 0 ? <Empty description={t('d.nodata')} /> : (
              <Pie
                data={stateDist} angleField="count" colorField="label"
                height={240} theme={CHART_THEME} innerRadius={0.62}
                legend={{ color: { position: 'right' } }} label={false}
              />
            )}
          </Card>
        </Col>
        <Col xs={24} md={12} xl={6}>
          <Card title={t('d.hourly')}>
            {(stats?.by_hour || []).length === 0 ? <Empty description={t('d.nodata')} /> : (
              <Column
                data={(stats?.by_hour || []).map((h) => ({ ...h, hourLabel: t('d.hour', { h: h.hour }) }))}
                xField="hourLabel" yField="pnl" height={240} theme={CHART_THEME}
                style={{ fill: (d) => ((d.pnl ?? 0) >= 0 ? GREEN : RED) }}
                axis={{ y: { labelFormatter: (v) => `$${v}` } }}
                tooltip={{ items: [{ field: 'pnl' }, { field: 'trades', name: t('d.trades') }] }}
              />
            )}
          </Card>
        </Col>
        <Col xs={24} md={12} xl={6}>
          <Card title={t('d.byside')}>
            <Table
              size="small" pagination={false} rowKey="side"
              dataSource={stats?.by_side || []}
              locale={{ emptyText: t('d.nodata') }}
              columns={[
                { title: t('c.side'), dataIndex: 'side', render: (s) => <SideTag s={s} /> },
                { title: t('d.trades'), dataIndex: 'trades' },
                { title: t('d.winrate'), key: 'wr', render: (_, r) => (r.trades ? `${((r.wins / r.trades) * 100).toFixed(1)}%` : '—') },
                { title: t('c.pnl'), dataIndex: 'pnl', render: (v) => <Pnl v={v} /> },
              ]}
            />
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {t('d.viewing')}<Tag color="blue">{t('c.paper')}</Tag>
            </Typography.Text>
          </Card>
        </Col>
      </Row>
    </Space>
  )
}
