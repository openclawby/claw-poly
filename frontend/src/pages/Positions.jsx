import React, { useEffect, useReducer, useState } from 'react'
import {
  Button, Card, Col, Progress, Row, Space, Statistic, Table, Tag, Typography,
} from 'antd'
import { ExportOutlined, ReloadOutlined, SyncOutlined } from '@ant-design/icons'
import {
  apiGet, BLUE, fmtTs, GREEN, mmss, ModeTag, num, Pnl, pmUrl, RED, SideTag,
  StateTag,
} from '../util'
import { useLang } from '../i18n'

export default function Positions() {
  const { t } = useLang()
  const [rows, setRows] = useState(null)
  const [loading, setLoading] = useState(false)
  const [quoting, setQuoting] = useState(false)
  const [quotedN, setQuotedN] = useState(0)
  const [, tick] = useReducer((x) => x + 1, 0)

  const load = async () => {
    setLoading(true)
    try {
      // 第一段:秒开表格(纯数据库,无行情)
      const fast = await apiGet('/api/positions/open?quotes=0')
      setRows(fast.positions)
    } catch { /* noop */ }
    setLoading(false)
    // 第二段:10 并发补实时报价,期间有可见的加载提示
    setQuoting(true)
    try {
      const full = await apiGet('/api/positions/open')
      setRows(full.positions)
      setQuotedN(full.quoted || 0)
    } catch { /* noop */ }
    setQuoting(false)
  }

  useEffect(() => {
    load()
    const iv = setInterval(load, 15000)
    const sec = setInterval(tick, 1000)
    return () => { clearInterval(iv); clearInterval(sec) }
  }, [])

  const nowSec = Math.floor(Date.now() / 1000)
  const list = rows || []
  const resting = list.filter((r) => r.state === 'ordered')
  const holding = list.filter((r) => r.state === 'tp_set' || r.state === 'holding')
  const invested = holding.reduce((s, r) => s + (r.usd || 0), 0)
    + resting.reduce((s, r) => s + (r.usd || 0), 0)
  const unreal = holding.reduce((s, r) => s + (r.unrealized ?? 0), 0)

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Row gutter={[16, 16]}>
        <Col xs={12} md={6}><Card size="small"><Statistic title={t('p.open.n')} value={list.length} /></Card></Col>
        <Col xs={12} md={6}>
          <Card size="small">
            <Statistic title={t('p.holding')} value={holding.length} suffix={` / ${t('p.resting')} ${resting.length}`} valueStyle={{ fontSize: 20 }} />
          </Card>
        </Col>
        <Col xs={12} md={6}><Card size="small"><Statistic title={t('p.invested')} value={invested} precision={2} prefix="$" /></Card></Col>
        <Col xs={12} md={6}>
          <Card size="small">
            <Statistic
              title={t('p.unreal')} value={unreal} precision={2}
              valueStyle={{ color: unreal >= 0 ? GREEN : RED }}
              prefix={unreal >= 0 ? '+$' : '-$'}
              formatter={(v) => Math.abs(Number(v)).toFixed(2)}
            />
          </Card>
        </Col>
      </Row>

      <Card
        title={(
          <Space>
            {t('p.title')}
            {quoting && (
              <Tag icon={<SyncOutlined spin />} color="processing">{t('p.quoting')}</Tag>
            )}
            {!quoting && quotedN > 0 && (
              <Tag color="success">{t('p.quoted.n', { n: quotedN })}</Tag>
            )}
          </Space>
        )}
        extra={<Button icon={<ReloadOutlined />} onClick={load} loading={loading || quoting}>{t('c.refresh')}</Button>}
        styles={{ body: { padding: 0 } }}
      >
        <Table
          rowKey={(r) => r.slug + r.strategy} dataSource={list} loading={rows === null}
          size="middle" pagination={false} scroll={{ x: 1200 }}
          locale={{ emptyText: t('p.empty') }}
          columns={[
            {
              title: t('c.round'), key: 'slug', fixed: 'left', width: 150,
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
            { title: t('c.strategy'), dataIndex: 'strategy', width: 110, render: (v) => <Tag color="geekblue">{v}</Tag> },
            { title: t('c.state'), dataIndex: 'state', width: 105, render: (s) => <StateTag s={s} /> },
            { title: t('c.mode'), dataIndex: 'mode', width: 80, render: (m) => <ModeTag m={m} /> },
            { title: t('c.side'), dataIndex: 'side', width: 95, render: (s) => <SideTag s={s} /> },
            { title: t('c.entry'), dataIndex: 'entry_price', width: 80, render: (v) => num(v) },
            { title: t('c.amount'), dataIndex: 'usd', width: 75, render: (v) => (v != null ? `$${num(v, 2)}` : '—') },
            { title: t('c.shares'), dataIndex: 'shares', width: 85, render: (v) => num(v, 2) },
            { title: t('p.curbid'), dataIndex: 'cur_bid', width: 90, render: (v) => (v != null ? v.toFixed(2) : (quoting ? <SyncOutlined spin style={{ color: '#666' }} /> : '—')) },
            {
              title: t('p.unreal.col'), dataIndex: 'unrealized', width: 100,
              sorter: (a, b) => (a.unrealized ?? 0) - (b.unrealized ?? 0),
              render: (v) => (v != null ? <Pnl v={v} /> : (quoting ? <SyncOutlined spin style={{ color: '#666' }} /> : <Pnl v={v} />)),
            },
            {
              title: `${t('p.settle.in')} / ${t('p.opens.in')}`, key: 'cd', width: 150,
              render: (_, r) => {
                const started = nowSec >= r.start_ts
                const target = started ? r.end_ts : r.start_ts
                const remain = target - nowSec
                const total = started ? 300 : Math.max(target - (r.updated_ts || target - 3600), 60)
                return (
                  <Space direction="vertical" size={0} style={{ width: '100%' }}>
                    <Typography.Text style={{ fontSize: 12 }}>
                      {started ? t('p.started') : t('p.notstarted')} · {mmss(remain)}
                    </Typography.Text>
                    <Progress
                      percent={started ? Math.round(((300 - remain) / 300) * 100) : Math.min(99, Math.round((1 - remain / total) * 100))}
                      size="small" showInfo={false}
                      strokeColor={r.side === 'up' ? GREEN : r.side === 'down' ? RED : BLUE}
                    />
                  </Space>
                )
              },
            },
            { title: t('c.reason'), dataIndex: 'reason', ellipsis: { showTitle: false }, render: (v) => <Typography.Text style={{ fontSize: 12 }} ellipsis={{ tooltip: v }}>{v || '—'}</Typography.Text> },
          ]}
        />
      </Card>
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>{t('p.note')}</Typography.Text>
    </Space>
  )
}
