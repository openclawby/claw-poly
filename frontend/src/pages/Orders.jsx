import React, { useCallback, useEffect, useState } from 'react'
import { Button, Card, Select, Space, Switch, Table, Tag, Typography, message } from 'antd'
import { DownloadOutlined, ReloadOutlined } from '@ant-design/icons'
import {
  apiGet, fmtTs, KIND_KEYS, KindTag, ModeTag, num, SideTag, STRATEGY_KEYS,
} from '../util'
import { useLang } from '../i18n'

export default function Orders() {
  const { t } = useLang()
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(false)
  const [auto, setAuto] = useState(true)
  const [f, setF] = useState({ kind: '', mode: '', strategy: '', limit: 300 })

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const q = new URLSearchParams(
        Object.entries(f).filter(([, v]) => v !== '' && v != null)).toString()
      setRows((await apiGet(`/api/orders?${q}`)).orders)
    } catch (e) { message.error(String(e)) } finally { setLoading(false) }
  }, [f])

  useEffect(() => { load() }, [load])
  useEffect(() => {
    if (!auto) return undefined
    const iv = setInterval(load, 10000)
    return () => clearInterval(iv)
  }, [auto, load])

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Card size="small">
        <Space wrap>
          <Select
            allowClear placeholder={t('c.kind')} style={{ width: 130 }}
            value={f.kind || undefined}
            onChange={(v) => setF({ ...f, kind: v || '' })}
            options={KIND_KEYS.map((v) => ({ value: v, label: t(`k.${v}`) }))}
          />
          <Select
            allowClear placeholder={t('c.mode')} style={{ width: 100 }}
            value={f.mode || undefined}
            onChange={(v) => setF({ ...f, mode: v || '' })}
            options={[{ value: 'paper', label: t('c.paper') }, { value: 'live', label: t('c.live') }]}
          />
          <Select
            allowClear placeholder={t('c.strategy')} style={{ width: 130 }}
            value={f.strategy || undefined}
            onChange={(v) => setF({ ...f, strategy: v || '' })}
            options={STRATEGY_KEYS.map((v) => ({ value: v, label: v }))}
          />
          <Select
            style={{ width: 130 }} value={f.limit}
            onChange={(v) => setF({ ...f, limit: v })}
            options={[100, 300, 1000, 3000].map((n) => ({ value: n, label: t('c.last', { n }) }))}
          />
          <Button icon={<ReloadOutlined />} onClick={load} loading={loading}>{t('c.refresh')}</Button>
          <Button icon={<DownloadOutlined />} onClick={() => { window.location.href = '/api/export?what=orders' + (f.strategy ? `&strategy=${f.strategy}` : '') + (f.mode ? `&mode=${f.mode}` : '') }}>
            {t('c.export')}
          </Button>
          <Space size={4}>
            <Switch size="small" checked={auto} onChange={setAuto} />
            <Typography.Text type="secondary">{t('c.auto')}</Typography.Text>
          </Space>
          <Typography.Text type="secondary">{t('c.total', { n: rows.length })}</Typography.Text>
        </Space>
      </Card>

      <Card styles={{ body: { padding: 0 } }}>
        <Table
          rowKey="id" dataSource={rows} loading={loading} size="middle"
          scroll={{ x: 1150 }}
          pagination={{ pageSize: 25, showSizeChanger: true, pageSizeOptions: [25, 50, 100], showTotal: (n) => t('c.total', { n }) }}
          columns={[
            { title: '#', dataIndex: 'id', width: 70, sorter: (a, b) => a.id - b.id, defaultSortOrder: 'descend' },
            { title: t('c.time'), dataIndex: 'ts', width: 150, render: (v) => fmtTs(v) },
            {
              title: t('c.round'), dataIndex: 'slug', width: 190,
              render: (v) => <Typography.Text copyable={{ text: v }} style={{ fontSize: 12 }}>{v.replace('btc-updown-5m-', '5m-')}</Typography.Text>,
            },
            { title: t('c.strategy'), dataIndex: 'strategy', width: 110, render: (v) => (v ? <Tag color="geekblue">{v}</Tag> : '—') },
            { title: t('c.kind'), dataIndex: 'kind', width: 95, render: (k) => <KindTag k={k} /> },
            { title: t('c.side'), dataIndex: 'side', width: 95, render: (s) => <SideTag s={s} /> },
            { title: t('c.entry'), dataIndex: 'price', width: 85, render: (v) => num(v) },
            { title: t('c.amount'), dataIndex: 'usd', width: 85, render: (v) => (v != null ? `$${num(v)}` : '—') },
            { title: t('c.mode'), dataIndex: 'mode', width: 80, render: (m) => <ModeTag m={m} /> },
            {
              title: t('c.orderid'), dataIndex: 'order_id', width: 160, ellipsis: true,
              render: (v) => (v ? <Typography.Text copyable={{ text: v }} style={{ fontSize: 12 }}>{v.slice(0, 16)}…</Typography.Text> : '—'),
            },
            { title: t('c.note'), dataIndex: 'note', ellipsis: { showTitle: false }, render: (v) => <Typography.Text style={{ fontSize: 12 }} ellipsis={{ tooltip: v }}>{v || '—'}</Typography.Text> },
          ]}
        />
      </Card>
    </Space>
  )
}
