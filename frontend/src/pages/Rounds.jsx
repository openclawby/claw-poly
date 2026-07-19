import React, { useCallback, useContext, useEffect, useState } from 'react'
import {
  Button, Card, Col, Descriptions, Row, Select, Space, Statistic, Switch,
  Table, Tag, Typography, message,
} from 'antd'
import { DownloadOutlined, ExportOutlined, ReloadOutlined } from '@ant-design/icons'
import {
  apiGet, fmtTs, GREEN, KindTag, ModeTag, num, Pnl, pmUrl, RED, ResultTag,
  SideTag, STATE_KEYS, StateTag, STRATEGY_KEYS,
} from '../util'
import { Ctx } from '../App'
import { useLang } from '../i18n'

function RoundDetail({ r }) {
  const { t } = useLang()
  const [orders, setOrders] = useState(null)
  useEffect(() => {
    apiGet(`/api/orders?slug=${r.slug}&limit=50`)
      .then((d) => setOrders(d.orders)).catch(() => setOrders([]))
  }, [r.slug])
  return (
    <Space direction="vertical" size={12} style={{ width: '100%' }}>
      <Descriptions
        size="small" bordered column={{ xs: 1, md: 3 }}
        items={[
          { label: t('r.d.slug'), children: <Typography.Text copyable style={{ fontSize: 12 }}>{r.slug}</Typography.Text> },
          { label: t('r.d.open'), children: fmtTs(r.start_ts) },
          { label: t('r.d.close'), children: fmtTs(r.end_ts) },
          { label: 'Up token', children: <Typography.Text copyable={{ text: r.token_up }} style={{ fontSize: 12 }}>{r.token_up ? `${r.token_up.slice(0, 14)}…` : '—'}</Typography.Text> },
          { label: 'Down token', children: <Typography.Text copyable={{ text: r.token_down }} style={{ fontSize: 12 }}>{r.token_down ? `${r.token_down.slice(0, 14)}…` : '—'}</Typography.Text> },
          { label: t('r.d.tick'), children: r.tick ?? '—' },
          { label: t('r.d.entryoid'), children: r.order_id || '—' },
          { label: t('r.d.tpoid'), children: r.tp_order_id || '—' },
          { label: t('r.d.shares'), children: num(r.shares, 4) },
          { label: t('r.d.openp'), children: r.open_price ? `$${num(r.open_price)}` : '—' },
          { label: t('r.d.closep'), children: r.close_price ? `$${num(r.close_price)}` : '—' },
          { label: t('r.d.updated'), children: fmtTs(r.updated_ts) },
          { label: t('c.reason'), children: r.reason || '—', span: 3 },
        ]}
      />
      <Table
        size="small" rowKey="id" pagination={false} dataSource={orders || []}
        loading={orders === null}
        locale={{ emptyText: t('r.d.noorders') }}
        columns={[
          { title: t('c.time'), dataIndex: 'ts', render: (v) => fmtTs(v) },
          { title: t('c.strategy'), dataIndex: 'strategy', render: (v) => (v ? <Tag color="geekblue">{v}</Tag> : '—') },
          { title: t('c.kind'), dataIndex: 'kind', render: (k) => <KindTag k={k} /> },
          { title: t('c.side'), dataIndex: 'side', render: (s) => <SideTag s={s} /> },
          { title: t('c.entry'), dataIndex: 'price', render: (v) => num(v) },
          { title: t('c.amount'), dataIndex: 'usd', render: (v) => (v != null ? `$${num(v)}` : '—') },
          { title: t('c.orderid'), dataIndex: 'order_id', ellipsis: true },
          { title: t('c.note'), dataIndex: 'note', ellipsis: true },
        ]}
      />
    </Space>
  )
}

export default function Rounds() {
  const { t } = useLang()
  const { state } = useContext(Ctx)
  const preview = state?.status?.preview
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(false)
  const [auto, setAuto] = useState(true)
  const [f, setF] = useState({ state: '', side: '', result: '', strategy: '', limit: 300 })

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const q = new URLSearchParams(
        Object.entries(f).filter(([, v]) => v !== '' && v != null)).toString()
      const d = await apiGet(`/api/rounds?${q}`)
      setRows(d.rounds)
    } catch (e) { message.error(String(e)) } finally { setLoading(false) }
  }, [f])

  useEffect(() => { load() }, [load])
  useEffect(() => {
    if (!auto) return undefined
    const iv = setInterval(load, 10000)
    return () => clearInterval(iv)
  }, [auto, load])

  const settled = rows.filter((r) => r.state === 'settled')
  const sumPnl = settled.reduce((s, r) => s + (r.pnl || 0), 0)
  const wins = settled.filter((r) => (r.pnl || 0) > 0).length

  const sel = (key, options, placeholder, width = 130) => (
    <Select
      allowClear placeholder={placeholder} style={{ width }} value={f[key] || undefined}
      onChange={(v) => setF({ ...f, [key]: v || '' })} options={options}
    />
  )

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Card size="small">
        <Space wrap>
          {sel('state', STATE_KEYS.map((v) => ({ value: v, label: t(`st.${v}`) })), t('r.filter.state'))}
          {sel('side', [{ value: 'up', label: t('c.up') }, { value: 'down', label: t('c.down') }], t('c.side'), 100)}
          {sel('result', [
            { value: 'up', label: t('r.filter.result.up') },
            { value: 'down', label: t('r.filter.result.down') },
            { value: 'unknown', label: t('r.filter.result.unknown') },
          ], t('c.result'), 130)}
          {sel('strategy', STRATEGY_KEYS.map((v) => ({ value: v, label: v })), t('c.strategy'), 130)}
          <Select
            style={{ width: 130 }} value={f.limit}
            onChange={(v) => setF({ ...f, limit: v })}
            options={[100, 300, 1000, 3000].map((n) => ({ value: n, label: t('c.last', { n }) }))}
          />
          <Button icon={<ReloadOutlined />} onClick={load} loading={loading}>{t('c.refresh')}</Button>
          <Button icon={<DownloadOutlined />} onClick={() => { window.location.href = '/api/export?what=trades' + (f.strategy ? `&strategy=${f.strategy}` : '') }}>
            {t('c.export')}
          </Button>
          <Space size={4}>
            <Switch size="small" checked={auto} onChange={setAuto} />
            <Typography.Text type="secondary">{t('c.auto')}</Typography.Text>
          </Space>
        </Space>
      </Card>

      <Row gutter={16}>
        <Col span={6}><Card size="small"><Statistic title={t('r.found')} value={rows.length} /></Card></Col>
        <Col span={6}><Card size="small"><Statistic title={t('r.settled')} value={settled.length} /></Card></Col>
        <Col span={6}>
          <Card size="small">
            <Statistic title={t('r.wr')} value={settled.length ? (wins / settled.length) * 100 : 0} precision={1} suffix="%" />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic
              title={t('r.sum')} value={sumPnl} precision={2} prefix={sumPnl >= 0 ? '+$' : '-$'}
              valueStyle={{ color: sumPnl >= 0 ? GREEN : RED }}
              formatter={(v) => Math.abs(Number(v)).toFixed(2)}
            />
          </Card>
        </Col>
      </Row>

      <Card styles={{ body: { padding: 0 } }}>
        <Table
          rowKey={(r) => r.slug + (r.strategy || '')} dataSource={rows} loading={loading} size="middle"
          scroll={{ x: 1350 }}
          pagination={{ pageSize: 20, showSizeChanger: true, pageSizeOptions: [20, 50, 100], showTotal: (n) => t('r.total', { n }) }}
          expandable={{ expandedRowRender: (r) => <RoundDetail r={r} /> }}
          columns={[
            {
              title: t('c.round'), key: 'slug', fixed: 'left', width: 150,
              sorter: (a, b) => a.start_ts - b.start_ts, defaultSortOrder: 'descend',
              render: (_, r) => (
                <Space direction="vertical" size={0}>
                  <a href={pmUrl(r.slug)} target="_blank" rel="noreferrer">
                    {fmtTs(r.start_ts, 'MM-DD HH:mm')} <ExportOutlined style={{ fontSize: 11 }} />
                  </a>
                  <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                    ~{fmtTs(r.end_ts, 'HH:mm')}
                  </Typography.Text>
                </Space>
              ),
            },
            { title: t('c.state'), dataIndex: 'state', width: 105, render: (s) => <StateTag s={s} /> },
            { title: t('c.strategy'), dataIndex: 'strategy', width: 110, render: (v) => (v ? <Tag color="geekblue">{v}</Tag> : '—') },
            { title: t('c.mode'), dataIndex: 'mode', width: 80, render: (m) => <ModeTag m={m} /> },
            { title: t('c.side'), dataIndex: 'side', width: 95, render: (s) => <SideTag s={s} /> },
            { title: t('c.entry'), dataIndex: 'entry_price', width: 80, render: (v) => num(v) },
            { title: t('c.amount'), dataIndex: 'usd', width: 75, render: (v) => (v != null ? `$${num(v, 0)}` : '—') },
            { title: t('c.shares'), dataIndex: 'shares', width: 85, render: (v) => num(v, 2) },
            {
              title: t('r.btc.oc'), key: 'oc', width: 175,
              render: (_, r) => (r.open_price
                ? (
                  <span style={{ fontVariantNumeric: 'tabular-nums', fontSize: 12 }}>
                    {num(r.open_price, 1)} → {r.close_price ? num(r.close_price, 1) : '…'}
                    {r.close_price && (
                      <Typography.Text style={{ color: r.close_price >= r.open_price ? GREEN : RED, marginLeft: 4, fontSize: 12 }}>
                        ({r.close_price >= r.open_price ? '+' : ''}{num(r.close_price - r.open_price, 1)})
                      </Typography.Text>
                    )}
                  </span>
                ) : '—'),
            },
            { title: t('c.result'), dataIndex: 'result', width: 75, render: (v) => <ResultTag r={v} /> },
            {
              title: t('c.pnl'), dataIndex: 'pnl', width: 95,
              sorter: (a, b) => (a.pnl || 0) - (b.pnl || 0),
              render: (v) => <Pnl v={v} bold />,
            },
            {
              title: t('c.reason'), dataIndex: 'reason', ellipsis: { showTitle: false },
              render: (v, row) => {
                if (row.state === 'pending' && preview) {
                  if (!preview.ready) return <Typography.Text type="secondary" style={{ fontSize: 12 }}>{t('r.pending.warm')}</Typography.Text>
                  return (
                    <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                      {t('r.pending.wait', { m: Math.round((preview.lead_sec || 600) / 60) })}
                      <Typography.Text style={{ color: preview.side === 'up' ? GREEN : RED, fontSize: 12 }}>
                        {preview.side === 'up' ? t('c.up') : t('c.down')}
                      </Typography.Text>
                      {preview.tier === 'trigger' ? t('r.pending.tier.t') : t('r.pending.tier.c')}
                    </Typography.Text>
                  )
                }
                return <Typography.Text style={{ fontSize: 12 }} ellipsis={{ tooltip: v }}>{v || '—'}</Typography.Text>
              },
            },
          ]}
        />
      </Card>
    </Space>
  )
}
