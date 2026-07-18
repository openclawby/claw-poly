import React, { useEffect, useState } from 'react'
import {
  Badge, Button, Card, Col, Divider, Drawer, Form, InputNumber, message,
  Popconfirm, Row, Select, Space, Switch, Table, Tabs, Tag, Tooltip, Typography,
} from 'antd'
import {
  FileTextOutlined, QuestionCircleOutlined, ReloadOutlined, SaveOutlined,
  TrophyOutlined,
} from '@ant-design/icons'
import { Column, Line } from '@ant-design/plots'
import { apiGet, apiPost, BLUE, CHART_THEME, ORANGE, Pnl } from '../util'
import { mx, useLang } from '../i18n'

const ORDER = ['pre_trend', 'fair_value', 'tick_momo', 'open_burst', 'prev_reverse']

function PickTable({ pick }) {
  const { t } = useLang()
  if (!pick) return null
  const rows = [
    { seg: t('s.bt.is'), ...pick.is, key: 'is' },
    { seg: t('s.bt.oos'), ...pick.oos, key: 'oos' },
  ]
  return (
    <Table
      size="small" pagination={false} rowKey="key" dataSource={rows}
      columns={[
        { title: t('s.bt'), dataIndex: 'seg' },
        { title: t('s.bt.trades'), dataIndex: 'trades' },
        { title: t('s.bt.wr'), dataIndex: 'win_rate', render: (v) => `${v}%` },
        { title: t('s.bt.ev'), dataIndex: 'ev_usd', render: (v) => <Pnl v={v} digits={2} /> },
        { title: t('s.bt.net'), dataIndex: 'net_usd', render: (v) => <Pnl v={v} /> },
      ]}
    />
  )
}

function StrategyCard({ k, meta, pick, data, onReload }) {
  const { t, lang } = useLang()
  const enabled = (data.enabled || []).includes(k)
  const [cfg, setCfg] = useState({})
  const [params, setParams] = useState({})
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    const c = data.strat_cfg?.[k] || {}
    setCfg({ usd: c.usd ?? 5, daily_loss: c.daily_loss ?? 10, entry_delay: c.entry_delay ?? 20 })
    const p = {}
    meta.params.forEach((pd) => { p[pd.key] = data.params?.[pd.key] })
    setParams(p)
  }, [data, k]) // eslint-disable-line

  const name = mx(lang, meta, 'name')

  const label = (text, hint) => (
    <Space size={4}>
      {text}
      {hint && <Tooltip title={hint}><QuestionCircleOutlined style={{ color: '#888' }} /></Tooltip>}
    </Space>
  )

  const save = async (cfgOverride, paramsOverride) => {
    setSaving(true)
    try {
      const c = cfgOverride || cfg
      const p = paramsOverride || params
      const cleanP = Object.fromEntries(
        Object.entries(p).filter(([, v]) => v !== null && v !== undefined && v !== ''))
      await apiPost('/api/settings', {
        strat_cfg: JSON.stringify({ ...(data.strat_cfg || {}), [k]: c }),
        params: JSON.stringify({ ...(data.params || {}), ...cleanP }),
      })
      message.success(t('s.saved', { name }))
      onReload()
    } catch (e) { message.error(String(e.message || e)) } finally { setSaving(false) }
  }

  const applyChampion = () => {
    if (!pick) return
    const c = { ...cfg, entry_delay: Math.max(0, pick.entry_delay || 0) }
    const p = { ...params, ...pick.params }
    setCfg(c)
    setParams(p)
    save(c, p)
  }

  const toggle = async (on) => {
    const list = on
      ? [...new Set([...(data.enabled || []), k])]
      : (data.enabled || []).filter((x) => x !== k)
    try {
      await apiPost('/api/settings', { enabled_strategies: JSON.stringify(list) })
      message.success(on ? t('s.enabled.msg', { name }) : t('s.disabled.msg', { name }))
      onReload()
    } catch (e) { message.error(String(e.message || e)) }
  }

  return (
    <Badge.Ribbon text={t('s.running')} color="green" style={{ display: enabled ? undefined : 'none' }}>
      <Card
        title={(
          <Space>
            {name}
            <Tag>{k}</Tag>
            {pick && <Tag color={pick.verdict.includes('✅') ? 'success' : 'warning'}>{pick.verdict}</Tag>}
          </Space>
        )}
        extra={(
          <Space>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>{t('s.today')} <Pnl v={data.today_pnl?.[k]} /></Typography.Text>
            <Switch checked={enabled} onChange={toggle} checkedChildren={t('s.on')} unCheckedChildren={t('s.off')} />
          </Space>
        )}
      >
        <Space direction="vertical" size={8} style={{ width: '100%' }}>
          <Typography.Text type="warning">{mx(lang, meta, 'tagline')}</Typography.Text>
          <Typography.Paragraph
            type="secondary" style={{ marginBottom: 0, fontSize: 12 }}
            ellipsis={{ rows: 2, expandable: true }}
          >
            {mx(lang, meta, 'logic')}
          </Typography.Paragraph>

          <Divider orientation="left" plain style={{ margin: '8px 0 4px' }}>{t('s.risk')}</Divider>
          <Row gutter={8}>
            <Col span={8}>
              <Form.Item label={label(t('s.usd'), t('s.usd.hint'))} style={{ marginBottom: 8 }}>
                <InputNumber min={0.5} max={1000} value={cfg.usd} style={{ width: '100%' }}
                  onChange={(v) => setCfg({ ...cfg, usd: v })} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item label={label(t('s.stop'), t('s.stop.hint'))} style={{ marginBottom: 8 }}>
                <InputNumber min={0} value={cfg.daily_loss} style={{ width: '100%' }}
                  onChange={(v) => setCfg({ ...cfg, daily_loss: v })} />
              </Form.Item>
            </Col>
            <Col span={8}>
              {k !== 'pre_trend' && (
                <Form.Item label={label(t('s.delay'), t('s.delay.hint'))} style={{ marginBottom: 8 }}>
                  <InputNumber min={0} max={240} value={cfg.entry_delay} style={{ width: '100%' }}
                    onChange={(v) => setCfg({ ...cfg, entry_delay: v })} />
                </Form.Item>
              )}
            </Col>
          </Row>

          <Divider orientation="left" plain style={{ margin: '4px 0' }}>{t('s.params')}</Divider>
          <Row gutter={8}>
            {meta.params.map((p) => (
              <Col span={12} key={p.key}>
                <Form.Item label={label(mx(lang, p, 'label'), mx(lang, p, 'hint'))} style={{ marginBottom: 8 }}>
                  {p.type === 'select'
                    ? (
                      <Select
                        value={params[p.key]} style={{ width: '100%' }}
                        options={(p.options || []).map((o) => ({ value: o.value, label: mx(lang, o, 'label') }))}
                        onChange={(v) => setParams({ ...params, [p.key]: v })}
                      />
                    )
                    : (
                      <InputNumber step={0.01} value={params[p.key]} style={{ width: '100%' }}
                        onChange={(v) => setParams({ ...params, [p.key]: v })} />
                    )}
                </Form.Item>
              </Col>
            ))}
          </Row>

          <Space>
            <Button type="primary" icon={<SaveOutlined />} loading={saving} onClick={() => save()}>
              {t('s.save')}
            </Button>
            {pick && (
              <Popconfirm title={t('s.champion.confirm')} onConfirm={applyChampion} okText={t('s.apply')} cancelText={t('c.cancel')}>
                <Button icon={<TrophyOutlined />}>{t('s.champion')}</Button>
              </Popconfirm>
            )}
          </Space>

          {pick ? <PickTable pick={pick} /> : <Typography.Text type="secondary">{t('s.nopick')}</Typography.Text>}
        </Space>
      </Card>
    </Badge.Ribbon>
  )
}

export default function Strategies() {
  const { t, lang } = useLang()
  const [data, setData] = useState(null)
  const [reports, setReports] = useState(null)
  const [drawer, setDrawer] = useState(false)

  const load = () => apiGet('/api/strategies').then(setData).catch((e) => message.error(String(e)))
  useEffect(() => { load() }, [])

  const openReports = async () => {
    setDrawer(true)
    if (!reports) setReports(await apiGet('/api/backtest').catch(() => ({})))
  }

  if (!data) return <Card loading />

  const picks = Object.fromEntries((data.picks || []).map((p) => [p.strategy, p]))
  const acc = data.accuracy

  const calData = (acc?.calibration || []).flatMap((c) => [
    { bucket: c.bucket, prob: c.mid * 100, series: lang === 'en' ? 'Model (bucket mid)' : '模型预测(区间中值)' },
    { bucket: c.bucket, prob: c.realized * 100, series: lang === 'en' ? 'Realized Up freq' : '实际上涨频率' },
  ])
  const confData = (acc?.confidence || []).map((c) => ({
    bucket: c.label, rate: c.total ? +(c.hits / c.total * 100).toFixed(1) : 0, n: c.total,
  }))

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Card size="small">
        <Space style={{ justifyContent: 'space-between', width: '100%' }} wrap>
          <Typography.Text>
            {t('s.enabled.n', { n: (data.enabled || []).length })}
            {(data.enabled || []).map((k) => (
              <Tag color={k === 'mystic_east' ? 'purple' : 'green'} key={k} style={{ marginLeft: 4 }}>
                {mx(lang, data.meta[k], 'name') || k}
              </Tag>
            ))}
            <Typography.Text type="secondary" style={{ marginLeft: 8, fontSize: 12 }}>
              {t('s.multi.tip')}
            </Typography.Text>
          </Typography.Text>
          <Space>
            <Button icon={<FileTextOutlined />} onClick={openReports}>{t('s.reports')}</Button>
            <Button icon={<ReloadOutlined />} onClick={load}>{t('c.refresh')}</Button>
          </Space>
        </Space>
      </Card>

      <Row gutter={[16, 16]}>
        {ORDER.filter((k) => data.meta[k]).map((k) => (
          <Col xs={24} xl={12} key={k}>
            <StrategyCard k={k} meta={data.meta[k]} pick={picks[k]} data={data} onReload={load} />
          </Col>
        ))}
      </Row>

      {acc && (
        <Card title={t('s.audit')} size="small">
          <Row gutter={[16, 16]}>
            <Col xs={24} lg={12}>
              <Line
                data={calData} xField="bucket" yField="prob" colorField="series"
                height={220} theme={CHART_THEME}
                scale={{ color: { range: [BLUE, ORANGE] } }}
                axis={{ y: { labelFormatter: (v) => `${v}%` } }}
                style={{ lineWidth: 2 }} point={{ sizeField: 3 }}
                legend={{ color: { position: 'top' } }}
              />
            </Col>
            <Col xs={24} lg={12}>
              <Column
                data={confData} xField="bucket" yField="rate"
                height={220} theme={CHART_THEME}
                style={{ fill: BLUE, radiusTopLeft: 4, radiusTopRight: 4 }}
                label={{ text: (d) => `${d.rate}%`, position: 'top', style: { fill: '#ddd' } }}
                axis={{ y: { labelFormatter: (v) => `${v}%` } }}
              />
            </Col>
          </Row>
        </Card>
      )}

      <Drawer title={t('s.reports')} open={drawer} onClose={() => setDrawer(false)} width={720}>
        <Tabs
          items={[
            { key: 'r', label: 'REPORT', children: <pre style={{ whiteSpace: 'pre-wrap', fontSize: 12 }}>{reports?.['REPORT.md'] || '…'}</pre> },
            { key: 'a', label: 'ACCURACY', children: <pre style={{ whiteSpace: 'pre-wrap', fontSize: 12 }}>{reports?.['ACCURACY.md'] || '…'}</pre> },
            { key: 'p', label: 'PREBET', children: <pre style={{ whiteSpace: 'pre-wrap', fontSize: 12 }}>{reports?.['PREBET.md'] || '…'}</pre> },
          ]}
        />
      </Drawer>
    </Space>
  )
}
